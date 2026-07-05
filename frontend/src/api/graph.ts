import { apiClient } from './client';

// ========== Graph Database APIs ==========
// 从 client.ts 拆分：图节点/边/遍历/算法/导出。

export const graphApi = {
  async createNode(data: { type: string; properties?: Record<string, unknown>; text_content?: string }, agentId: string = 'default') {
    const response = await apiClient.post('/api/nodes', { ...data, agent_id: agentId });
    return response.data;
  },

  async getNodes(params?: { node_type?: string; limit?: number; offset?: number; agent_id?: string }) {
    const response = await apiClient.get('/api/nodes/search', { params });
    return response.data;
  },

  async getNode(nodeId: string, agentId: string = 'default') {
    const response = await apiClient.get(`/api/nodes/${nodeId}`, { params: { agent_id: agentId } });
    return response.data;
  },

  async updateNode(nodeId: string, data: { type?: string; properties?: Record<string, unknown>; text_content?: string }, agentId: string = 'default') {
    const response = await apiClient.put(`/api/nodes/${nodeId}`, { ...data, agent_id: agentId });
    return response.data;
  },

  async deleteNode(nodeId: string, cascade: boolean = true, agentId: string = 'default') {
    const response = await apiClient.delete(`/api/nodes/${nodeId}`, { params: { cascade, agent_id: agentId } });
    return response.data;
  },

  async createEdge(data: { source_id: string; target_id: string; relation_type: string; properties?: Record<string, unknown>; text_content?: string }, agentId: string = 'default') {
    const response = await apiClient.post('/api/edges', { ...data, agent_id: agentId });
    return response.data;
  },

  async getEdges(params?: { relation_type?: string; source_id?: string; target_id?: string; limit?: number; offset?: number; agent_id?: string }) {
    const response = await apiClient.get('/api/edges/search', { params });
    return response.data;
  },

  async deleteEdge(edgeId: string, agentId: string = 'default') {
    const response = await apiClient.delete(`/api/edges/${edgeId}`, { params: { agent_id: agentId } });
    return response.data;
  },

  async getNodeNeighbors(nodeId: string, params?: { max_depth?: number; direction?: string; agent_id?: string }) {
    const response = await apiClient.get(`/api/nodes/${nodeId}/neighbors`, { params });
    return response.data;
  },

  async traverseBFS(data: { start_id: string; max_depth?: number; node_type_filter?: string; agent_id?: string }) {
    const response = await apiClient.post('/api/traverse/bfs', data);
    return response.data;
  },

  async traverseDFS(data: { start_id: string; max_depth?: number; node_type_filter?: string; agent_id?: string }) {
    const response = await apiClient.post('/api/traverse/dfs', data);
    return response.data;
  },

  async getShortestPath(params: { start_id: string; end_id: string; max_length?: number; agent_id?: string }) {
    const response = await apiClient.get('/api/paths/shortest', { params });
    return response.data;
  },

  async graphSemanticSearch(data: { query: string; node_type?: string; limit?: number; agent_id?: string }) {
    const response = await apiClient.post('/api/semantic/search', data);
    return response.data;
  },

  async graphHybridSearch(data: { query: string; node_type?: string; properties_filter?: Record<string, unknown>; limit?: number; agent_id?: string }) {
    const response = await apiClient.post('/api/semantic/hybrid', data);
    return response.data;
  },

  async getGraphStats(agentId: string = 'default') {
    const response = await apiClient.get('/api/stats', { params: { agent_id: agentId } });
    return response.data;
  },

  async getGraphHealth(agentId: string = 'default') {
    const response = await apiClient.get('/api/health', { params: { agent_id: agentId } });
    return response.data;
  },

  async getImportantNodes(params?: { limit?: number; agent_id?: string }) {
    const response = await apiClient.get('/api/algorithm/important-nodes', { params });
    return response.data;
  },

  async pageRank(params?: { damping?: number; max_iterations?: number; agent_id?: string }) {
    const response = await apiClient.get('/api/algorithm/pagerank', { params });
    return response.data;
  },

  async detectCommunities(params?: { method?: string; agent_id?: string }) {
    const response = await apiClient.get('/api/algorithm/communities', { params });
    return response.data;
  },

  async exportGraph(format: string = 'json', agentId: string = 'default') {
    const response = await apiClient.get(`/api/export/${format}`, { params: { agent_id: agentId } });
    return response.data;
  },
};
