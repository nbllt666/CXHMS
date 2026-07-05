import { apiClient } from './client';

// ========== CXFC APIs ==========
// 从 client.ts 拆分：CXFC 插件注册/心跳/发现/技能/连接/断开。

export const cxfcApi = {
  async registerCXFCPlugin(data: { name: string; version: string; description?: string; capabilities?: string[] }) {
    const response = await apiClient.post('/api/cxfc/register', data);
    return response.data;
  },

  async cxfcHeartbeat(pluginId: string) {
    const response = await apiClient.post('/api/cxfc/heartbeat', { plugin_id: pluginId });
    return response.data;
  },

  async cxfcDiscover() {
    const response = await apiClient.get('/api/cxfc/discover');
    return response.data;
  },

  async cxfcSkills(pluginId?: string) {
    const response = await apiClient.get('/api/cxfc/skills', { params: { plugin_id: pluginId } });
    return response.data;
  },

  async cxfcConnect(host: string, port: number) {
    const response = await apiClient.post('/api/cxfc/connect', { host, port });
    return response.data;
  },

  async cxfcDisconnect(pluginId: string) {
    const response = await apiClient.delete(`/api/cxfc/plugins/${pluginId}`);
    return response.data;
  },
};
