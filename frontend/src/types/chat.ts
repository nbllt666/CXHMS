// ========== 共享类型：Chat ==========
// F8: 统一 Message / ToolCall / StreamToolCall / StreamChunk / Session 类型定义。
// 唯一权威来源；chatStreamReducer.ts、api/chatStream.ts、store/chatStore.ts、
// pages/MemoryAgentPage.tsx 均 re-export 此处定义。

/**
 * 单条聊天消息。涵盖 ChatPage 与 MemoryAgentPage 的字段并集。
 */
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  memory_refs?: number[];
  tool_calls?: ToolCall[];
  thinking?: string;
  images?: string[]; // base64 encoded images
  content_type?: 'diary_summary' | 'archive_notice' | string;
}

/**
 * 工具调用记录（消息内嵌）。arguments/result 用 unknown 以兼容异构来源。
 */
export interface ToolCall {
  id: string;
  name: string;
  arguments?: unknown;
  result?: unknown;
  status?: 'pending' | 'executing' | 'completed' | 'failed';
}

/**
 * 流式 chunk 中的 tool_call 原始结构（兼容 OpenAI 风格 function 包装）。
 */
export interface StreamToolCall {
  id?: string;
  name?: string;
  arguments?: unknown;
  function?: {
    name?: string;
    arguments?: unknown;
  };
}

/**
 * SSE / WS 流式 chunk。取 chatStream.ts 与 chatStreamReducer.ts 字段并集。
 */
export interface StreamChunk {
  type: string;
  content?: string;
  done?: boolean;
  error?: string;
  session_id?: string;
  tool_call?: Record<string, unknown>;
  tool_name?: string;
  result?: unknown;
  thinking?: string;
  target_session_id?: string;
  summarized_up_to?: number;
}

/**
 * 会话。与后端 /api/context/sessions 返回结构对齐。
 */
export interface Session {
  id: string;
  title: string;
  agent_id?: string;
  message_count?: number;
  created_at?: string;
  updated_at?: string;
}
