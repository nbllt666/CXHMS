import { apiClient } from './client';

// ========== Memory APIs ==========
// 从 client.ts 拆分：记忆 CRUD / 永久记忆 / 归档 / 批量 / 记忆聊天 / 日记
// LRU cache 已移除，统一交 React Query。

export const memoryApi = {
  // Agent Memory Tables
  async getAgentMemoryTables() {
    const response = await apiClient.get('/api/memories/agents');
    return response.data;
  },

  // Memories
  async getMemories(params?: {
    type?: string;
    limit?: number;
    offset?: number;
    query?: string;
    agent_id?: string;
  }) {
    const response = await apiClient.get('/api/memories', { params });
    return response.data;
  },

  async createMemory(data: {
    content: string;
    type?: string;
    importance?: number;
    tags?: string[];
    agent_id?: string;
  }) {
    const response = await apiClient.post('/api/memories', data);
    return response.data;
  },

  async updateMemory(
    id: number,
    data: Partial<{
      content: string;
      type: string;
      importance: number;
      tags: string[];
    }>,
    agentId?: string
  ) {
    const response = await apiClient.put(`/api/memories/${id}`, {
      ...data,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async deleteMemory(id: number, soft_delete: boolean = false) {
    const response = await apiClient.delete(`/api/memories/${id}`, {
      params: { soft_delete },
    });
    return response.data;
  },

  // Permanent Memories
  async getPermanentMemories(params?: { limit?: number; offset?: number; workspace_id?: string }) {
    const response = await apiClient.get('/api/memories/permanent', { params });
    return response.data;
  },

  async createPermanentMemory(data: {
    content: string;
    importance?: number;
    tags?: string[];
    metadata?: Record<string, unknown>;
  }) {
    const response = await apiClient.post('/api/memories/permanent', data);
    return response.data;
  },

  async updatePermanentMemory(
    id: number,
    data: Partial<{
      content: string;
      importance: number;
      tags: string[];
      metadata: Record<string, unknown>;
    }>
  ) {
    const response = await apiClient.put(`/api/memories/permanent/${id}`, data);
    return response.data;
  },

  async deletePermanentMemory(id: number) {
    const response = await apiClient.delete(`/api/memories/permanent/${id}`);
    return response.data;
  },

  async searchMemories(
    query: string,
    options?: {
      type?: string;
      limit?: number;
    }
  ) {
    const response = await apiClient.post('/api/memories/search', {
      query,
      ...options,
    });
    return response.data;
  },

  async semanticSearch(
    query: string,
    options?: {
      limit?: number;
      min_score?: number;
    }
  ) {
    const response = await apiClient.post('/api/memories/semantic-search', {
      query,
      ...options,
    });
    return response.data;
  },

  // Archive
  async getArchiveStats() {
    const response = await apiClient.get('/api/archive/stats');
    return response.data;
  },

  async getArchivedMemories(params?: { limit?: number; offset?: number; agent_id?: string }) {
    const response = await apiClient.get('/api/archive/list', { params });
    return response.data;
  },

  async restoreMemory(memoryId: number, agentId?: string) {
    const response = await apiClient.post('/api/memories/batch/restore', {
      ids: [memoryId],
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async archiveMemory(memoryId: number, targetLevel: number = 1) {
    const response = await apiClient.post('/api/archive/memory', {
      memory_id: memoryId,
      target_level: targetLevel,
    });
    return response.data;
  },

  async mergeMemories(memoryIds: number[]) {
    const response = await apiClient.post('/api/archive/merge', {
      memory_ids: memoryIds,
    });
    return response.data;
  },

  async detectDuplicates() {
    const response = await apiClient.post('/api/archive/deduplicate');
    return response.data;
  },

  async autoArchiveProcess() {
    const response = await apiClient.post('/api/archive/auto-process');
    return response.data;
  },

  // Memory Chat
  async memoryChat(message: string, sessionId: string = 'default') {
    const response = await apiClient.post('/api/memory-chat', {
      message,
      session_id: sessionId,
    });
    return response.data;
  },

  // Batch Memory Operations
  async batchDeleteMemories(ids: number[], agentId?: string) {
    const response = await apiClient.post('/api/memories/batch/delete', {
      ids,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async batchUpdateTags(
    ids: number[],
    tags: string[],
    operation: 'add' | 'remove' | 'set' = 'add',
    agentId?: string
  ) {
    const response = await apiClient.post('/api/memories/batch/tags', {
      ids,
      tags,
      operation,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async batchArchiveMemories(ids: number[], agentId?: string) {
    const response = await apiClient.post('/api/memories/batch/archive', {
      ids,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async batchRestoreMemories(ids: number[], agentId?: string) {
    const response = await apiClient.post('/api/memories/batch/restore', {
      ids,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async batchUpdateMemories(
    ids: number[],
    data: { content?: string; tags?: string[]; importance?: number },
    agentId?: string
  ) {
    const response = await apiClient.post('/api/memories/batch/update', {
      ids,
      data,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async batchTagByQuery(
    query: string,
    tags: string[],
    operation: 'add' | 'remove' | 'set' = 'add',
    agentId?: string
  ) {
    const response = await apiClient.post('/api/memories/batch/tag-by-query', {
      query,
      tags,
      operation,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async batchDeleteByQuery(query: string, agentId?: string) {
    const response = await apiClient.post('/api/memories/batch/delete-by-query', {
      query,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async batchArchiveByQuery(query: string, targetLevel: number = 1, agentId?: string) {
    const response = await apiClient.post('/api/memories/batch/archive-by-query', {
      query,
      target_level: targetLevel,
      agent_id: agentId || 'default',
    });
    return response.data;
  },

  async getMemoriesByType(type: string, params?: { limit?: number; workspace_id?: string }) {
    const response = await apiClient.get(`/api/memories/type/${type}`, { params });
    return response.data;
  },

  async searchByTag(tag: string, params?: { limit?: number; workspace_id?: string }) {
    const response = await apiClient.get('/api/memories/search-by-tag', {
      params: { tag, ...params },
    });
    return response.data;
  },

  // Diary
  async getDiaryEntries(params?: { limit?: number; agent_id?: string; workspace_id?: string }) {
    const response = await apiClient.get('/api/memories/diary', {
      params: {
        limit: params?.limit ?? 100,
        agent_id: params?.agent_id ?? 'default',
        workspace_id: params?.workspace_id ?? 'default',
      },
    });
    return response.data;
  },
};
