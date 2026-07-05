// ========== chatStream (SSE 解析) 单元测试 ==========
// G6: 覆盖 ChatPage SSE 分支核心——readSseStream 解析 + fetchSseStream 错误处理。
// mock fetch 返回带 ReadableStream-like body 的 Response，验证 onChunk 回调。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  sendMessageStream,
  sendMemoryAgentMessageStream,
  sendSummaryAgentMessageStream,
} from './chatStream';
import type { StreamChunk } from '../types/chat';

// 构造 mock fetch Response：body.getReader() 顺序返回编码后的 chunk。
// 不依赖全局 Response/ReadableStream，避免 jsdom 差异。
function makeMockResponse(
  chunks: string[],
  options: { status?: number; statusText?: string; bodyText?: string } = {}
) {
  const { status = 200, statusText = 'OK', bodyText } = options;
  const encoder = new TextEncoder();
  const encoded = chunks.map((c) => encoder.encode(c));
  let index = 0;
  const reader = {
    read: async () => {
      if (index < encoded.length) {
        return { done: false, value: encoded[index++] };
      }
      return { done: true, value: undefined };
    },
    releaseLock: () => {},
  };
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    body: { getReader: () => reader },
    text: () => Promise.resolve(bodyText ?? chunks.join('')),
  } as unknown as Response;
}

describe('chatStream (SSE)', () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('sendMessageStream', () => {
    it('parses multiple SSE data lines and forwards chunks', async () => {
      const sseLines = [
        'data: {"type":"content","content":"hel"}\n',
        'data: {"type":"content","content":"lo"}\n',
        'data: {"type":"done"}\n',
      ];
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(sseLines));

      const onChunk = vi.fn();
      await sendMessageStream('hello', onChunk, 'default');

      expect(onChunk).toHaveBeenCalledTimes(3);
      expect(onChunk).toHaveBeenNthCalledWith(1, { type: 'content', content: 'hel' });
      expect(onChunk).toHaveBeenNthCalledWith(2, { type: 'content', content: 'lo' });
      expect(onChunk).toHaveBeenNthCalledWith(3, { type: 'done' });
    });

    it('accumulates content across chunks (integration with applyStreamChunk)', async () => {
      const sseLines = [
        'data: {"type":"content","content":"Hello"}\n',
        'data: {"type":"content","content":" world"}\n',
        'data: {"type":"done"}\n',
      ];
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(sseLines));

      const chunks: StreamChunk[] = [];
      await sendMessageStream('q', (c) => chunks.push(c), 'default');

      // 模拟 ChatPage 的 applyStreamChunk 累积
      let acc = '';
      for (const c of chunks) {
        if (c.type === 'content' && c.content) acc += c.content;
      }
      expect(acc).toBe('Hello world');
      expect(chunks[chunks.length - 1].type).toBe('done');
    });

    it('forwards error chunk when server sends error type', async () => {
      const sseLines = ['data: {"type":"content","content":"partial"}\n', 'data: {"type":"error","error":"boom"}\n'];
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(sseLines));

      const onChunk = vi.fn();
      await sendMessageStream('q', onChunk, 'default');

      expect(onChunk).toHaveBeenCalledWith({ type: 'error', error: 'boom' });
    });

    it('handles partial chunk split across reads', async () => {
      // 一个 SSE 行被拆到两次 read 中，验证 buffer 拼接
      const sseLines = ['data: {"type":"conten', 't","content":"x"}\n', 'data: {"type":"done"}\n'];
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(sseLines));

      const onChunk = vi.fn();
      await sendMessageStream('q', onChunk, 'default');

      expect(onChunk).toHaveBeenCalledTimes(2);
      expect(onChunk).toHaveBeenNthCalledWith(1, { type: 'content', content: 'x' });
    });

    it('ignores non-data lines (comments / heartbeats)', async () => {
      const sseLines = [': comment\n', 'data: {"type":"content","content":"ok"}\n', '\n', 'data: {"type":"done"}\n'];
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(sseLines));

      const onChunk = vi.fn();
      await sendMessageStream('q', onChunk, 'default');

      expect(onChunk).toHaveBeenCalledTimes(2);
    });

    it('sends POST to /api/chat/stream with message + agent_id', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(['data: {"type":"done"}\n']));

      await sendMessageStream('hello', () => {}, 'agent-1');

      expect(fetch).toHaveBeenCalledTimes(1);
      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(url).toContain('/api/chat/stream');
      expect(init?.method).toBe('POST');
      const body = JSON.parse(init?.body as string);
      expect(body.message).toBe('hello');
      expect(body.agent_id).toBe('agent-1');
    });

    it('includes images in body when provided', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(['data: {"type":"done"}\n']));
      await sendMessageStream('hi', () => {}, 'default', ['img1', 'img2']);
      const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
      expect(body.images).toEqual(['img1', 'img2']);
    });

    it('omits images when empty', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(['data: {"type":"done"}\n']));
      await sendMessageStream('hi', () => {}, 'default', []);
      const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
      expect(body.images).toBeUndefined();
    });
  });

  describe('sendMessageStream - HTTP error handling', () => {
    it('emits error chunk when response status is not ok', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(
        makeMockResponse([], { status: 500, statusText: 'Internal Server Error', bodyText: 'server fail' })
      );

      const onChunk = vi.fn();
      await sendMessageStream('q', onChunk, 'default');

      expect(onChunk).toHaveBeenCalledTimes(1);
      expect(onChunk).toHaveBeenCalledWith({
        type: 'error',
        error: expect.stringContaining('HTTP 500'),
      });
      expect(onChunk).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', error: expect.stringContaining('server fail') })
      );
    });

    it('emits error chunk with "No response body" when body is null', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        body: null,
        text: () => Promise.resolve(''),
      } as unknown as Response);

      const onChunk = vi.fn();
      await sendMessageStream('q', onChunk, 'default');

      expect(onChunk).toHaveBeenCalledWith({ type: 'error', error: 'No response body' });
    });

    it('silently returns on AbortError (user cancel)', async () => {
      const abortErr = new DOMException('Aborted', 'AbortError');
      vi.mocked(fetch).mockRejectedValueOnce(abortErr);

      const onChunk = vi.fn();
      await sendMessageStream('q', onChunk, 'default');

      expect(onChunk).not.toHaveBeenCalled();
    });

    it('emits error chunk on non-Abort fetch failure', async () => {
      vi.mocked(fetch).mockRejectedValueOnce(new Error('Network down'));

      const onChunk = vi.fn();
      await sendMessageStream('q', onChunk, 'default');

      expect(onChunk).toHaveBeenCalledWith({
        type: 'error',
        error: expect.stringContaining('Network down'),
      });
    });
  });

  describe('sendMemoryAgentMessageStream', () => {
    it('POSTs to /api/memory-agent/chat/stream with message only', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(['data: {"type":"done"}\n']));
      await sendMemoryAgentMessageStream('hi', () => {});
      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(url).toContain('/api/memory-agent/chat/stream');
      const body = JSON.parse(init?.body as string);
      expect(body.message).toBe('hi');
    });
  });

  describe('sendSummaryAgentMessageStream', () => {
    it('POSTs to /api/summary-agent/chat/stream with message + target_session_id', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(['data: {"type":"done"}\n']));
      await sendSummaryAgentMessageStream('summarize', () => {}, undefined, {
        targetSessionId: 'sess-1',
      });
      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(url).toContain('/api/summary-agent/chat/stream');
      const body = JSON.parse(init?.body as string);
      expect(body.message).toBe('summarize');
      expect(body.target_session_id).toBe('sess-1');
    });
  });

  describe('auth header', () => {
    it('includes Bearer token from localStorage', async () => {
      vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
        key === 'cxhms-token' ? 'tok-123' : null
      );
      vi.mocked(fetch).mockResolvedValueOnce(makeMockResponse(['data: {"type":"done"}\n']));

      await sendMessageStream('q', () => {}, 'default');

      const init = vi.mocked(fetch).mock.calls[0][1];
      expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer tok-123');
    });
  });
});
