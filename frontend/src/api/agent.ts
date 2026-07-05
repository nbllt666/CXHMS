import { apiClient } from './client';

// ========== Agent / Tools / ACP APIs ==========
// 从 client.ts 拆分：Agent 管理、工具管理、ACP Agent 管理。
// LRU cache 已移除，统一交 React Query。

// Type definitions（F8: 统一到 types/agent.ts，此处仅 re-export 保持向后兼容）
export type { Agent } from '../types/agent';

export const agentApi = {
  // ========== Chat Agent APIs ==========
  async getAgents() {
    const response = await apiClient.get('/api/agents');
    return response.data;
  },

  async getAgent(id: string) {
    const response = await apiClient.get(`/api/agents/${id}`);
    return response.data;
  },

  async createAgent(data: {
    name: string;
    description?: string;
    system_prompt?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number;
    use_memory?: boolean;
    use_tools?: boolean;
    vision_enabled?: boolean;
    memory_scene?: string;
  }) {
    const response = await apiClient.post('/api/agents', data);
    return response.data;
  },

  async updateAgent(
    id: string,
    data: Partial<{
      name: string;
      description: string;
      system_prompt: string;
      model: string;
      temperature: number;
      max_tokens: number;
      use_memory: boolean;
      use_tools: boolean;
      vision_enabled: boolean;
      memory_scene: string;
    }>
  ) {
    const response = await apiClient.put(`/api/agents/${id}`, data);
    return response.data;
  },

  async deleteAgent(id: string) {
    const response = await apiClient.delete(`/api/agents/${id}`);
    return response.data;
  },

  async cloneAgent(id: string) {
    const response = await apiClient.post(`/api/agents/${id}/clone`);
    return response.data;
  },

  // ========== Tools APIs ==========
  async getToolsStats() {
    const response = await apiClient.get('/api/tools/stats');
    return response.data;
  },

  async getTools(type?: string) {
    const params: Record<string, string> = {};
    // type 参数映射到 category
    if (type && type !== 'all' && type !== 'builtin') {
      params['category'] = type;
    }
    if (type === 'builtin') {
      params['include_builtin'] = 'true';
    }
    const response = await apiClient.get('/api/tools', { params });
    return response.data;
  },

  async createTool(data: {
    name: string;
    description?: string;
    type: 'mcp' | 'native' | 'custom';
    icon?: string;
    config?: Record<string, unknown>;
  }) {
    const response = await apiClient.post('/api/tools', data);
    return response.data;
  },

  async updateTool(
    id: string,
    data: Partial<{
      name: string;
      description: string;
      type: 'mcp' | 'native' | 'custom';
      icon: string;
      config: Record<string, unknown>;
      status: 'active' | 'inactive';
    }>
  ) {
    // G4 对齐：后端补了 PUT /api/tools/{name} update_tool 端点（对齐 interface_stub 契约）。
    // 字段映射：status→enabled, config→parameters, type/icon 后端不支持更新（忽略）。
    // 注意：后端按 name 索引，不支持重命名——data.name 仅用于调用方语义，不发送给后端。
    const { name: _name, type: _type, icon: _icon, status, config, ...rest } = data;
    const payload: Record<string, unknown> = { ...rest };
    if (status !== undefined) {
      payload.enabled = status === 'active';
    }
    if (config !== undefined) {
      payload.parameters = config;
    }
    const response = await apiClient.put(`/api/tools/${id}`, payload);
    return response.data;
  },

  // Note: `id` parameter is actually the tool name, not a numeric id
  async deleteTool(id: string) {
    const response = await apiClient.delete(`/api/tools/${id}`);
    return response.data;
  },

  async testTool(id: string, params: Record<string, unknown>) {
    const response = await apiClient.post(`/api/tools/${id}/test`, params);
    return response.data;
  },

  // ========== ACP APIs ==========
  async getAcpStats() {
    const response = await apiClient.get('/api/acp/stats');
    return response.data;
  },

  async getAcpAgents() {
    const response = await apiClient.get('/api/acp/agents');
    return response.data;
  },

  async createAcpAgent(data: {
    agent_id: string;
    host: string;
    port: number;
  }) {
    const response = await apiClient.post('/api/acp/connect', data);
    return response.data;
  },

  async updateAcpAgent(
    id?: string,
    data?: Partial<{
      name: string;
      description: string;
      capabilities: string[];
      status: 'active' | 'inactive';
    }>
  ) {
    // 后端无更新 ACP agent 的端点。抛错让调用方（如 React Query onError）能感知失败，
    // 避免静默返回 {status:'error'} 导致 UI 误报更新成功。
    // 将 data 纳入错误信息：既满足 noUnusedParameters 约束，又便于调用方诊断传入内容。
    throw new Error(
      `更新 ACP agent 不被支持（后端无对应端点）: id=${id ?? '(空)'}, data=${
        data ? JSON.stringify(data) : '(空)'
      }`
    );
  },

  async deleteAcpAgent(id: string) {
    const response = await apiClient.delete(`/api/acp/connect/${id}`);
    return response.data;
  },
};
