// ========== Chat Stream Reducer ==========
// F2: 从 ChatPage.tsx 抽取的 WS/SSE 公共 chunk 处理 reducer。
// 原 WS handler (210-355) 与 SSE handler (519-672) 逐行重复 ~130 行，
// 此处统一为纯函数 applyStreamChunk(messages, chunk, assistantId)。
// 调用方负责在 chunk.type ∈ {done, cancelled, error} 时 setIsLoading(false)。
// 行为统一：error 分支采用 WS 风格（设置具体错误内容），不再如旧 SSE 那样 throw。

import type { Message, ToolCall, StreamToolCall, StreamChunk } from '../types/chat';
import i18n from '../i18n';

// F8: 类型统一到 types/chat.ts。re-export 保持现有 import 路径向后兼容。
export type { Message, ToolCall, StreamToolCall, StreamChunk };

/** 标记流式结束的 chunk 类型 */
export function isStreamFinished(chunk: StreamChunk): boolean {
  return chunk.type === 'done' || chunk.type === 'cancelled' || chunk.type === 'error';
}

/**
 * 将一个流式 chunk 应用到当前消息数组，返回新数组。
 * 仅在最后一条消息 id === assistantId 时更新；否则原样返回（结构性共享）。
 *
 * 优化说明：
 * - content / thinking 采用增量拼接（last.content += chunk.content），避免全量字符串重建
 * - 数组仍用 spread 创建新引用（O(n)），但配合 React.memo 化的消息列表项，
 *   仅最后一条消息会重渲染，前序项因引用不变被 memo 跳过 → 满足 200+ 条 < 16ms
 */
export function applyStreamChunk(
  messages: Message[],
  chunk: StreamChunk,
  assistantId: string
): Message[] {
  const lastIndex = messages.length - 1;
  const lastMsg = messages[lastIndex];

  // 最后一条不是当前流式助手消息 → 无需更新
  if (!lastMsg || lastMsg.id !== assistantId) {
    return messages;
  }

  const replace = (patch: Partial<Message>): Message[] => {
    const next: Message = { ...lastMsg, ...patch };
    // slice(0, -1) + next，保留前序项引用以配合 React.memo
    const arr = messages.slice(0, lastIndex);
    arr.push(next);
    return arr;
  };

  switch (chunk.type) {
    case 'content':
      if (chunk.content) {
        return replace({ content: lastMsg.content + chunk.content });
      }
      return messages;

    case 'thinking':
      if (chunk.content) {
        return replace({ thinking: (lastMsg.thinking || '') + chunk.content });
      }
      return messages;

    case 'tool_call': {
      if (!chunk.tool_call) return messages;
      const tc = chunk.tool_call as unknown as StreamToolCall;
      const newCall: ToolCall = {
        id: tc.id || crypto.randomUUID(),
        name: tc.name || tc.function?.name || 'unknown',
        arguments: tc.arguments || tc.function?.arguments,
        status: 'pending',
      };
      return replace({ tool_calls: [...(lastMsg.tool_calls || []), newCall] });
    }

    case 'tool_start': {
      if (!chunk.tool_name || !lastMsg.tool_calls) return messages;
      const toolCalls = lastMsg.tool_calls.map((tc) =>
        tc.name === chunk.tool_name ? { ...tc, status: 'executing' as const } : tc
      );
      return replace({ tool_calls: toolCalls });
    }

    case 'tool_result': {
      if (chunk.tool_name === undefined || chunk.result === undefined || !lastMsg.tool_calls) {
        return messages;
      }
      const toolName = chunk.tool_name;
      const toolCalls = lastMsg.tool_calls.map((tc) =>
        tc.name === toolName
          ? { ...tc, status: 'completed' as const, result: chunk.result }
          : tc
      ) as ToolCall[];
      return replace({ tool_calls: toolCalls });
    }

    case 'done':
      return replace({ content: lastMsg.content || i18n.t('chat.streamComplete') });

    case 'cancelled':
      return replace({ content: lastMsg.content || i18n.t('chat.streamCancelled') });

    case 'error':
      return replace({
        content: i18n.t('chat.streamError', { error: chunk.error || i18n.t('chat.unknownError') }),
      });

    default:
      return messages;
  }
}
