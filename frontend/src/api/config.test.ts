// ========== configApi 单元测试 ==========
// G6: 覆盖服务配置/统一配置/配置分区/可用模型。
// B9 回归契约：写操作（updateServiceConfig/setConfig/setConfigSection）使用 POST/PUT。

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

import { configApi } from './config';

describe('configApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('Service config', () => {
    it('getServiceConfig → GET /api/service/config', async () => {
      const data = { llm: { model: 'gpt-4' } };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await configApi.getServiceConfig();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/service/config');
    });

    it('updateServiceConfig → POST /api/service/config', async () => {
      const data = { status: 'ok' };
      mocks.post.mockResolvedValueOnce({ data });
      const payload = { llm: { temperature: 0.5 } };
      const result = await configApi.updateServiceConfig(payload);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/service/config', payload);
    });

    it('getAvailableModels → GET /api/service/models', async () => {
      const data = [{ id: 'gpt-4', name: 'GPT-4' }];
      mocks.get.mockResolvedValueOnce({ data });
      const result = await configApi.getAvailableModels();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/service/models');
    });
  });

  describe('Unified config', () => {
    it('getConfig → GET /api/config', async () => {
      const data = { llm: {}, memory: {} };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await configApi.getConfig();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/config');
    });

    it('setConfig → PUT /api/config with data', async () => {
      const data = { status: 'ok' };
      mocks.put.mockResolvedValueOnce({ data });
      const payload = { llm: { model: 'gpt-4' } };
      const result = await configApi.setConfig(payload);
      expect(result).toEqual(data);
      expect(mocks.put).toHaveBeenCalledWith('/api/config', payload);
    });

    it('setConfigSection → PUT /api/config with section + data wrapper', async () => {
      mocks.put.mockResolvedValueOnce({ data: {} });
      await configApi.setConfigSection('vector', { host: 'localhost' });
      expect(mocks.put).toHaveBeenCalledWith('/api/config', {
        section: 'vector',
        data: { host: 'localhost' },
      });
    });
  });

  describe('Config sections', () => {
    it('getConfigSection("vector") → GET /api/config/vector', async () => {
      const data = { host: 'localhost' };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await configApi.getConfigSection('vector');
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/config/vector');
    });

    it('getConfigSection("graph") → GET /api/config/graph', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await configApi.getConfigSection('graph');
      expect(mocks.get).toHaveBeenCalledWith('/api/config/graph');
    });

    it('getConfigSection("cxfc") → GET /api/config/cxfc', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await configApi.getConfigSection('cxfc');
      expect(mocks.get).toHaveBeenCalledWith('/api/config/cxfc');
    });

    it('getConfigSection("llm") → falls back to GET /api/config', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await configApi.getConfigSection('llm');
      expect(mocks.get).toHaveBeenCalledWith('/api/config');
    });

    it('getConfigSection(unknown) → falls back to GET /api/config', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await configApi.getConfigSection('unknown-section');
      expect(mocks.get).toHaveBeenCalledWith('/api/config');
    });
  });
});
