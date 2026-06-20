import axios, { AxiosInstance, AxiosError, AxiosResponse } from 'axios';
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';
const CONTROL_SERVICE_URL = import.meta.env.VITE_CONTROL_SERVICE_URL || 'http://localhost:8765';

// 动态获取当前 API URL（优先 localStorage 保存的地址）
const getCurrentApiUrl = () => localStorage.getItem('cxhms-api-url') || API_BASE_URL;
const getCurrentControlUrl = () => localStorage.getItem('cxhms-control-url') || CONTROL_SERVICE_URL;

interface RetryConfig extends InternalAxiosRequestConfig {
  retryCount?: number;
}

// Type definitions
export interface Agent {
  id: string;
  name: string;
  description?: string;
  is_default?: boolean;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  system_prompt?: string;
  use_memory?: boolean;
  memory_scene?: string;
  tools?: string[];
  capabilities?: string[];
  decay_model?: string;
  use_tools?: boolean;
  vision_enabled?: boolean;
  created_at?: string;
  updated_at?: string;
}

class ApiClient {
  private client: AxiosInstance;
  private controlClient: AxiosInstance;
  private maxRetries: number = 3;
  private retryDelay: number = 1000;
  private maxRetryDelay: number = 30000;
  private maxCacheSize: number = 100;
  private cache: Map<string, { data: unknown; timestamp: number; ttl: number }>;

  constructor() {
    this.client = axios.create({
      baseURL: getCurrentApiUrl(),
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.controlClient = axios.create({
      baseURL: getCurrentControlUrl(),
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.cache = new Map();
    this._setupInterceptors(this.client);
    this._setupInterceptors(this.controlClient);
  }

  private _getCacheKey(url: string, params?: Record<string, unknown>): string {
    return `${url}?${JSON.stringify(params || {})}`;
  }

  private _getFromCache(key: string): unknown | null {
    const cached = this.cache.get(key);
    if (!cached) return null;

    if (Date.now() - cached.timestamp > cached.ttl) {
      this.cache.delete(key);
      return null;
    }

    return cached.data;
  }

  private _setCache(key: string, data: unknown, ttl: number = 60000): void {
    if (this.cache.size >= this.maxCacheSize) {
      const oldestKey = this.cache.keys().next().value;
      if (oldestKey !== undefined) {
        this.cache.delete(oldestKey);
      }
    }
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl,
    });
  }

  private _clearCache(pattern?: string): void {
    if (pattern) {
      for (const key of this.cache.keys()) {
        if (key.includes(pattern)) {
          this.cache.delete(key);
        }
      }
    } else {
      this.cache.clear();
    }
  }

  private _setupInterceptors(axiosInstance: AxiosInstance) {
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

        if (config && config.retryCount !== undefined && config.retryCount < this.maxRetries) {
          config.retryCount += 1;
          const delay = Math.min(this.retryDelay * Math.pow(2, config.retryCount - 1), this.maxRetryDelay);
          await new Promise((resolve) =>
            setTimeout(resolve, delay)
          );
          return axiosInstance.request(config as AxiosRequestConfig);
        }

        return Promise.reject(error);
      }
    );
  }

  // ========== Control Service APIs (Port 8765) ==========

  // Check control service health
  async getControlServiceHealth() {
    const response = await this.controlClient.get('/health');
    return response.data;
  }

  // Get main backend status via control service
  async getMainBackendStatus() {
    const response = await this.controlClient.get('/control/status');
    return response.data;
  }

  // Start main backend service
  async startMainBackend() {
    const response = await this.controlClient.post('/control/start');
    return response.data;
  }

  // Stop main backend service
  async stopMainBackend() {
    const response = await this.controlClient.post('/control/stop');
    return response.data;
  }

  // Restart main backend service
  async restartMainBackend() {
    const response = await this.controlClient.post('/control/restart');
    return response.data;
  }

  // ========== Main Backend APIs (Port 8000) ==========

  // Service Config (used by vector/llm settings sections)
  async getServiceConfig() {
    const response = await this.client.get('/api/service/config');
    return response.data;
  }

  async updateServiceConfig(config: Record<string, unknown>) {
    const response = await this.client.post('/api/service/config', config);
    return response.data;
  }

  // Agent Memory Tables
  async getAgentMemoryTables() {
    const response = await this.client.get('/api/memories/agents');
    return response.data;
  }

  // Memories
  async getMemories(params?: {
    type?: string;
    limit?: number;
    offset?: number;
    query?: string;
    agent_id?: string;
  }) {
    const response = await this.client.get('/api/memories', { params });
    return response.data;
  }

  async createMemory(data: {
    content: string;
    type?: string;
    importance?: number;
    tags?: string[];
    agent_id?: string;
  }) {
    const response = await this.client.post('/api/memories', data);
    return response.data;
  }

  async updateMemory(
    id: number,
    data: Partial<{
      content: string;
      type: string;
      importance: number;
      tags: string[];
    }>,
    agentId?: string
  ) {
    const response = await this.client.put(`/api/memories/${id}`, {
      ...data,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async deleteMemory(id: number, soft_delete: boolean = false) {
    const response = await this.client.delete(`/api/memories/${id}`, {
      params: { soft_delete },
    });
    return response.data;
  }

  // Permanent Memories
  async getPermanentMemories(params?: { limit?: number; offset?: number; workspace_id?: string }) {
    const response = await this.client.get('/api/memories/permanent', { params });
    return response.data;
  }

  async createPermanentMemory(data: {
    content: string;
    importance?: number;
    tags?: string[];
    metadata?: Record<string, unknown>;
  }) {
    const response = await this.client.post('/api/memories/permanent', data);
    return response.data;
  }

  async updatePermanentMemory(
    id: number,
    data: Partial<{
      content: string;
      importance: number;
      tags: string[];
      metadata: Record<string, unknown>;
    }>
  ) {
    const response = await this.client.put(`/api/memories/permanent/${id}`, data);
    return response.data;
  }

  async deletePermanentMemory(id: number) {
    const response = await this.client.delete(`/api/memories/permanent/${id}`);
    return response.data;
  }

  async searchMemories(
    query: string,
    options?: {
      type?: string;
      limit?: number;
    }
  ) {
    const response = await this.client.post('/api/memories/search', {
      query,
      ...options,
    });
    return response.data;
  }

  async semanticSearch(
    query: string,
    options?: {
      limit?: number;
      min_score?: number;
    }
  ) {
    const response = await this.client.post('/api/memories/semantic-search', {
      query,
      ...options,
    });
    return response.data;
  }

  // Archive
  async getArchiveStats() {
    const response = await this.client.get('/api/archive/stats');
    return response.data;
  }

  async getArchivedMemories(params?: { limit?: number; offset?: number; agent_id?: string }) {
    const response = await this.client.get('/api/archive/list', { params });
    return response.data;
  }

  async restoreMemory(memoryId: number, agentId?: string) {
    const response = await this.client.post('/api/memories/batch/restore', {
      ids: [memoryId],
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async archiveMemory(memoryId: number, targetLevel: number = 1) {
    const response = await this.client.post('/api/archive/memory', {
      memory_id: memoryId,
      target_level: targetLevel,
    });
    return response.data;
  }

  async mergeMemories(memoryIds: number[]) {
    const response = await this.client.post('/api/archive/merge', {
      memory_ids: memoryIds,
    });
    return response.data;
  }

  async detectDuplicates() {
    const response = await this.client.post('/api/archive/deduplicate');
    return response.data;
  }

  async autoArchiveProcess() {
    const response = await this.client.post('/api/archive/auto-process');
    return response.data;
  }

  // Memory Chat
  async memoryChat(message: string, sessionId: string = 'default') {
    const response = await this.client.post('/api/memory-chat', {
      message,
      session_id: sessionId,
    });
    return response.data;
  }

  // Chat
  async sendMessage(message: string, sessionId?: string, agentId?: string) {
    const response = await this.client.post('/api/chat', {
      message,
      session_id: sessionId,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  // Context
  async getSessions() {
    const cacheKey = this._getCacheKey('/api/context/sessions');
    const cached = this._getFromCache(cacheKey);
    if (cached) return cached;

    const response = await this.client.get('/api/context/sessions');
    this._setCache(cacheKey, response.data, 30000);
    return response.data;
  }

  async createSession(title?: string, agentId?: string) {
    this._clearCache('/api/context/sessions');
    const response = await this.client.post('/api/context/sessions', {
      workspace_id: 'default',
      title: title || '新对话',
      ...(agentId ? { agent_id: agentId } : {}),
    });
    return response.data;
  }

  async deleteSession(sessionId: string) {
    this._clearCache('/api/context/sessions');
    this._clearCache(`/api/context/sessions/${sessionId}`);
    const response = await this.client.delete(`/api/context/sessions/${sessionId}`);
    return response.data;
  }

  async clearSessionMessages(sessionId: string): Promise<{ status: string; message: string }> {
    const response = await this.client.delete(`/api/context/sessions/${sessionId}/messages`);
    return response.data;
  }

  async clearAllSessions() {
    this._clearCache('/api/context/sessions');
    const response = await this.client.delete('/api/context/sessions/all');
    return response.data;
  }

  // Admin
  async getHealth() {
    const response = await this.client.get('/health');
    return response.data;
  }

  async getAdminStats() {
    const response = await this.client.get('/api/admin/stats');
    return response.data;
  }

  async getChatHistory(agentId: string) {
    const response = await this.client.get(`/api/chat/history/agent-${agentId}`);
    return response.data;
  }

  async getAgentContext(agentId: string, limit: number = 50) {
    const response = await this.client.get(`/api/agents/${agentId}/context`, { params: { limit } });
    return response.data;
  }

  // ========== ACP APIs ==========

  async getAcpStats() {
    const response = await this.client.get('/api/acp/stats');
    return response.data;
  }

  async getAcpAgents() {
    const response = await this.client.get('/api/acp/agents');
    return response.data;
  }

  async createAcpAgent(data: {
    agent_id: string;
    host: string;
    port: number;
  }) {
    const response = await this.client.post('/api/acp/connect', data);
    return response.data;
  }

  async updateAcpAgent(
    id?: string,
    data?: Partial<{
      name: string;
      description: string;
      capabilities: string[];
      status: 'active' | 'inactive';
    }>
  ) {
    console.warn('updateAcpAgent: No backend endpoint exists for updating ACP agents. This operation is not supported.', { id, data });
    return { status: 'error', message: 'Updating ACP agents is not supported' };
  }

  async deleteAcpAgent(id: string) {
    const response = await this.client.delete(`/api/acp/connect/${id}`);
    return response.data;
  }

  // ========== Chat Agent APIs ==========

  async getAgents() {
    const cacheKey = this._getCacheKey('/api/agents');
    const cached = this._getFromCache(cacheKey);
    if (cached) return cached;

    const response = await this.client.get('/api/agents');
    this._setCache(cacheKey, response.data, 300000);
    return response.data;
  }

  async getAgent(id: string) {
    const cacheKey = this._getCacheKey(`/api/agents/${id}`);
    const cached = this._getFromCache(cacheKey);
    if (cached) return cached;

    const response = await this.client.get(`/api/agents/${id}`);
    this._setCache(cacheKey, response.data, 300000);
    return response.data;
  }

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
    this._clearCache('/api/agents');
    const response = await this.client.post('/api/agents', data);
    return response.data;
  }

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
    this._clearCache('/api/agents');
    this._clearCache(`/api/agents/${id}`);
    const response = await this.client.put(`/api/agents/${id}`, data);
    return response.data;
  }

  async deleteAgent(id: string) {
    this._clearCache('/api/agents');
    this._clearCache(`/api/agents/${id}`);
    const response = await this.client.delete(`/api/agents/${id}`);
    return response.data;
  }

  async cloneAgent(id: string) {
    const response = await this.client.post(`/api/agents/${id}/clone`);
    return response.data;
  }

  // ========== Tools APIs ==========

  async getToolsStats() {
    const response = await this.client.get('/api/tools/stats');
    return response.data;
  }

  async getTools(type?: string) {
    const params: Record<string, string> = {};
    // type 参数映射到 category
    if (type && type !== 'all' && type !== 'builtin') {
      params['category'] = type;
    }
    if (type === 'builtin') {
      params['include_builtin'] = 'true';
    }
    const response = await this.client.get('/api/tools', { params });
    return response.data;
  }

  async createTool(data: {
    name: string;
    description?: string;
    type: 'mcp' | 'native' | 'custom';
    icon?: string;
    config?: Record<string, unknown>;
  }) {
    const response = await this.client.post('/api/tools', data);
    return response.data;
  }

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
    // No PUT endpoint exists; re-register the tool via POST to effectively update it
    const response = await this.client.post('/api/tools', { name: id, ...data });
    return response.data;
  }

  // Note: `id` parameter is actually the tool name, not a numeric id
  async deleteTool(id: string) {
    const response = await this.client.delete(`/api/tools/${id}`);
    return response.data;
  }

  async testTool(id: string, params: Record<string, unknown>) {
    const response = await this.client.post(`/api/tools/${id}/test`, params);
    return response.data;
  }

  // ========== Streaming Chat API ==========

  async sendMessageStream(
    message: string,
    onChunk: (chunk: {
      type: string;
      content?: string;
      done?: boolean;
      error?: string;
      session_id?: string;
      tool_call?: Record<string, unknown>;
      tool_name?: string;
      result?: unknown;
    }) => void,
    agentId?: string,
    images?: string[],
    signal?: AbortSignal
  ) {
    try {
      const response = await fetch(`${this.client.defaults.baseURL}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('cxhms-token') || ''}`,
        },
        body: JSON.stringify({
          message,
          agent_id: agentId || 'default',
          images: images && images.length > 0 ? images : undefined,
        }),
        signal,
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        onChunk({ type: 'error', error: `HTTP ${response.status}: ${errorText}` });
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onChunk({ type: 'error', error: 'No response body' });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();

          if (value) {
            buffer += decoder.decode(value, { stream: true });
          }

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.trim().startsWith('data: ')) {
              try {
                const data = JSON.parse(line.trim().slice(6));
                onChunk(data);
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }

          if (done) {
            // 处理buffer中剩余的数据
            if (buffer.trim().startsWith('data: ')) {
              try {
                const data = JSON.parse(buffer.trim().slice(6));
                onChunk(data);
              } catch (e) {
                console.error('Failed to parse remaining buffer:', e);
              }
            }
            break;
          }
        }
      } catch (streamError) {
        onChunk({
          type: 'error',
          error: `Stream error: ${streamError instanceof Error ? streamError.message : 'Unknown error'}`,
        });
      } finally {
        reader.releaseLock();
      }
    } catch (fetchError) {
      onChunk({
        type: 'error',
        error: `Fetch error: ${fetchError instanceof Error ? fetchError.message : 'Unknown error'}`,
      });
    }
  }

  // ========== Batch Memory Operations APIs ==========

  async batchDeleteMemories(ids: number[], agentId?: string) {
    const response = await this.client.post('/api/memories/batch/delete', {
      ids,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async batchUpdateTags(
    ids: number[],
    tags: string[],
    operation: 'add' | 'remove' | 'set' = 'add',
    agentId?: string
  ) {
    const response = await this.client.post('/api/memories/batch/tags', {
      ids,
      tags,
      operation,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async batchArchiveMemories(ids: number[], agentId?: string) {
    const response = await this.client.post('/api/memories/batch/archive', {
      ids,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async batchRestoreMemories(ids: number[], agentId?: string) {
    const response = await this.client.post('/api/memories/batch/restore', {
      ids,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async batchUpdateMemories(
    ids: number[],
    data: { content?: string; tags?: string[]; importance?: number },
    agentId?: string
  ) {
    const response = await this.client.post('/api/memories/batch/update', {
      ids,
      data,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async batchTagByQuery(
    query: string,
    tags: string[],
    operation: 'add' | 'remove' | 'set' = 'add',
    agentId?: string
  ) {
    const response = await this.client.post('/api/memories/batch/tag-by-query', {
      query,
      tags,
      operation,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async batchDeleteByQuery(query: string, agentId?: string) {
    const response = await this.client.post('/api/memories/batch/delete-by-query', {
      query,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async batchArchiveByQuery(query: string, targetLevel: number = 1, agentId?: string) {
    const response = await this.client.post('/api/memories/batch/archive-by-query', {
      query,
      target_level: targetLevel,
      agent_id: agentId || 'default',
    });
    return response.data;
  }

  async getMemoriesByType(type: string, params?: { limit?: number; workspace_id?: string }) {
    const response = await this.client.get(`/api/memories/type/${type}`, { params });
    return response.data;
  }

  async searchByTag(tag: string, params?: { limit?: number; workspace_id?: string }) {
    const response = await this.client.get('/api/memories/search-by-tag', {
      params: { tag, ...params },
    });
    return response.data;
  }

  // ========== Memory Agent Streaming API ==========

  async sendMemoryAgentMessageStream(
    message: string,
    onChunk: (chunk: {
      type: string;
      content?: string;
      done?: boolean;
      error?: string;
      session_id?: string;
      tool_call?: Record<string, unknown>;
      tool_name?: string;
      result?: unknown;
      thinking?: string;
    }) => void,
    signal?: AbortSignal
  ) {
    try {
      const response = await fetch(`${this.client.defaults.baseURL}/api/memory-agent/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('cxhms-token') || ''}`,
        },
        body: JSON.stringify({ message }),
        signal,
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        onChunk({ type: 'error', error: `HTTP ${response.status}: ${errorText}` });
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onChunk({ type: 'error', error: 'No response body' });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();

          if (value) {
            buffer += decoder.decode(value, { stream: true });
          }

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.trim().startsWith('data: ')) {
              try {
                const data = JSON.parse(line.trim().slice(6));
                onChunk(data);
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }

          if (done) {
            // Process remaining buffer data
            if (buffer.trim().startsWith('data: ')) {
              try {
                const data = JSON.parse(buffer.trim().slice(6));
                onChunk(data);
              } catch (e) {
                console.error('Failed to parse remaining buffer:', e);
              }
            }
            break;
          }
        }
      } catch (streamError) {
        onChunk({
          type: 'error',
          error: `Stream error: ${streamError instanceof Error ? streamError.message : 'Unknown error'}`,
        });
      } finally {
        reader.releaseLock();
      }
    } catch (fetchError) {
      onChunk({
        type: 'error',
        error: `Fetch error: ${fetchError instanceof Error ? fetchError.message : 'Unknown error'}`,
      });
    }
  }

  // ========== Summary Agent Streaming API ==========

  async sendSummaryAgentMessageStream(
    message: string,
    onChunk: (chunk: {
      type: string;
      content?: string;
      done?: boolean;
      error?: string;
      session_id?: string;
      tool_call?: Record<string, unknown>;
      tool_name?: string;
      result?: unknown;
      target_session_id?: string;
      summarized_up_to?: number;
    }) => void,
    signal?: AbortSignal,
    options?: { targetSessionId?: string }
  ) {
    try {
      const response = await fetch(`${this.client.defaults.baseURL}/api/summary-agent/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('cxhms-token') || ''}`,
        },
        body: JSON.stringify({
          message,
          target_session_id: options?.targetSessionId,
        }),
        signal,
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        onChunk({ type: 'error', error: `HTTP ${response.status}: ${errorText}` });
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onChunk({ type: 'error', error: 'No response body' });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();

          if (value) {
            buffer += decoder.decode(value, { stream: true });
          }

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.trim().startsWith('data: ')) {
              try {
                const data = JSON.parse(line.trim().slice(6));
                onChunk(data);
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }

          if (done) {
            if (buffer.trim().startsWith('data: ')) {
              try {
                const data = JSON.parse(buffer.trim().slice(6));
                onChunk(data);
              } catch (e) {
                console.error('Failed to parse remaining buffer:', e);
              }
            }
            break;
          }
        }
      } catch (streamError) {
        onChunk({
          type: 'error',
          error: `Stream error: ${streamError instanceof Error ? streamError.message : 'Unknown error'}`,
        });
      } finally {
        reader.releaseLock();
      }
    } catch (fetchError) {
      onChunk({
        type: 'error',
        error: `Fetch error: ${fetchError instanceof Error ? fetchError.message : 'Unknown error'}`,
      });
    }
  }

  // ========== Diary API ==========

  async getDiaryEntries(params?: { limit?: number; agent_id?: string; workspace_id?: string }) {
    const response = await this.client.get('/api/memories/diary', {
      params: {
        limit: params?.limit ?? 100,
        agent_id: params?.agent_id ?? 'default',
        workspace_id: params?.workspace_id ?? 'default',
      },
    });
    return response.data;
  }

  // ========== Models API ==========

  async getAvailableModels() {
    const response = await this.client.get('/api/service/models');
    return response.data;
  }

  // ========== Stats API ==========

  async getStats() {
    const response = await this.client.get('/api/stats');
    return response.data;
  }

  // ========== Graph Database API ==========

  async createNode(data: { type: string; properties?: Record<string, unknown>; text_content?: string }, agentId: string = 'default') {
    const response = await this.client.post('/api/nodes', { ...data, agent_id: agentId });
    return response.data;
  }

  async getNodes(params?: { node_type?: string; limit?: number; offset?: number; agent_id?: string }) {
    const response = await this.client.get('/api/nodes/search', { params });
    return response.data;
  }

  async getNode(nodeId: string, agentId: string = 'default') {
    const response = await this.client.get(`/api/nodes/${nodeId}`, { params: { agent_id: agentId } });
    return response.data;
  }

  async updateNode(nodeId: string, data: { type?: string; properties?: Record<string, unknown>; text_content?: string }, agentId: string = 'default') {
    const response = await this.client.put(`/api/nodes/${nodeId}`, { ...data, agent_id: agentId });
    return response.data;
  }

  async deleteNode(nodeId: string, cascade: boolean = true, agentId: string = 'default') {
    const response = await this.client.delete(`/api/nodes/${nodeId}`, { params: { cascade, agent_id: agentId } });
    return response.data;
  }

  async createEdge(data: { source_id: string; target_id: string; relation_type: string; properties?: Record<string, unknown>; text_content?: string }, agentId: string = 'default') {
    const response = await this.client.post('/api/edges', { ...data, agent_id: agentId });
    return response.data;
  }

  async getEdges(params?: { relation_type?: string; source_id?: string; target_id?: string; limit?: number; offset?: number; agent_id?: string }) {
    const response = await this.client.get('/api/edges/search', { params });
    return response.data;
  }

  async deleteEdge(edgeId: string, agentId: string = 'default') {
    const response = await this.client.delete(`/api/edges/${edgeId}`, { params: { agent_id: agentId } });
    return response.data;
  }

  async getNodeNeighbors(nodeId: string, params?: { max_depth?: number; direction?: string; agent_id?: string }) {
    const response = await this.client.get(`/api/nodes/${nodeId}/neighbors`, { params });
    return response.data;
  }

  async traverseBFS(data: { start_id: string; max_depth?: number; node_type_filter?: string; agent_id?: string }) {
    const response = await this.client.post('/api/traverse/bfs', data);
    return response.data;
  }

  async traverseDFS(data: { start_id: string; max_depth?: number; node_type_filter?: string; agent_id?: string }) {
    const response = await this.client.post('/api/traverse/dfs', data);
    return response.data;
  }

  async getShortestPath(params: { start_id: string; end_id: string; max_length?: number; agent_id?: string }) {
    const response = await this.client.get('/api/paths/shortest', { params });
    return response.data;
  }

  async graphSemanticSearch(data: { query: string; node_type?: string; limit?: number; agent_id?: string }) {
    const response = await this.client.post('/api/semantic/search', data);
    return response.data;
  }

  async graphHybridSearch(data: { query: string; node_type?: string; properties_filter?: Record<string, unknown>; limit?: number; agent_id?: string }) {
    const response = await this.client.post('/api/semantic/hybrid', data);
    return response.data;
  }

  async getGraphStats(agentId: string = 'default') {
    const response = await this.client.get('/api/stats', { params: { agent_id: agentId } });
    return response.data;
  }

  async getGraphHealth(agentId: string = 'default') {
    const response = await this.client.get('/api/health', { params: { agent_id: agentId } });
    return response.data;
  }

  async getImportantNodes(params?: { limit?: number; agent_id?: string }) {
    const response = await this.client.get('/api/algorithm/important-nodes', { params });
    return response.data;
  }

  async pageRank(params?: { damping?: number; max_iterations?: number; agent_id?: string }) {
    const response = await this.client.get('/api/algorithm/pagerank', { params });
    return response.data;
  }

  async detectCommunities(params?: { method?: string; agent_id?: string }) {
    const response = await this.client.get('/api/algorithm/communities', { params });
    return response.data;
  }

  async exportGraph(format: string = 'json', agentId: string = 'default') {
    const response = await this.client.get(`/api/export/${format}`, { params: { agent_id: agentId } });
    return response.data;
  }

  // ========== Vector Database API ==========

  async getVectorConfig() {
    const response = await this.client.get('/api/vector/config');
    return response.data;
  }

  async getVectorStatus() {
    const response = await this.client.get('/api/vector/status');
    return response.data;
  }

  async getVectorHealth() {
    const response = await this.client.get('/api/vector/health');
    return response.data;
  }

  async vectorSync() {
    const response = await this.client.post('/api/vector/sync');
    return response.data;
  }

  async vectorRebuild() {
    const response = await this.client.post('/api/vector/rebuild');
    return response.data;
  }

  async vectorSearch(data: { query: string; limit?: number }) {
    const response = await this.client.post('/api/vector/search', data);
    return response.data;
  }

  async getVectorStats() {
    const response = await this.client.get('/api/vector/stats');
    return response.data;
  }

  // ========== CXFC API ==========

  async registerCXFCPlugin(data: { name: string; version: string; description?: string; capabilities?: string[] }) {
    const response = await this.client.post('/api/cxfc/register', data);
    return response.data;
  }

  async cxfcHeartbeat(pluginId: string) {
    const response = await this.client.post('/api/cxfc/heartbeat', { plugin_id: pluginId });
    return response.data;
  }

  async cxfcDiscover() {
    const response = await this.client.get('/api/cxfc/discover');
    return response.data;
  }

  async cxfcSkills(pluginId?: string) {
    const response = await this.client.get('/api/cxfc/skills', { params: { plugin_id: pluginId } });
    return response.data;
  }

  async cxfcConnect(host: string, port: number) {
    const response = await this.client.post('/api/cxfc/connect', { host, port });
    return response.data;
  }

  async cxfcDisconnect(pluginId: string) {
    const response = await this.client.delete(`/api/cxfc/plugins/${pluginId}`);
    return response.data;
  }

  // ========== Unified Config API ==========

  async getConfig() {
    const response = await this.client.get('/api/config');
    return response.data;
  }

  async setConfig(data: Record<string, unknown>) {
    const response = await this.client.put('/api/config', data);
    return response.data;
  }

  async getConfigSection(section: string) {
    const sectionEndpoints: Record<string, string> = {
      'vector': '/api/config/vector',
      'graph': '/api/config/graph',
      'cxfc': '/api/config/cxfc',
      'llm': '/api/config',
    };
    const endpoint = sectionEndpoints[section] || '/api/config';
    const response = await this.client.get(endpoint);
    return response.data;
  }

  async setConfigSection(section: string, data: Record<string, unknown>) {
    const response = await this.client.put('/api/config', { section, data });
    return response.data;
  }
  /** 检查后端连接是否可用 */
  async checkHealth(apiUrl?: string): Promise<boolean> {
    try {
      const url = apiUrl || this.client.defaults.baseURL;
      const response = await axios.get(`${url}/health`, { timeout: 5000 });
      return response.status === 200;
    } catch {
      return false;
    }
  }

  /** 动态修改后端地址 */
  setBaseUrls(apiUrl: string, controlUrl?: string) {
    this.client.defaults.baseURL = apiUrl;
    if (controlUrl) {
      this.controlClient.defaults.baseURL = controlUrl;
    }
    localStorage.setItem('cxhms-api-url', apiUrl);
    if (controlUrl) {
      localStorage.setItem('cxhms-control-url', controlUrl);
    }
  }

  /** 获取当前 API 地址 */
  getApiUrl(): string {
    return this.client.defaults.baseURL || API_BASE_URL;
  }
}

export const api = new ApiClient();
