// ========== vectorApi 单元测试 ==========
// G6: 覆盖向量库配置/状态/健康/同步/重建/搜索/统计。
// B9 回归契约：写操作（vectorSync/vectorRebuild/vectorSearch）使用 POST。

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

import { vectorApi } from './vector';

describe('vectorApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('Read operations (GET)', () => {
    it('getVectorConfig → GET /api/vector/config', async () => {
      const data = { provider: 'chroma' };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await vectorApi.getVectorConfig();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/vector/config');
    });

    it('getVectorStatus → GET /api/vector/status', async () => {
      const data = { status: 'ready' };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await vectorApi.getVectorStatus();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/vector/status');
    });

    it('getVectorHealth → GET /api/vector/health', async () => {
      const data = { healthy: true };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await vectorApi.getVectorHealth();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/vector/health');
    });

    it('getVectorStats → GET /api/vector/stats', async () => {
      const data = { total_vectors: 1000 };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await vectorApi.getVectorStats();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/vector/stats');
    });
  });

  describe('Write operations (POST)', () => {
    it('vectorSync → POST /api/vector/sync', async () => {
      const data = { success: true, synced: 50 };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await vectorApi.vectorSync();
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/vector/sync');
    });

    it('vectorRebuild → POST /api/vector/rebuild', async () => {
      const data = { success: true, rebuilt: 1000 };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await vectorApi.vectorRebuild();
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/vector/rebuild');
    });

    it('vectorSearch → POST /api/vector/search with query + limit', async () => {
      const data = [{ id: 'v1', score: 0.9 }];
      mocks.post.mockResolvedValueOnce({ data });
      const result = await vectorApi.vectorSearch({ query: 'find', limit: 5 });
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/vector/search', { query: 'find', limit: 5 });
    });

    it('vectorSearch without limit → POST with query only', async () => {
      mocks.post.mockResolvedValueOnce({ data: [] });
      await vectorApi.vectorSearch({ query: 'q' });
      expect(mocks.post).toHaveBeenCalledWith('/api/vector/search', { query: 'q' });
    });
  });
});
