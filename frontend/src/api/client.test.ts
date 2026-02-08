import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, API_BASE_URL } from './client'

describe('API Client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('Health Check', () => {
    it('should check health successfully', async () => {
      const mockResponse = { status: 'healthy', service: 'CXHMS' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      } as Response)

      const result = await api.health.check()
      expect(result).toEqual(mockResponse)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/health`)
    })

    it('should throw error on failed health check', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 500
      } as Response)

      await expect(api.health.check()).rejects.toThrow('HTTP error! status: 500')
    })
  })

  describe('Chat API', () => {
    it('should send message successfully', async () => {
      const mockResponse = {
        status: 'success',
        response: 'AI response',
        session_id: 'session-1'
      }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      } as Response)

      const result = await api.chat.sendMessage('Hello', 'default', null)
      expect(result).toEqual(mockResponse)
    })

    it('should get chat history', async () => {
      const mockHistory = {
        messages: [
          { id: '1', role: 'user', content: 'Hello' },
          { id: '2', role: 'assistant', content: 'Hi!' }
        ]
      }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockHistory)
      } as Response)

      const result = await api.chat.getHistory('session-1')
      expect(result.messages).toHaveLength(2)
    })

    it('should create session', async () => {
      const mockSession = { id: 'new-session', title: 'New Chat' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSession)
      } as Response)

      const result = await api.chat.createSession()
      expect(result.id).toBe('new-session')
    })

    it('should get sessions', async () => {
      const mockSessions = [
        { id: '1', title: 'Chat 1' },
        { id: '2', title: 'Chat 2' }
      ]
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSessions)
      } as Response)

      const result = await api.chat.getSessions()
      expect(result).toHaveLength(2)
    })

    it('should delete session', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({})
      } as Response)

      await api.chat.deleteSession('session-1')
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/chat/sessions/session-1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })

  describe('Agent API', () => {
    it('should get all agents', async () => {
      const mockAgents = [
        { id: 'default', name: 'Default Agent' }
      ]
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAgents)
      } as Response)

      const result = await api.agents.getAll()
      expect(result).toHaveLength(1)
    })

    it('should get agent by id', async () => {
      const mockAgent = { id: 'default', name: 'Default Agent' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAgent)
      } as Response)

      const result = await api.agents.getById('default')
      expect(result.id).toBe('default')
    })

    it('should create agent', async () => {
      const mockAgent = { id: 'new-agent', name: 'New Agent' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAgent)
      } as Response)

      const result = await api.agents.create({ name: 'New Agent' })
      expect(result.id).toBe('new-agent')
    })

    it('should update agent', async () => {
      const mockAgent = { id: 'default', name: 'Updated Agent' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockAgent)
      } as Response)

      const result = await api.agents.update('default', { name: 'Updated Agent' })
      expect(result.name).toBe('Updated Agent')
    })

    it('should delete agent', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({})
      } as Response)

      await api.agents.delete('agent-1')
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agents/agent-1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })

  describe('Memory API', () => {
    it('should get all memories', async () => {
      const mockResponse = {
        memories: [{ id: '1', content: 'Test memory' }],
        total: 1
      }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      } as Response)

      const result = await api.memories.getAll()
      expect(result.memories).toHaveLength(1)
      expect(result.total).toBe(1)
    })

    it('should get memory by id', async () => {
      const mockMemory = { id: '1', content: 'Test memory' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockMemory)
      } as Response)

      const result = await api.memories.getById('1')
      expect(result.id).toBe('1')
    })

    it('should create memory', async () => {
      const mockMemory = { id: '1', content: 'New memory' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockMemory)
      } as Response)

      const result = await api.memories.create({ content: 'New memory' })
      expect(result.content).toBe('New memory')
    })

    it('should update memory', async () => {
      const mockMemory = { id: '1', content: 'Updated memory' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockMemory)
      } as Response)

      const result = await api.memories.update('1', { content: 'Updated memory' })
      expect(result.content).toBe('Updated memory')
    })

    it('should delete memory', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({})
      } as Response)

      await api.memories.delete('1')
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/memories/1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })

    it('should search memories', async () => {
      const mockResults = [{ id: '1', content: 'Test', score: 0.9 }]
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResults)
      } as Response)

      const result = await api.memories.search('test query')
      expect(result).toHaveLength(1)
    })
  })
})
