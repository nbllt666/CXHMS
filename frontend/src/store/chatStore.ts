import { create } from 'zustand'
import { persist } from 'zustand/middleware'

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
  is_default?: boolean
}

interface Session {
  id: string
  title: string
  agent_id?: string
  message_count: number
  created_at: string
}

interface ChatState {
  // Agent
  agents: Agent[]
  currentAgentId: string
  setAgents: (agents: Agent[]) => void
  setCurrentAgentId: (id: string) => void
  
  // Session
  sessions: Session[]
  currentSessionId: string | null
  setSessions: (sessions: Session[]) => void
  setCurrentSessionId: (id: string | null) => void
  
  // UI State
  isChatExpanded: boolean
  setIsChatExpanded: (expanded: boolean) => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      // Agent
      agents: [],
      currentAgentId: 'default',
      setAgents: (agents) => set({ agents }),
      setCurrentAgentId: (id) => set({ currentAgentId: id }),
      
      // Session
      sessions: [],
      currentSessionId: null,
      setSessions: (sessions) => set({ sessions }),
      setCurrentSessionId: (id) => set({ currentSessionId: id }),
      
      // UI State
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
