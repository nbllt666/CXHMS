import axios, { AxiosInstance, AxiosError, AxiosResponse } from 'axios';
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios';

// ========== API client 基础设施 ==========
// 本文件仅保留 axios 实例、interceptors（含重试）与通用健康/状态/地址方法。
// 业务域方法已按域拆分至 memory.ts / chat.ts / agent.ts / graph.ts / vector.ts / cxfc.ts / config.ts，
// 并通过 ./index 聚合为 `api` 对象以保持向后兼容。
// LRU cache 已移除，统一交 React Query 管理。

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';
const CONTROL_SERVICE_URL = import.meta.env.VITE_CONTROL_SERVICE_URL || 'http://localhost:8765';

// 动态获取当前 API URL（优先 localStorage 保存的地址）
const getCurrentApiUrl = () => localStorage.getItem('cxhms-api-url') || API_BASE_URL;
const getCurrentControlUrl = () => localStorage.getItem('cxhms-control-url') || CONTROL_SERVICE_URL;

interface RetryConfig extends InternalAxiosRequestConfig {
  retryCount?: number;
}

// 重试参数（模块级常量，替代原 class 私有字段）
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;
const MAX_RETRY_DELAY = 30000;

function setupInterceptors(axiosInstance: AxiosInstance) {
  axiosInstance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = localStorage.getItem('cxhms-token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error: AxiosError) => Promise.reject(error)
  );

  axiosInstance.interceptors.response.use(
    (response: AxiosResponse) => response,
    async (error: AxiosError) => {
      if (error.response?.status === 401) {
        localStorage.removeItem('cxhms-token');
        console.warn('Authentication required. Redirecting to home page.');
        window.location.href = '/';
        return Promise.reject(error);
      }

      if (error.response?.status === 503) {
        return Promise.reject(error);
      }

      const config = error.config as RetryConfig | undefined;
      if (!config || !config.retryCount) {
        if (config) config.retryCount = 0;
      }

      // B9: 写操作（POST/PUT/DELETE/PATCH）禁用自动重试，避免重复写入。
      // 仅 GET（及默认/未知方法）保留指数退避重试。
      const writeMethods = ['post', 'put', 'delete', 'patch'];
      const method = (config?.method || 'get').toLowerCase();
      if (writeMethods.includes(method)) {
        return Promise.reject(error);
      }

      if (config && config.retryCount !== undefined && config.retryCount < MAX_RETRIES) {
        config.retryCount += 1;
        const delay = Math.min(RETRY_DELAY * Math.pow(2, config.retryCount - 1), MAX_RETRY_DELAY);
        await new Promise((resolve) => setTimeout(resolve, delay));
        return axiosInstance.request(config as AxiosRequestConfig);
      }

      return Promise.reject(error);
    }
  );
}

// 主后端 axios 实例（Port 8001）
export const apiClient: AxiosInstance = axios.create({
  baseURL: getCurrentApiUrl(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Control service axios 实例（Port 8765，已停用但保留兼容）
export const controlClient: AxiosInstance = axios.create({
  baseURL: getCurrentControlUrl(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

setupInterceptors(apiClient);
setupInterceptors(controlClient);

// ========== 通用 API（健康 / 状态 / 地址管理） ==========
export const commonApi = {
  // Control Service health
  async getControlServiceHealth() {
    const response = await controlClient.get('/health');
    return response.data;
  },

  // Get main backend status via health check (control service removed)
  async getMainBackendStatus() {
    const response = await apiClient.get('/health');
    return { running: response.data.status === 'healthy' || response.data.status === 'degraded', ...response.data };
  },

  // Start/stop/restart methods removed - control service no longer exists
  async startMainBackend() {
    throw new Error('Control service removed - start manually');
  },

  async stopMainBackend() {
    throw new Error('Control service removed - stop manually');
  },

  async restartMainBackend() {
    throw new Error('Control service removed - restart manually');
  },

  // Admin / Health
  async getHealth() {
    const response = await apiClient.get('/health');
    return response.data;
  },

  async getAdminStats() {
    const response = await apiClient.get('/api/admin/stats');
    return response.data;
  },

  // Stats（全局；按 agent 的图统计见 graphApi.getGraphStats）
  async getStats() {
    const response = await apiClient.get('/api/stats');
    return response.data;
  },

  /** 检查后端连接是否可用 */
  async checkHealth(apiUrl?: string): Promise<boolean> {
    try {
      const url = apiUrl || apiClient.defaults.baseURL;
      const response = await axios.get(`${url}/health`, { timeout: 5000 });
      return response.status === 200;
    } catch {
      return false;
    }
  },

  /** 动态修改后端地址 */
  setBaseUrls(apiUrl: string, controlUrl?: string) {
    apiClient.defaults.baseURL = apiUrl;
    if (controlUrl) {
      controlClient.defaults.baseURL = controlUrl;
    }
    localStorage.setItem('cxhms-api-url', apiUrl);
    if (controlUrl) {
      localStorage.setItem('cxhms-control-url', controlUrl);
    }
  },

  /** 获取当前 API 地址 */
  getApiUrl(): string {
    return apiClient.defaults.baseURL || API_BASE_URL;
  },
};

export { API_BASE_URL, CONTROL_SERVICE_URL };
