import axios, { AxiosInstance, AxiosError } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
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

  // Service Management
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

  async updateServiceConfig(config: Record<string, any>) {
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
  async sendMessage(message: string, sessionId?: string) {
    const response = await this.client.post('/api/chat', {
      message,
      session_id: sessionId
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

  // Admin
  async getHealth() {
    const response = await this.client.get('/health')
    return response.data
  }

  async getStats() {
    const response = await this.client.get('/api/admin/stats')
    return response.data
  }
}

export const api = new ApiClient()
