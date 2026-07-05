import { apiClient } from './client';

// ========== Vector Database APIs ==========
// 从 client.ts 拆分：向量库配置/状态/健康/同步/重建/搜索/统计。

export const vectorApi = {
  async getVectorConfig() {
    const response = await apiClient.get('/api/vector/config');
    return response.data;
  },

  async getVectorStatus() {
    const response = await apiClient.get('/api/vector/status');
    return response.data;
  },

  async getVectorHealth() {
    const response = await apiClient.get('/api/vector/health');
    return response.data;
  },

  async vectorSync() {
    const response = await apiClient.post('/api/vector/sync');
    return response.data;
  },

  async vectorRebuild() {
    const response = await apiClient.post('/api/vector/rebuild');
    return response.data;
  },

  async vectorSearch(data: { query: string; limit?: number }) {
    const response = await apiClient.post('/api/vector/search', data);
    return response.data;
  },

  async getVectorStats() {
    const response = await apiClient.get('/api/vector/stats');
    return response.data;
  },
};
