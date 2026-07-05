import { apiClient } from './client';
import {
  sendMessageStream,
  sendMemoryAgentMessageStream,
  sendSummaryAgentMessageStream,
  type StreamChunk,
} from './chatStream';

// ========== Chat / Session APIs ==========
// 从 client.ts 拆分：聊天发送、会话管理、历史。
// 流式方法见 ./chatStream，此处重新挂载到 chatApi 以保持聚合兼容。
// LRU cache 已移除，统一交 React Query。

export type { StreamChunk } from './chatStream';

export const chatApi = {
  // Chat
  async sendMessage(message: string, sessionId?: string, agentId?: string) {
    const response = await apiClient.post('/api/chat', {
      message,
      session_id: sessionId,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  // Context / Sessions
  async getSessions() {
    const response = await apiClient.get('/api/context/sessions');
    return response.data;
  },

  async createSession(title?: string, agentId?: string) {
    const response = await apiClient.post('/api/context/sessions', {
      workspace_id: 'default',
      title: title || '新对话',
      ...(agentId ? { agent_id: agentId } : {}),
    });
    return response.data;
  },

  async deleteSession(sessionId: string) {
    const response = await apiClient.delete(`/api/context/sessions/${sessionId}`);
    return response.data;
  },

  async clearSessionMessages(sessionId: string): Promise<{ status: string; message: string }> {
    const response = await apiClient.delete(`/api/context/sessions/${sessionId}/messages`);
    return response.data;
  },

  async clearAllSessions() {
    const response = await apiClient.delete('/api/context/sessions/all');
    return response.data;
  },

  // History & Context
  async getChatHistory(sessionId: string) {
    // 接受完整 session key（如 `agent-<agentId>` 或真实 sessionId）。
    // 调用方负责统一口径：`currentSessionId || \`agent-${agentId}\``，
    // 与 clearSessionMessages 保持一致，避免 clear 与 history 取不同 key 的错配。
    const response = await apiClient.get(`/api/chat/history/${sessionId}`);
    return response.data;
  },

  async getAgentContext(agentId: string, limit: number = 50) {
    const response = await apiClient.get(`/api/agents/${agentId}/context`, { params: { limit } });
    return response.data;
  },

  // Streaming（委托至 ./chatStream）
  sendMessageStream,
  sendMemoryAgentMessageStream,
  sendSummaryAgentMessageStream,
};
