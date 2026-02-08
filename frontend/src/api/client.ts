import axios, { AxiosInstance, AxiosError } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''
const CONTROL_SERVICE_URL = ''

// Type definitions
export interface Agent {
  id: string
  name: string
  description?: string
  is_default?: boolean
  model?: string
  temperature?: number
  max_tokens?: number
  system_prompt?: string
  use_memory?: boolean
  memory_scene?: string
  tools?: string[]
  capabilities?: string[]
}

class ApiClient {
  private client: AxiosInstance
  private controlClient: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Control service client (for managing main backend)
    this.controlClient = axios.create({
      baseURL: CONTROL_SERVICE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        // Add auth token if available
        const token = localStorage.getItem('cxhms-token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          // Handle unauthorized
          localStorage.removeItem('cxhms-token')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  // ========== Control Service APIs (Port 8765) ==========

  // Check control service health
  async getControlServiceHealth() {
    const response = await this.controlClient.get('/health')
    return response.data
  }

  // Get main backend status via control service
  async getMainBackendStatus() {
    const response = await this.controlClient.get('/control/status')
    return response.data
  }

  // Start main backend service
  async startMainBackend() {
    const response = await this.controlClient.post('/control/start')
    return response.data
  }

  // Stop main backend service
  async stopMainBackend() {
    const response = await this.controlClient.post('/control/stop')
    return response.data
  }

  // Restart main backend service
  async restartMainBackend() {
    const response = await this.controlClient.post('/control/restart')
    return response.data
  }

  // ========== Main Backend APIs (Port 8000) ==========

  // Service Management (via main backend when running)
  async getServiceStatus() {
    const response = await this.client.get('/api/service/status')
    return response.data
  }

  async startService(config: {
    host?: string
    port?: number
    log_level?: string
    reload?: boolean
    use_conda?: boolean
  }) {
    const response = await this.client.post('/api/service/start', config)
    return response.data
  }

  async stopService() {
    const response = await this.client.post('/api/service/stop')
    return response.data
  }

  async restartService(config: {
    host?: string
    port?: number
    log_level?: string
    reload?: boolean
    use_conda?: boolean
  }) {
    const response = await this.client.post('/api/service/restart', config)
    return response.data
  }

  async getServiceLogs(lines: number = 100) {
    const response = await this.client.get('/api/service/logs', { params: { lines } })
    return response.data
  }

  async getServiceConfig() {
    const response = await this.client.get('/api/service/config')
    return response.data
  }

  async updateServiceConfig(config: Record<string, unknown>) {
    const response = await this.client.post('/api/service/config', config)
    return response.data
  }

  async getEnvironmentInfo() {
    const response = await this.client.get('/api/service/environment')
    return response.data
  }

  // Memories
  async getMemories(params?: {
    type?: string
    limit?: number
    offset?: number
    query?: string
  }) {
    const response = await this.client.get('/api/memories', { params })
    return response.data
  }

  async createMemory(data: {
    content: string
    type?: string
    importance?: number
    tags?: string[]
  }) {
    const response = await this.client.post('/api/memories', data)
    return response.data
  }

  async updateMemory(id: number, data: Partial<{
    content: string
    type: string
    importance: number
    tags: string[]
  }>) {
    const response = await this.client.put(`/api/memories/${id}`, data)
    return response.data
  }

  async deleteMemory(id: number, soft: boolean = true) {
    const response = await this.client.delete(`/api/memories/${id}`, {
      params: { soft }
    })
    return response.data
  }

  async searchMemories(query: string, options?: {
    type?: string
    limit?: number
  }) {
    const response = await this.client.post('/api/memories/search', {
      query,
      ...options
    })
    return response.data
  }

  async semanticSearch(query: string, options?: {
    limit?: number
    min_score?: number
  }) {
    const response = await this.client.post('/api/memories/semantic-search', {
      query,
      ...options
    })
    return response.data
  }

  // Archive
  async getArchiveStats() {
    const response = await this.client.get('/api/archive/stats')
    return response.data
  }

  async archiveMemory(memoryId: number, targetLevel: number = 1) {
    const response = await this.client.post('/api/archive/memory', {
      memory_id: memoryId,
      target_level: targetLevel
    })
    return response.data
  }

  async mergeMemories(memoryIds: number[]) {
    const response = await this.client.post('/api/archive/merge', {
      memory_ids: memoryIds
    })
    return response.data
  }

  async detectDuplicates() {
    const response = await this.client.post('/api/archive/deduplicate')
    return response.data
  }

  async autoArchiveProcess() {
    const response = await this.client.post('/api/archive/auto-process')
    return response.data
  }

  // Memory Chat
  async memoryChat(message: string, sessionId: string = 'default') {
    const response = await this.client.post('/api/memory-chat', {
      message,
      session_id: sessionId
    })
    return response.data
  }

  // Chat
  async sendMessage(message: string, sessionId?: string, agentId?: string) {
    const response = await this.client.post('/api/chat', {
      message,
      session_id: sessionId,
      agent_id: agentId || 'default'
    })
    return response.data
  }

  // Context
  async getSessions() {
    const response = await this.client.get('/api/context/sessions')
    return response.data
  }

  async createSession(title?: string) {
    const response = await this.client.post('/api/context/sessions', { title })
    return response.data
  }

  async deleteSession(sessionId: string) {
    const response = await this.client.delete(`/api/context/sessions/${sessionId}`)
    return response.data
  }

  // Admin
  async getHealth() {
    const response = await this.client.get('/health')
    return response.data
  }

  async getStats() {
    const response = await this.client.get('/api/admin/stats')
    return response.data
  }

  async getChatHistory(sessionId: string) {
    const response = await this.client.get(`/api/chat/history/${sessionId}`)
    return response.data
  }

  // ========== ACP APIs ==========

  async getAcpStats() {
    const response = await this.client.get('/api/acp/stats')
    return response.data
  }

  async getAcpAgents() {
    const response = await this.client.get('/api/acp/agents')
    return response.data
  }

  async createAcpAgent(data: {
    name: string
    description?: string
    capabilities?: string[]
    status?: 'active' | 'inactive'
  }) {
    const response = await this.client.post('/api/acp/agents', data)
    return response.data
  }

  async updateAcpAgent(id: string, data: Partial<{
    name: string
    description: string
    capabilities: string[]
    status: 'active' | 'inactive'
  }>) {
    const response = await this.client.put(`/api/acp/agents/${id}`, data)
    return response.data
  }

  async deleteAcpAgent(id: string) {
    const response = await this.client.delete(`/api/acp/agents/${id}`)
    return response.data
  }

  // ========== Chat Agent APIs ==========

  async getAgents() {
    const response = await this.client.get('/api/agents')
    return response.data
  }

  async getAgent(id: string) {
    const response = await this.client.get(`/api/agents/${id}`)
    return response.data
  }

  async createAgent(data: {
    name: string
    description?: string
    system_prompt?: string
    model?: string
    temperature?: number
    max_tokens?: number
    use_memory?: boolean
    use_tools?: boolean
    memory_scene?: string
  }) {
    const response = await this.client.post('/api/agents', data)
    return response.data
  }

  async updateAgent(id: string, data: Partial<{
    name: string
    description: string
    system_prompt: string
    model: string
    temperature: number
    max_tokens: number
    use_memory: boolean
    use_tools: boolean
    memory_scene: string
  }>) {
    const response = await this.client.put(`/api/agents/${id}`, data)
    return response.data
  }

  async deleteAgent(id: string) {
    const response = await this.client.delete(`/api/agents/${id}`)
    return response.data
  }

  async cloneAgent(id: string) {
    const response = await this.client.post(`/api/agents/${id}/clone`)
    return response.data
  }

  // ========== Tools APIs ==========

  async getToolsStats() {
    const response = await this.client.get('/api/tools/stats')
    return response.data
  }

  async getTools(type?: string) {
    const params = type ? { type } : {}
    const response = await this.client.get('/api/tools', { params })
    return response.data
  }

  async createTool(data: {
    name: string
    description?: string
    type: 'mcp' | 'native' | 'custom'
    icon?: string
    config?: Record<string, unknown>
  }) {
    const response = await this.client.post('/api/tools', data)
    return response.data
  }

  async updateTool(id: string, data: Partial<{
    name: string
    description: string
    type: 'mcp' | 'native' | 'custom'
    icon: string
    config: Record<string, unknown>
    status: 'active' | 'inactive'
  }>) {
    const response = await this.client.put(`/api/tools/${id}`, data)
    return response.data
  }

  async deleteTool(id: string) {
    const response = await this.client.delete(`/api/tools/${id}`)
    return response.data
  }

  async testTool(id: string, params: Record<string, unknown>) {
    const response = await this.client.post(`/api/tools/${id}/test`, params)
    return response.data
  }

  // ========== Streaming Chat API ==========

  async sendMessageStream(
    message: string,
    sessionId: string,
    onChunk: (chunk: { content?: string; done?: boolean; error?: string; session_id?: string }) => void,
    agentId?: string
  ) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('cxhms-token') || ''}`
        },
        body: JSON.stringify({ message, session_id: sessionId, agent_id: agentId || 'default' })
      })

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error')
        onChunk({ error: `HTTP ${response.status}: ${errorText}` })
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onChunk({ error: 'No response body' })
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.trim().startsWith('data: ')) {
              try {
                const data = JSON.parse(line.trim().slice(6))
                onChunk(data)
              } catch (e) {
                console.error('Failed to parse SSE data:', e)
              }
            }
          }
        }
      } catch (streamError) {
        onChunk({ error: `Stream error: ${streamError instanceof Error ? streamError.message : 'Unknown error'}` })
      } finally {
        reader.releaseLock()
      }
    } catch (fetchError) {
      onChunk({ error: `Fetch error: ${fetchError instanceof Error ? fetchError.message : 'Unknown error'}` })
    }
  }

  // ========== Batch Memory Operations APIs ==========

  async batchDeleteMemories(ids: number[]) {
    const response = await this.client.post('/api/memories/batch/delete', { ids })
    return response.data
  }

  async batchUpdateTags(ids: number[], tags: string[], operation: 'add' | 'remove' | 'set' = 'add') {
    const response = await this.client.post('/api/memories/batch/tags', { ids, tags, operation })
    return response.data
  }

  async batchArchiveMemories(ids: number[]) {
    const response = await this.client.post('/api/memories/batch/archive', { ids })
    return response.data
  }

  async getMemoriesByType(type: string, params?: { limit?: number; workspace_id?: string }) {
    const response = await this.client.get(`/api/memories/type/${type}`, { params })
    return response.data
  }

  async searchByTag(tag: string, params?: { limit?: number; workspace_id?: string }) {
    const response = await this.client.get('/api/memories/search-by-tag', {
      params: { tag, ...params }
    })
    return response.data
  }
}

export const api = new ApiClient()
