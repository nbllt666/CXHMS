import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '../api/client'

interface Agent {
  id: string
  name: string
  description: string
  system_prompt: string
  model: string
  temperature: number
  max_tokens: number
  use_memory: boolean
  use_tools: boolean
  memory_scene: string
  vision_enabled?: boolean
  is_default?: boolean
}

interface Session {
  id: string
  title: string
  agent_id?: string
  message_count?: number
  created_at?: string
  updated_at?: string
}

interface ChatState {
  agents: Agent[]
  currentAgentId: string | null
  setAgents: (agents: Agent[]) => void
  setCurrentAgentId: (id: string | null) => void
  fetchAgents: () => Promise<void>

  sessions: Session[]
  currentSessionId: string | null
  setSessions: (sessions: Session[]) => void
  setCurrentSessionId: (id: string | null) => void

  isChatExpanded: boolean
  setIsChatExpanded: (expanded: boolean) => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      agents: [],
      currentAgentId: null,

      setAgents: (agents) => set({ agents }),

      setCurrentAgentId: (id) => set({ currentAgentId: id }),

      fetchAgents: async () => {
        try {
          const data = await api.getAgents()
          const filteredAgents = data.filter((agent: Agent) => agent.id !== 'memory-agent')
          set({ agents: filteredAgents })

          const { currentAgentId } = get()
          if (!currentAgentId && filteredAgents.length > 0) {
            const defaultAgent = filteredAgents.find((a: Agent) => a.is_default) || filteredAgents[0]
            set({ currentAgentId: defaultAgent.id })
          }
        } catch (error) {
          console.error('Failed to fetch agents:', error)
        }
      },

      sessions: [],
      currentSessionId: null,
      setSessions: (sessions) => set({ sessions }),
      setCurrentSessionId: (id) => set({ currentSessionId: id }),

      isChatExpanded: false,
      setIsChatExpanded: (expanded) => set({ isChatExpanded: expanded }),
    }),
    {
      name: 'cxhms-chat-storage',
      partialize: (state) => ({
        currentAgentId: state.currentAgentId,
        currentSessionId: state.currentSessionId,
        isChatExpanded: state.isChatExpanded,
      }),
    }
  )
)
