// ========== chatApi 单元测试 ==========
// G6: 覆盖 Chat / Session / History 方法。
// B9 回归契约：写操作（POST/PUT/DELETE）使用对应 HTTP method（非 GET），
//              B9 修复后 client.ts interceptor 不会对这些方法重试。
//              本测试验证 chatApi 写方法走 POST/PUT/DELETE 路径（B9 前置条件）。

import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}));

vi.mock('./client', () => ({
  apiClient: {
    get: mocks.get,
    post: mocks.post,
    put: mocks.put,
    delete: mocks.del,
  },
}));

import { chatApi } from './chat';

describe('chatApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('Chat', () => {
    it('sendMessage → POST /api/chat with message/session_id/agent_id', async () => {
      const data = { status: 'success', response: 'hi', session_id: 's1' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await chatApi.sendMessage('Hello', 'session-1', 'agent-1');
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/chat', {
        message: 'Hello',
        session_id: 'session-1',
        agent_id: 'agent-1',
      });
    });

    it('sendMessage defaults agent_id to "default"', async () => {
      mocks.post.mockResolvedValueOnce({ data: {} });
      await chatApi.sendMessage('Hi');
      expect(mocks.post).toHaveBeenCalledWith('/api/chat', {
        message: 'Hi',
        session_id: undefined,
        agent_id: 'default',
      });
    });
  });

  describe('Sessions', () => {
    it('getSessions → GET /api/context/sessions', async () => {
      const data = [{ id: '1', title: 'S1' }];
      mocks.get.mockResolvedValueOnce({ data });
      const result = await chatApi.getSessions();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/context/sessions');
    });

    it('createSession → POST /api/context/sessions with workspace_id + title', async () => {
      const data = { id: 'new', title: '新对话' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await chatApi.createSession('My Chat', 'agent-1');
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/context/sessions', {
        workspace_id: 'default',
        title: 'My Chat',
        agent_id: 'agent-1',
      });
    });

    it('createSession defaults title to 新对话', async () => {
      mocks.post.mockResolvedValueOnce({ data: {} });
      await chatApi.createSession();
      expect(mocks.post).toHaveBeenCalledWith('/api/context/sessions', {
        workspace_id: 'default',
        title: '新对话',
      });
    });

    it('deleteSession → DELETE /api/context/sessions/{id} (write op, no retry per B9)', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await chatApi.deleteSession('session-1');
      expect(mocks.del).toHaveBeenCalledWith('/api/context/sessions/session-1');
    });

    it('clearSessionMessages → DELETE /api/context/sessions/{id}/messages', async () => {
      mocks.del.mockResolvedValueOnce({ data: { status: 'ok', message: 'cleared' } });
      const result = await chatApi.clearSessionMessages('session-1');
      expect(result.status).toBe('ok');
      expect(mocks.del).toHaveBeenCalledWith('/api/context/sessions/session-1/messages');
    });

    it('clearAllSessions → DELETE /api/context/sessions/all', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await chatApi.clearAllSessions();
      expect(mocks.del).toHaveBeenCalledWith('/api/context/sessions/all');
    });
  });

  describe('History & Context', () => {
    it('getChatHistory → GET /api/chat/history/{sessionId}', async () => {
      const data = { messages: [{ id: '1', role: 'user', content: 'hi' }] };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await chatApi.getChatHistory('agent-default');
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/chat/history/agent-default');
    });

    it('getAgentContext → GET /api/agents/{id}/context with limit param', async () => {
      mocks.get.mockResolvedValueOnce({ data: { messages: [] } });
      await chatApi.getAgentContext('agent-1', 20);
      expect(mocks.get).toHaveBeenCalledWith('/api/agents/agent-1/context', { params: { limit: 20 } });
    });

    it('getAgentContext defaults limit to 50', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await chatApi.getAgentContext('agent-1');
      expect(mocks.get).toHaveBeenCalledWith('/api/agents/agent-1/context', { params: { limit: 50 } });
    });
  });

  describe('Streaming delegates', () => {
    it('chatApi exposes sendMessageStream / sendMemoryAgentMessageStream / sendSummaryAgentMessageStream', () => {
      expect(typeof chatApi.sendMessageStream).toBe('function');
      expect(typeof chatApi.sendMemoryAgentMessageStream).toBe('function');
      expect(typeof chatApi.sendSummaryAgentMessageStream).toBe('function');
    });
  });

  // B9 回归契约：写操作必须使用 POST/PUT/DELETE，不能误用 GET。
  // 这是 B9「写操作不重试」的前提——interceptor 按 method 区分时，写方法才会被排除。
  describe('B9 contract: write operations use non-GET methods', () => {
    it('sendMessage uses POST', async () => {
      mocks.post.mockResolvedValueOnce({ data: {} });
      await chatApi.sendMessage('x');
      expect(mocks.post).toHaveBeenCalled();
      expect(mocks.get).not.toHaveBeenCalled();
    });

    it('createSession uses POST', async () => {
      mocks.post.mockResolvedValueOnce({ data: {} });
      await chatApi.createSession();
      expect(mocks.post).toHaveBeenCalled();
    });

    it('deleteSession uses DELETE', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await chatApi.deleteSession('s1');
      expect(mocks.del).toHaveBeenCalled();
    });

    it('clearSessionMessages uses DELETE', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await chatApi.clearSessionMessages('s1');
      expect(mocks.del).toHaveBeenCalled();
    });
  });
});
