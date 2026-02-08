import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useChatStore } from './chatStore'
import { api } from '../api/client'

vi.mock('../api/client', () => ({
  api: {
    chat: {
      sendMessage: vi.fn(),
      getHistory: vi.fn(),
      createSession: vi.fn(),
      getSessions: vi.fn(),
      deleteSession: vi.fn()
    }
  }
}))

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      sessions: [],
      currentSessionId: null,
      isLoading: false,
      error: null
    })
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useChatStore.getState()
      expect(state.messages).toEqual([])
      expect(state.sessions).toEqual([])
      expect(state.currentSessionId).toBeNull()
      expect(state.isLoading).toBe(false)
      expect(state.error).toBeNull()
    })
  })

  describe('setCurrentSession', () => {
    it('should set current session', () => {
      useChatStore.getState().setCurrentSession('session-1')
      expect(useChatStore.getState().currentSessionId).toBe('session-1')
    })
  })

  describe('addMessage', () => {
    it('should add a message', () => {
      const message = {
        id: '1',
        role: 'user' as const,
        content: 'Hello',
        timestamp: new Date().toISOString()
      }
      useChatStore.getState().addMessage(message)
      expect(useChatStore.getState().messages).toHaveLength(1)
      expect(useChatStore.getState().messages[0].content).toBe('Hello')
    })
  })

  describe('clearMessages', () => {
    it('should clear all messages', () => {
      useChatStore.getState().addMessage({
        id: '1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString()
      })
      useChatStore.getState().clearMessages()
      expect(useChatStore.getState().messages).toHaveLength(0)
    })
  })

  describe('sendMessage', () => {
    it('should handle successful message send', async () => {
      const mockResponse = {
        status: 'success',
        response: 'AI response',
        session_id: 'session-1'
      }
      vi.mocked(api.chat.sendMessage).mockResolvedValueOnce(mockResponse)

      const result = await useChatStore.getState().sendMessage('Hello', 'default')

      expect(result).toEqual(mockResponse)
      expect(useChatStore.getState().isLoading).toBe(false)
    })

    it('should handle error', async () => {
      vi.mocked(api.chat.sendMessage).mockRejectedValueOnce(new Error('Network error'))

      await expect(useChatStore.getState().sendMessage('Hello', 'default'))
        .rejects.toThrow('Network error')
      expect(useChatStore.getState().error).toBe('Network error')
      expect(useChatStore.getState().isLoading).toBe(false)
    })
  })

  describe('loadSessions', () => {
    it('should load sessions successfully', async () => {
      const mockSessions = [
        { id: '1', title: 'Session 1', updated_at: new Date().toISOString() },
        { id: '2', title: 'Session 2', updated_at: new Date().toISOString() }
      ]
      vi.mocked(api.chat.getSessions).mockResolvedValueOnce(mockSessions)

      await useChatStore.getState().loadSessions()

      expect(useChatStore.getState().sessions).toHaveLength(2)
    })

    it('should handle load error', async () => {
      vi.mocked(api.chat.getSessions).mockRejectedValueOnce(new Error('Load failed'))

      await useChatStore.getState().loadSessions()

      expect(useChatStore.getState().sessions).toEqual([])
      expect(useChatStore.getState().error).toBe('Load failed')
    })
  })

  describe('createSession', () => {
    it('should create new session', async () => {
      const mockSession = {
        id: 'new-session',
        title: 'New Session',
        created_at: new Date().toISOString()
      }
      vi.mocked(api.chat.createSession).mockResolvedValueOnce(mockSession)

      const result = await useChatStore.getState().createSession()

      expect(result.id).toBe('new-session')
      expect(useChatStore.getState().currentSessionId).toBe('new-session')
    })
  })

  describe('deleteSession', () => {
    it('should delete session', async () => {
      vi.mocked(api.chat.deleteSession).mockResolvedValueOnce(undefined)

      await useChatStore.getState().deleteSession('session-1')

      expect(api.chat.deleteSession).toHaveBeenCalledWith('session-1')
    })
  })
})
