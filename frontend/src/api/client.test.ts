// ========== client.ts 单元测试 ==========
// G6 观察项 4 处置：拆分后仅覆盖 client.ts 暴露的 commonApi 与 axios 基础设施。
// 其他域（Chat/Agent/Memory/ACP/Tools/Archive/Batch/Memory Chat）已由对应 .test.ts 文件覆盖，
// 不再在本文件重复。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      put: mockPut,
      delete: mockDelete,
      defaults: { baseURL: 'http://localhost:8001' },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    })),
    // 用于 checkHealth 的 axios.get 直调
    get: vi.fn(),
  },
}));

describe('commonApi (client.ts)', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let api: any;

  beforeEach(async () => {
    vi.resetModules();
    mockGet.mockReset();
    mockPost.mockReset();
    mockPut.mockReset();
    mockDelete.mockReset();
    localStorage.clear();

    api = await import('./index').then((m) => m.api);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Health Check', () => {
    it('getHealth → GET /health', async () => {
      const mockResponse = { status: 'healthy', service: 'CXHMS' };
      mockGet.mockResolvedValueOnce({ data: mockResponse });

      const result = await api.getHealth();
      expect(result).toEqual(mockResponse);
      expect(mockGet).toHaveBeenCalledWith('/health');
    });
  });

  describe('Control Service API', () => {
    it('getControlServiceHealth → controlClient GET /health', async () => {
      const mockHealth = { status: 'healthy', service: 'control' };
      mockGet.mockResolvedValueOnce({ data: mockHealth });

      const result = await api.getControlServiceHealth();
      expect(result.status).toBe('healthy');
    });

    it('getMainBackendStatus → GET /health and map running flag', async () => {
      const mockStatus = { status: 'healthy', uptime: 7200 };
      mockGet.mockResolvedValueOnce({ data: mockStatus });

      const result = await api.getMainBackendStatus();
      expect(result.running).toBe(true);
    });

    it('getMainBackendStatus maps degraded to running=true', async () => {
      mockGet.mockResolvedValueOnce({ data: { status: 'degraded' } });
      const result = await api.getMainBackendStatus();
      expect(result.running).toBe(true);
    });

    it('startMainBackend throws (control service removed)', async () => {
      await expect(api.startMainBackend()).rejects.toThrow(/Control service removed/);
    });

    it('stopMainBackend throws (control service removed)', async () => {
      await expect(api.stopMainBackend()).rejects.toThrow(/Control service removed/);
    });

    it('restartMainBackend throws (control service removed)', async () => {
      await expect(api.restartMainBackend()).rejects.toThrow(/Control service removed/);
    });
  });

  describe('Admin API', () => {
    it('getAdminStats → GET /api/admin/stats', async () => {
      const mockStats = { total_memories: 100, total_sessions: 50 };
      mockGet.mockResolvedValueOnce({ data: mockStats });

      const result = await api.getAdminStats();
      expect(result.total_memories).toBe(100);
      expect(mockGet).toHaveBeenCalledWith('/api/admin/stats');
    });

    it('getStats → GET /api/stats', async () => {
      const mockStats = { memories: 100, agents: 5 };
      mockGet.mockResolvedValueOnce({ data: mockStats });

      const result = await api.getStats();
      expect(result).toEqual(mockStats);
      expect(mockGet).toHaveBeenCalledWith('/api/stats');
    });
  });

  describe('Base URL Management', () => {
    it('setBaseUrls updates apiClient.defaults.baseURL', () => {
      const newUrl = 'http://new-api:9999';
      api.setBaseUrls(newUrl, 'http://new-control:8888');
      expect(api.getApiUrl()).toBe(newUrl);
    });

    it('setBaseUrls without controlUrl still updates api URL', () => {
      api.setBaseUrls('http://new-api-only:9999');
      expect(api.getApiUrl()).toBe('http://new-api-only:9999');
    });

    it('getApiUrl returns non-empty string by default', () => {
      const url = api.getApiUrl();
      expect(typeof url).toBe('string');
      expect(url.length).toBeGreaterThan(0);
    });
  });

  describe('checkHealth', () => {
    it('checkHealth returns true when GET /health returns 200', async () => {
      const axios = (await import('axios')).default;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (axios as any).get.mockResolvedValueOnce({ status: 200 });

      const result = await api.checkHealth('http://test:8001');
      expect(result).toBe(true);
    });

    it('checkHealth returns false on network error', async () => {
      const axios = (await import('axios')).default;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (axios as any).get.mockRejectedValueOnce(new Error('Network Error'));

      const result = await api.checkHealth('http://test:8001');
      expect(result).toBe(false);
    });
  });

  describe('Error Handling', () => {
    it('getHealth propagates network error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network Error'));
      await expect(api.getHealth()).rejects.toThrow('Network Error');
    });

    it('getAdminStats propagates 404 error', async () => {
      const error = new Error('Not Found') as Error & { response: { status: number } };
      error.response = { status: 404 };
      mockGet.mockRejectedValueOnce(error);
      await expect(api.getAdminStats()).rejects.toThrow();
    });

    it('getMainBackendStatus propagates 500 error', async () => {
      const error = new Error('Internal Server Error') as Error & {
        response: { status: number };
      };
      error.response = { status: 500 };
      mockGet.mockRejectedValueOnce(error);
      await expect(api.getMainBackendStatus()).rejects.toThrow();
    });
  });

  // B9 回归契约：写操作（POST/PUT/DELETE/PATCH）失败时不重试，避免重复写入。
  // spec B9 要求：写操作禁用自动重试；仅 GET 保留指数退避。
  // client.ts interceptor 按 config.method 区分，写方法直接 reject 不进入重试循环。
  describe('B9 contract: write operations do not retry', () => {
    it('POST failure does not retry (no duplicate writes)', async () => {
      const { apiClient } = await import('./client');
      mockPost.mockRejectedValue(new Error('Server Error'));
      await expect(apiClient.post('/test', {})).rejects.toThrow('Server Error');
      // 等待潜在重试窗口（若误重试，此处会让 mockPost 被多次调用）
      await new Promise((resolve) => setTimeout(resolve, 100));
      expect(mockPost).toHaveBeenCalledTimes(1);
    });

    it('PUT failure does not retry', async () => {
      const { apiClient } = await import('./client');
      mockPut.mockRejectedValue(new Error('Server Error'));
      await expect(apiClient.put('/test', {})).rejects.toThrow('Server Error');
      await new Promise((resolve) => setTimeout(resolve, 100));
      expect(mockPut).toHaveBeenCalledTimes(1);
    });

    it('DELETE failure does not retry', async () => {
      const { apiClient } = await import('./client');
      mockDelete.mockRejectedValue(new Error('Server Error'));
      await expect(apiClient.delete('/test')).rejects.toThrow('Server Error');
      await new Promise((resolve) => setTimeout(resolve, 100));
      expect(mockDelete).toHaveBeenCalledTimes(1);
    });

    it('401 triggers redirect (no retry, write or read)', async () => {
      const { apiClient } = await import('./client');
      const originalHref = window.location.href;
      const error401 = new Error('Unauthorized') as Error & {
        response: { status: number };
      };
      error401.response = { status: 401 };
      mockPost.mockRejectedValue(error401);
      await expect(apiClient.post('/test', {})).rejects.toThrow();
      expect(mockPost).toHaveBeenCalledTimes(1);
      // 还原 href 避免污染后续测试
      Object.defineProperty(window, 'location', {
        value: { href: originalHref },
        writable: true,
      });
    });

    it('503 service unavailable does not retry', async () => {
      const { apiClient } = await import('./client');
      const error503 = new Error('Service Unavailable') as Error & {
        response: { status: number };
      };
      error503.response = { status: 503 };
      mockPost.mockRejectedValue(error503);
      await expect(apiClient.post('/test', {})).rejects.toThrow();
      expect(mockPost).toHaveBeenCalledTimes(1);
    });
  });
});
