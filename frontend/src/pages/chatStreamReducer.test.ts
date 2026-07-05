// ========== chatStreamReducer 单元测试 ==========
// G6: 覆盖 F2 抽取的 WS/SSE 公共 reducer。
// 纯函数测试，无 React 渲染依赖。覆盖 content/thinking/tool_call/tool_start/tool_result/
// done/cancelled/error 全部 chunk 类型 + 守卫子句 + 结构性共享。

import { describe, it, expect, vi } from 'vitest';
import { applyStreamChunk, isStreamFinished } from './chatStreamReducer';
import type { Message, StreamChunk } from '../types/chat';

// done/cancelled/error 分支调用 i18n.t，mock 之避免依赖 i18n 初始化与 locale 文件。
// 返回值约定：带 error 选项时返回 `${key}:${error}`，便于断言；否则返回 key。
vi.mock('../i18n', () => ({
  default: {
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && 'error' in opts) return `${key}:${String(opts.error)}`;
      return key;
    },
  },
}));

// crypto.randomUUID 在 Node 18+ jsdom 下可用；为防止环境差异，stub 之保证 tool_call 测试稳定。
if (!globalThis.crypto || !globalThis.crypto.randomUUID) {
  Object.defineProperty(globalThis, 'crypto', {
    value: { randomUUID: () => 'mock-uuid-' + Math.random().toString(36).slice(2) },
    writable: true,
    configurable: true,
  });
}

function makeAssistantMessage(id = 'asst-1', overrides: Partial<Message> = {}): Message {
  return {
    id,
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString(),
    thinking: '',
    tool_calls: [],
    ...overrides,
  };
}

describe('chatStreamReducer', () => {
  describe('isStreamFinished', () => {
    it('returns true for done/cancelled/error', () => {
      expect(isStreamFinished({ type: 'done' })).toBe(true);
      expect(isStreamFinished({ type: 'cancelled' })).toBe(true);
      expect(isStreamFinished({ type: 'error', error: 'boom' })).toBe(true);
    });

    it('returns false for content/thinking/tool_call/tool_start/tool_result/session', () => {
      expect(isStreamFinished({ type: 'content', content: 'a' })).toBe(false);
      expect(isStreamFinished({ type: 'thinking', content: 'b' })).toBe(false);
      expect(isStreamFinished({ type: 'tool_call', tool_call: {} })).toBe(false);
      expect(isStreamFinished({ type: 'tool_start', tool_name: 'x' })).toBe(false);
      expect(isStreamFinished({ type: 'tool_result', tool_name: 'x', result: 1 })).toBe(false);
      expect(isStreamFinished({ type: 'session', session_id: 's1' })).toBe(false);
    });
  });

  describe('applyStreamChunk - guard clauses', () => {
    it('returns original array when messages is empty', () => {
      const result = applyStreamChunk([], { type: 'content', content: 'x' }, 'asst-1');
      expect(result).toEqual([]);
    });

    it('returns original array (same ref) when last message id !== assistantId', () => {
      const msgs = [makeAssistantMessage('other-id')];
      const result = applyStreamChunk(msgs, { type: 'content', content: 'x' }, 'asst-1');
      expect(result).toBe(msgs);
    });
  });

  describe('applyStreamChunk - content', () => {
    it('appends content to last message', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: 'Hello' })];
      const result = applyStreamChunk(msgs, { type: 'content', content: ' world' }, 'asst-1');
      expect(result[0].content).toBe('Hello world');
    });

    it('does not mutate original array (structural sharing)', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: 'Hello' })];
      const result = applyStreamChunk(msgs, { type: 'content', content: '!' }, 'asst-1');
      expect(msgs[0].content).toBe('Hello');
      expect(result).not.toBe(msgs);
    });

    it('returns original when content chunk has empty content', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: 'Hello' })];
      const result = applyStreamChunk(msgs, { type: 'content', content: '' }, 'asst-1');
      expect(result).toBe(msgs);
    });
  });

  describe('applyStreamChunk - thinking', () => {
    it('accumulates thinking content', () => {
      const msgs = [makeAssistantMessage('asst-1', { thinking: 'step1' })];
      const result = applyStreamChunk(msgs, { type: 'thinking', content: ' step2' }, 'asst-1');
      expect(result[0].thinking).toBe('step1 step2');
    });

    it('initializes thinking when undefined', () => {
      const msgs = [makeAssistantMessage('asst-1', { thinking: undefined })];
      const result = applyStreamChunk(msgs, { type: 'thinking', content: 'first' }, 'asst-1');
      expect(result[0].thinking).toBe('first');
    });
  });

  describe('applyStreamChunk - tool_call', () => {
    it('appends a new pending tool_call', () => {
      const msgs = [makeAssistantMessage('asst-1')];
      const chunk: StreamChunk = {
        type: 'tool_call',
        tool_call: { id: 'tc-1', name: 'search', arguments: { q: 'x' } },
      };
      const result = applyStreamChunk(msgs, chunk, 'asst-1');
      expect(result[0].tool_calls).toHaveLength(1);
      expect(result[0].tool_calls![0].id).toBe('tc-1');
      expect(result[0].tool_calls![0].name).toBe('search');
      expect(result[0].tool_calls![0].status).toBe('pending');
    });

    it('uses function.name when top-level name missing (OpenAI style)', () => {
      const msgs = [makeAssistantMessage('asst-1')];
      const chunk: StreamChunk = {
        type: 'tool_call',
        tool_call: { id: 'tc-2', function: { name: 'calc', arguments: '{}' } },
      };
      const result = applyStreamChunk(msgs, chunk, 'asst-1');
      expect(result[0].tool_calls![0].name).toBe('calc');
    });

    it('returns original when tool_call field missing', () => {
      const msgs = [makeAssistantMessage('asst-1')];
      const result = applyStreamChunk(msgs, { type: 'tool_call' }, 'asst-1');
      expect(result).toBe(msgs);
    });
  });

  describe('applyStreamChunk - tool_start', () => {
    it('sets matching tool_call status to executing', () => {
      const msgs = [
        makeAssistantMessage('asst-1', {
          tool_calls: [
            { id: 'tc-1', name: 'search', arguments: {}, status: 'pending' },
            { id: 'tc-2', name: 'calc', arguments: {}, status: 'pending' },
          ],
        }),
      ];
      const result = applyStreamChunk(msgs, { type: 'tool_start', tool_name: 'search' }, 'asst-1');
      expect(result[0].tool_calls![0].status).toBe('executing');
      expect(result[0].tool_calls![1].status).toBe('pending');
    });

    it('returns original when message has no tool_calls', () => {
      const msgs = [makeAssistantMessage('asst-1', { tool_calls: undefined })];
      const result = applyStreamChunk(msgs, { type: 'tool_start', tool_name: 'x' }, 'asst-1');
      expect(result).toBe(msgs);
    });
  });

  describe('applyStreamChunk - tool_result', () => {
    it('sets matching tool_call status to completed with result', () => {
      const msgs = [
        makeAssistantMessage('asst-1', {
          tool_calls: [{ id: 'tc-1', name: 'search', arguments: {}, status: 'executing' }],
        }),
      ];
      const result = applyStreamChunk(
        msgs,
        { type: 'tool_result', tool_name: 'search', result: { hits: 5 } },
        'asst-1'
      );
      expect(result[0].tool_calls![0].status).toBe('completed');
      expect(result[0].tool_calls![0].result).toEqual({ hits: 5 });
    });
  });

  describe('applyStreamChunk - done', () => {
    it('fills empty content with i18n streamComplete key', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: '' })];
      const result = applyStreamChunk(msgs, { type: 'done' }, 'asst-1');
      expect(result[0].content).toBe('chat.streamComplete');
    });

    it('preserves existing content', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: 'final answer' })];
      const result = applyStreamChunk(msgs, { type: 'done' }, 'asst-1');
      expect(result[0].content).toBe('final answer');
    });
  });

  describe('applyStreamChunk - cancelled', () => {
    it('fills empty content with i18n streamCancelled key', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: '' })];
      const result = applyStreamChunk(msgs, { type: 'cancelled' }, 'asst-1');
      expect(result[0].content).toBe('chat.streamCancelled');
    });
  });

  describe('applyStreamChunk - error', () => {
    it('sets content to i18n streamError with error detail', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: '' })];
      const result = applyStreamChunk(msgs, { type: 'error', error: 'boom' }, 'asst-1');
      expect(result[0].content).toBe('chat.streamError:boom');
    });

    it('uses unknownError key when chunk.error missing', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: '' })];
      const result = applyStreamChunk(msgs, { type: 'error' }, 'asst-1');
      expect(result[0].content).toBe('chat.streamError:chat.unknownError');
    });
  });

  describe('applyStreamChunk - unknown chunk type', () => {
    it('returns original array for unknown type', () => {
      const msgs = [makeAssistantMessage('asst-1', { content: 'x' })];
      const result = applyStreamChunk(msgs, { type: 'session', session_id: 's1' }, 'asst-1');
      expect(result).toBe(msgs);
    });
  });
});
