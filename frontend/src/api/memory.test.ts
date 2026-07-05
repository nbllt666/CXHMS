// ========== memoryApi 单元测试 ==========
// G6: 覆盖记忆 CRUD / 永久记忆 / 归档 / 批量 / 记忆聊天 / 日记。
// B9 回归契约：写操作（createMemory/updateMemory/deleteMemory/search 等）使用 POST/PUT/DELETE。

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

import { memoryApi } from './memory';

describe('memoryApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('Memories CRUD', () => {
    it('getMemories with params → GET /api/memories', async () => {
      const data = { memories: [{ id: 1, content: 'm' }], total: 1 };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await memoryApi.getMemories({ type: 'long_term', limit: 10, offset: 0 });
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/memories', {
        params: { type: 'long_term', limit: 10, offset: 0 },
      });
    });

    it('createMemory → POST /api/memories with payload', async () => {
      const data = { id: 1, content: 'new' };
      mocks.post.mockResolvedValueOnce({ data });
      const payload = { content: 'new', type: 'long_term', importance: 4, tags: ['t1'] };
      const result = await memoryApi.createMemory(payload);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/memories', payload);
    });

    it('updateMemory → PUT /api/memories/{id} with agent_id injected', async () => {
      const data = { id: 1, content: 'updated' };
      mocks.put.mockResolvedValueOnce({ data });
      const result = await memoryApi.updateMemory(1, { content: 'updated' }, 'agent-1');
      expect(result).toEqual(data);
      expect(mocks.put).toHaveBeenCalledWith('/api/memories/1', {
        content: 'updated',
        agent_id: 'agent-1',
      });
    });

    it('updateMemory defaults agent_id to "default"', async () => {
      mocks.put.mockResolvedValueOnce({ data: {} });
      await memoryApi.updateMemory(1, { content: 'x' });
      expect(mocks.put).toHaveBeenCalledWith('/api/memories/1', {
        content: 'x',
        agent_id: 'default',
      });
    });

    it('deleteMemory → DELETE /api/memories/{id} with soft_delete param', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await memoryApi.deleteMemory(1, false);
      expect(mocks.del).toHaveBeenCalledWith('/api/memories/1', { params: { soft_delete: false } });
    });

    it('deleteMemory defaults to soft_delete=false (hard delete)', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await memoryApi.deleteMemory(1);
      expect(mocks.del).toHaveBeenCalledWith('/api/memories/1', { params: { soft_delete: false } });
    });
  });

  describe('Search', () => {
    it('searchMemories → POST /api/memories/search with query + options', async () => {
      const data = [{ id: 1, content: 'hit', score: 0.9 }];
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.searchMemories('q', { type: 'long_term', limit: 5 });
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/memories/search', {
        query: 'q',
        type: 'long_term',
        limit: 5,
      });
    });

    it('semanticSearch → POST /api/memories/semantic-search', async () => {
      const data = [{ id: 1, score: 0.95 }];
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.semanticSearch('q', { limit: 5, min_score: 0.8 });
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/memories/semantic-search', {
        query: 'q',
        limit: 5,
        min_score: 0.8,
      });
    });

    it('getMemoriesByType → GET /api/memories/type/{type}', async () => {
      mocks.get.mockResolvedValueOnce({ data: { memories: [] } });
      await memoryApi.getMemoriesByType('long_term', { limit: 10 });
      expect(mocks.get).toHaveBeenCalledWith('/api/memories/type/long_term', { params: { limit: 10 } });
    });

    it('searchByTag → GET /api/memories/search-by-tag with tag param', async () => {
      mocks.get.mockResolvedValueOnce({ data: { memories: [] } });
      await memoryApi.searchByTag('important', { limit: 10 });
      expect(mocks.get).toHaveBeenCalledWith('/api/memories/search-by-tag', {
        params: { tag: 'important', limit: 10 },
      });
    });
  });

  describe('Archive', () => {
    it('archiveMemory → POST /api/archive/memory', async () => {
      const data = { success: true, memory_id: 1, level: 2 };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.archiveMemory(1, 2);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/archive/memory', {
        memory_id: 1,
        target_level: 2,
      });
    });

    it('detectDuplicates → POST /api/archive/deduplicate', async () => {
      const data = { duplicates_found: 3, groups: [] };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.detectDuplicates();
      expect(result.duplicates_found).toBe(3);
      expect(mocks.post).toHaveBeenCalledWith('/api/archive/deduplicate');
    });

    it('autoArchiveProcess → POST /api/archive/auto-process', async () => {
      const data = { processed: 20, archived: 15 };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.autoArchiveProcess();
      expect(result).toEqual(data);
    });
  });

  describe('Batch operations', () => {
    it('batchDeleteMemories → POST /api/memories/batch/delete with agent_id', async () => {
      const data = { success: true, deleted: 3 };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.batchDeleteMemories([1, 2, 3], 'agent-1');
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/memories/batch/delete', {
        ids: [1, 2, 3],
        agent_id: 'agent-1',
      });
    });

    it('batchUpdateTags → POST /api/memories/batch/tags with operation', async () => {
      const data = { success: true, updated: 5 };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.batchUpdateTags([1, 2], ['t1'], 'add', 'agent-1');
      expect(result.updated).toBe(5);
      expect(mocks.post).toHaveBeenCalledWith('/api/memories/batch/tags', {
        ids: [1, 2],
        tags: ['t1'],
        operation: 'add',
        agent_id: 'agent-1',
      });
    });
  });

  describe('Memory chat', () => {
    it('memoryChat → POST /api/memory-chat', async () => {
      const data = { response: 'mem agent resp', session_id: 's1' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await memoryApi.memoryChat('what?', 's1');
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/memory-chat', {
        message: 'what?',
        session_id: 's1',
      });
    });

    it('memoryChat defaults session to "default"', async () => {
      mocks.post.mockResolvedValueOnce({ data: {} });
      await memoryApi.memoryChat('hi');
      expect(mocks.post).toHaveBeenCalledWith('/api/memory-chat', {
        message: 'hi',
        session_id: 'default',
      });
    });
  });
});
