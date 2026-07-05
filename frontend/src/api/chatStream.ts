import { apiClient } from './client';

// ========== Chat Streaming APIs ==========
// 从 chat.ts 拆分：3 个 SSE 流式方法（sendMessageStream / sendMemoryAgentMessageStream /
// sendSummaryAgentMessageStream）。三者结构高度相似，后续可进一步抽取公共 SSE 解析 helper。

import type { StreamChunk } from '../types/chat';

// F8: StreamChunk 统一到 types/chat.ts。re-export 保持向后兼容。
export type { StreamChunk };

/**
 * 通用 SSE 读取循环：从给定的 fetch Response 解析 `data: ` 行并回调 onChunk。
 * 抽取以减少三个 stream 方法的重复样板。
 */
async function readSseStream(
  response: Response,
  onChunk: (chunk: StreamChunk) => void
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) {
    onChunk({ type: 'error', error: 'No response body' });
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (value) {
        buffer += decoder.decode(value, { stream: true });
      }

      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim().startsWith('data: ')) {
          try {
            const data = JSON.parse(line.trim().slice(6));
            onChunk(data);
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }

      if (done) {
        // 处理 buffer 中剩余的数据
        if (buffer.trim().startsWith('data: ')) {
          try {
            const data = JSON.parse(buffer.trim().slice(6));
            onChunk(data);
          } catch (e) {
            console.error('Failed to parse remaining buffer:', e);
          }
        }
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** 构造带鉴权头的 SSE fetch 请求 */
function buildSseRequest(body: Record<string, unknown>, signal?: AbortSignal): RequestInit {
  return {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('cxhms-token') || ''}`,
    },
    body: JSON.stringify(body),
    signal,
  };
}

/** 处理 SSE fetch 调用全流程：fetch → 错误检查 → 流读取 */
async function fetchSseStream(
  url: string,
  body: Record<string, unknown>,
  onChunk: (chunk: StreamChunk) => void,
  signal?: AbortSignal
): Promise<void> {
  try {
    const response = await fetch(url, buildSseRequest(body, signal));

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      onChunk({ type: 'error', error: `HTTP ${response.status}: ${errorText}` });
      return;
    }

    await readSseStream(response, onChunk);
  } catch (streamError) {
    // 区分 AbortError（用户取消）与真实错误
    if (streamError instanceof DOMException && streamError.name === 'AbortError') {
      return;
    }
    onChunk({
      type: 'error',
      error: `Fetch error: ${streamError instanceof Error ? streamError.message : 'Unknown error'}`,
    });
  }
}

// ========== Streaming Chat API ==========
export async function sendMessageStream(
  message: string,
  onChunk: (chunk: StreamChunk) => void,
  agentId?: string,
  images?: string[],
  signal?: AbortSignal
): Promise<void> {
  await fetchSseStream(
    `${apiClient.defaults.baseURL}/api/chat/stream`,
    {
      message,
      agent_id: agentId || 'default',
      images: images && images.length > 0 ? images : undefined,
    },
    onChunk,
    signal
  );
}

// ========== Memory Agent Streaming API ==========
export async function sendMemoryAgentMessageStream(
  message: string,
  onChunk: (chunk: StreamChunk) => void,
  signal?: AbortSignal
): Promise<void> {
  await fetchSseStream(
    `${apiClient.defaults.baseURL}/api/memory-agent/chat/stream`,
    { message },
    onChunk,
    signal
  );
}

// ========== Summary Agent Streaming API ==========
export async function sendSummaryAgentMessageStream(
  message: string,
  onChunk: (chunk: StreamChunk) => void,
  signal?: AbortSignal,
  options?: { targetSessionId?: string }
): Promise<void> {
  await fetchSseStream(
    `${apiClient.defaults.baseURL}/api/summary-agent/chat/stream`,
    {
      message,
      target_session_id: options?.targetSessionId,
    },
    onChunk,
    signal
  );
}
