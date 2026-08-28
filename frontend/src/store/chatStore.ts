import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '../api';
import type { Agent, Session } from '../types';

// F8: Agent / Session 类型统一到 types/，此处不再重复声明。

interface ChatState {
  agents: Agent[];
  currentAgentId: string | null;
  isLoadingAgents: boolean;
  agentsError: string | null;
  isHydrated: boolean;
  setAgents: (agents: Agent[]) => void;
  setCurrentAgentId: (id: string | null) => void;
  fetchAgents: () => Promise<void>;

  sessions: Session[];
  currentSessionId: string | null;
  isLoadingSessions: boolean;
  sessionsError: string | null;
  setSessions: (sessions: Session[]) => void;
  setCurrentSessionId: (id: string | null) => void;
  fetchSessions: () => Promise<void>;
  createSession: (agentId?: string) => Promise<string | null>;
  deleteSession: (sessionId: string) => Promise<void>;

  isChatExpanded: boolean;
  setIsChatExpanded: (expanded: boolean) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      agents: [],
      currentAgentId: null,
      isLoadingAgents: false,
      agentsError: null,
      isHydrated: false,

      setAgents: (agents) => set({ agents }),

      setCurrentAgentId: (id) => set({ currentAgentId: id }),

      fetchAgents: async () => {
        set({ isLoadingAgents: true, agentsError: null });
        try {
          const response = await api.getAgents();
          const agents = response.agents || response || [];
          const filteredAgents = agents.filter((agent: Agent) => agent.id !== 'memory-agent');
          set({ agents: filteredAgents, isHydrated: true });

          const { currentAgentId } = get();
          // F6: currentAgentId 悬空（已被删除）时回退到默认 agent，避免指向不存在的会话。
          if (!currentAgentId || !filteredAgents.some((a: Agent) => a.id === currentAgentId)) {
            const defaultAgent =
              filteredAgents.find((a: Agent) => a.is_default) || filteredAgents[0];
            set({ currentAgentId: defaultAgent?.id ?? null });
          }
        } catch (error) {
          console.error('Failed to fetch agents:', error);
          set({ agentsError: '加载失败', isHydrated: true });
        } finally {
          set({ isLoadingAgents: false });
        }
      },

      sessions: [],
      currentSessionId: null,
      isLoadingSessions: false,
      sessionsError: null,

      setSessions: (sessions) => set({ sessions }),

      setCurrentSessionId: (id) => set({ currentSessionId: id }),

      fetchSessions: async () => {
        set({ isLoadingSessions: true, sessionsError: null });
        try {
          const data = await api.getSessions();
          const sessionsList = Array.isArray(data) ? data : data?.sessions ?? [];
          set({ sessions: sessionsList });
        } catch (error) {
          console.error('Failed to fetch sessions:', error);
          set({ sessionsError: '加载失败' });
        } finally {
          set({ isLoadingSessions: false });
        }
      },

      createSession: async (agentId?: string) => {
        try {
          const data = await api.createSession(undefined, agentId);
          if (data.session_id) {
            if (agentId) {
              set({ currentAgentId: agentId });
            }
            set({ currentSessionId: data.session_id });
            await get().fetchSessions();
            return data.session_id;
          }
          return null;
        } catch (error) {
          console.error('Failed to create session:', error);
          return null;
        }
      },

      deleteSession: async (sessionId: string) => {
        try {
          await api.deleteSession(sessionId);
          const { currentSessionId } = get();
          if (currentSessionId === sessionId) {
            set({ currentSessionId: null });
          }
          await get().fetchSessions();
        } catch (error) {
          console.error('Failed to delete session:', error);
          throw error;
        }
      },

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
);
