import { apiClient } from './client';
import type {
  ConfigDiff,
  ReinitResponse,
  ReinitStatus,
  ConfigSaveResponse,
} from './client';

// ========== Config / Service / Models APIs ==========
// 从 client.ts 拆分：服务配置、统一配置、配置分区、可用模型。
// Task 9：新增配置重载与组件重新初始化方法（reload-config / reinit / reinit/status）。

export const configApi = {
  // Service Config (used by vector/llm settings sections)
  async getServiceConfig() {
    const response = await apiClient.get('/api/service/config');
    return response.data;
  },

  // Task 8.1：updateServiceConfig 现在返回带 diff/reinit_task_id 的结构（auto_reinit 默认 true）
  async updateServiceConfig(config: Record<string, unknown>): Promise<ConfigSaveResponse> {
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

  // ===== Task 9.1: POST /api/service/reload-config — 重载配置文件并返回差异 =====
  async reloadConfig(): Promise<{ status: string; diff: ConfigDiff }> {
    const response = await apiClient.post('/api/service/reload-config');
    return response.data;
  },

  // ===== Task 9.2: POST /api/service/reinit — 异步重新初始化组件 =====
  // 202 accepted | 409 conflict（已有任务执行中）
  // 注意：POST 写操作不走 axios 拦截器自动重试（B9 契约），409 在此手动捕获。
  async reinitComponents(components?: string[], reloadFirst?: boolean): Promise<ReinitResponse> {
    try {
      const response = await apiClient.post('/api/service/reinit', {
        components,
        reload_first: reloadFirst,
      });
      return response.data;
    } catch (error) {
      const axiosError = error as {
        response?: { status?: number; data?: { message?: string; current_component?: string } };
      };
      if (axiosError.response?.status === 409) {
        return {
          status: 'conflict',
          message: axiosError.response.data?.message,
          current_component: axiosError.response.data?.current_component,
        };
      }
      throw error;
    }
  },

  // ===== Task 9.3: GET /api/service/reinit/status — 查询重初始化任务状态 =====
  async getReinitStatus(): Promise<ReinitStatus> {
    const response = await apiClient.get('/api/service/reinit/status');
    return response.data;
  },
};
