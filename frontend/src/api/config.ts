import { apiClient } from './client';

// ========== Config / Service / Models APIs ==========
// 从 client.ts 拆分：服务配置、统一配置、配置分区、可用模型。

export const configApi = {
  // Service Config (used by vector/llm settings sections)
  async getServiceConfig() {
    const response = await apiClient.get('/api/service/config');
    return response.data;
  },

  async updateServiceConfig(config: Record<string, unknown>) {
    const response = await apiClient.post('/api/service/config', config);
    return response.data;
  },

  // Models
  async getAvailableModels() {
    const response = await apiClient.get('/api/service/models');
    return response.data;
  },

  // Unified Config
  async getConfig() {
    const response = await apiClient.get('/api/config');
    return response.data;
  },

  async setConfig(data: Record<string, unknown>) {
    const response = await apiClient.put('/api/config', data);
    return response.data;
  },

  async getConfigSection(section: string) {
    const sectionEndpoints: Record<string, string> = {
      'vector': '/api/config/vector',
      'graph': '/api/config/graph',
      'cxfc': '/api/config/cxfc',
      'llm': '/api/config',
    };
    const endpoint = sectionEndpoints[section] || '/api/config';
    const response = await apiClient.get(endpoint);
    return response.data;
  },

  async setConfigSection(section: string, data: Record<string, unknown>) {
    const response = await apiClient.put('/api/config', { section, data });
    return response.data;
  },
};
