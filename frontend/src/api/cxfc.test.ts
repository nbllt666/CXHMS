// ========== cxfcApi 单元测试 ==========
// G6: 覆盖 CXFC 插件注册/心跳/发现/技能/连接/断开。
// B9 回归契约：写操作（register/heartbeat/connect/disconnect）使用 POST/DELETE。

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

import { cxfcApi } from './cxfc';

describe('cxfcApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('Plugin registration & heartbeat', () => {
    it('registerCXFCPlugin → POST /api/cxfc/register with payload', async () => {
      const data = { id: 'p1', status: 'registered' };
      mocks.post.mockResolvedValueOnce({ data });
      const payload = {
        name: 'my-plugin',
        version: '1.0.0',
        description: 'desc',
        capabilities: ['search'],
      };
      const result = await cxfcApi.registerCXFCPlugin(payload);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/cxfc/register', payload);
    });

    it('cxfcHeartbeat → POST /api/cxfc/heartbeat with plugin_id', async () => {
      const data = { status: 'ok' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await cxfcApi.cxfcHeartbeat('p1');
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/cxfc/heartbeat', { plugin_id: 'p1' });
    });
  });

  describe('Discovery & skills', () => {
    it('cxfcDiscover → GET /api/cxfc/discover', async () => {
      const data = [{ id: 'p1', name: 'plugin' }];
      mocks.get.mockResolvedValueOnce({ data });
      const result = await cxfcApi.cxfcDiscover();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/cxfc/discover');
    });

    it('cxfcSkills with pluginId → GET /api/cxfc/skills with params', async () => {
      const data = [{ name: 'skill1' }];
      mocks.get.mockResolvedValueOnce({ data });
      const result = await cxfcApi.cxfcSkills('p1');
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/cxfc/skills', { params: { plugin_id: 'p1' } });
    });

    it('cxfcSkills without pluginId → params.plugin_id undefined', async () => {
      mocks.get.mockResolvedValueOnce({ data: [] });
      await cxfcApi.cxfcSkills();
      expect(mocks.get).toHaveBeenCalledWith('/api/cxfc/skills', { params: { plugin_id: undefined } });
    });
  });

  describe('Connect & disconnect', () => {
    it('cxfcConnect → POST /api/cxfc/connect with host + port', async () => {
      const data = { id: 'c1', connected: true };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await cxfcApi.cxfcConnect('localhost', 8080);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/cxfc/connect', { host: 'localhost', port: 8080 });
    });

    it('cxfcDisconnect → DELETE /api/cxfc/plugins/{id}', async () => {
      mocks.del.mockResolvedValueOnce({ data: { success: true } });
      const result = await cxfcApi.cxfcDisconnect('p1');
      expect(result).toEqual({ success: true });
      expect(mocks.del).toHaveBeenCalledWith('/api/cxfc/plugins/p1');
    });
  });
});
