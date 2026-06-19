﻿import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Bot,
  Users,
  MessageSquare,
  Activity,
  RefreshCw,
  Plus,
  Trash2,
  Loader2,
  Network,
} from 'lucide-react';
import { api } from '../api/client';
import { cn } from '../lib/utils';

interface AcpAgent {
  id: string;
  agent_id: string;
  name?: string;
  description?: string;
  status: 'active' | 'inactive' | 'error';
  capabilities?: string[];
  host: string;
  port: number;
  created_at: string;
  last_active?: string;
}

interface AcpStats {
  total_agents: number;
  active_agents: number;
  total_conversations: number;
  avg_response_time: number;
}

export function AcpPage() {
  const queryClient = useQueryClient();
  const [selectedAgent, setSelectedAgent] = useState<AcpAgent | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const { data: stats, isLoading: statsLoading } = useQuery<AcpStats>({
    queryKey: ['acp-stats'],
    queryFn: async () => {
      const response = await api.getAcpStats();
      return response;
    },
    refetchInterval: 10000,
  });

  const { data: agents, isLoading: agentsLoading } = useQuery<AcpAgent[]>({
    queryKey: ['acp-agents'],
    queryFn: async () => {
      const response = await api.getAcpAgents();
      return response.agents || [];
    },
    refetchInterval: 5000,
  });

  const createAgentMutation = useMutation({
    mutationFn: (data: { agent_id: string; host: string; port: number }) =>
      api.createAcpAgent(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['acp-agents'] });
      queryClient.invalidateQueries({ queryKey: ['acp-stats'] });
      setIsCreateModalOpen(false);
    },
  });

  const deleteAgentMutation = useMutation({
    mutationFn: api.deleteAcpAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['acp-agents'] });
      queryClient.invalidateQueries({ queryKey: ['acp-stats'] });
      setSelectedAgent(null);
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Network className="w-6 h-6 text-primary" />
            ACP 管理
          </h1>
          <p className="text-muted-foreground mt-1">管理 AI 代理和协调协议</p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          连接代理
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          title="总代理数"
          value={stats?.total_agents || 0}
          icon={Bot}
          loading={statsLoading}
        />
        <StatCard
          title="活跃代理"
          value={stats?.active_agents || 0}
          icon={Activity}
          loading={statsLoading}
          trend={
            stats
              ? `${stats.total_agents > 0 ? Math.round((stats.active_agents / stats.total_agents) * 100) : 0}%`
              : undefined
          }
        />
        <StatCard
          title="总会话数"
          value={stats?.total_conversations || 0}
          icon={MessageSquare}
          loading={statsLoading}
        />
        <StatCard
          title="平均响应时间"
          value={`${stats?.avg_response_time?.toFixed(2) || 0}ms`}
          icon={RefreshCw}
          loading={statsLoading}
        />
      </div>

      <div className="bg-card rounded-lg border border-border">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold flex items-center gap-2">
            <Users className="w-5 h-5" />
            代理列表
          </h2>
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['acp-agents'] })}
            className="p-2 hover:bg-accent rounded-lg transition-colors"
            title="刷新"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {agentsLoading ? (
          <div className="p-8 flex justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : agents && agents.length > 0 ? (
          <div className="divide-y divide-border">
            {agents.map((agent) => (
              <div
                key={agent.id}
                className={cn(
                  'p-4 hover:bg-accent/50 transition-colors cursor-pointer',
                  selectedAgent?.id === agent.id && 'bg-accent'
                )}
                onClick={() => setSelectedAgent(agent)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        'w-10 h-10 rounded-lg flex items-center justify-center',
                        agent.status === 'active'
                          ? 'bg-green-500/10'
                          : agent.status === 'error'
                            ? 'bg-red-500/10'
                            : 'bg-[var(--color-bg-tertiary)]'
                      )}
                    >
                      <Bot
                        className={cn(
                          'w-5 h-5',
                          agent.status === 'active'
                            ? 'text-green-500'
                            : agent.status === 'error'
                              ? 'text-red-500'
                              : 'text-[var(--color-text-tertiary)]'
                        )}
                      />
                    </div>
                    <div>
                      <h3 className="font-medium">{agent.name || agent.agent_id}</h3>
                      <p className="text-sm text-muted-foreground">
                        {agent.description || `${agent.host}:${agent.port}`}
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <span
                          className={cn(
                            'text-xs px-2 py-0.5 rounded-full',
                            agent.status === 'active'
                              ? 'bg-green-500/10 text-green-600'
                              : agent.status === 'error'
                                ? 'bg-red-500/10 text-red-600'
                                : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-tertiary)]'
                          )}
                        >
                          {agent.status === 'active'
                            ? '活跃'
                            : agent.status === 'error'
                              ? '错误'
                              : '停用'}
                        </span>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600">
                          {agent.host}:{agent.port}
                        </span>
                        {agent.capabilities?.map((cap) => (
                          <span
                            key={cap}
                            className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary"
                          >
                            {cap}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm('确定要断开此代理吗？')) {
                          deleteAgentMutation.mutate(agent.id);
                        }
                      }}
                      className="p-2 hover:bg-red-500/10 hover:text-red-500 rounded-lg transition-colors"
                      title="断开连接"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center text-muted-foreground">
            <Bot className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>暂无代理</p>
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="mt-4 text-primary hover:underline"
            >
              连接第一个代理
            </button>
          </div>
        )}
      </div>

      {isCreateModalOpen && (
        <AcpAgentModal
          title="连接 ACP 代理"
          onClose={() => setIsCreateModalOpen(false)}
          onSubmit={(data) => createAgentMutation.mutate(data)}
          isLoading={createAgentMutation.isPending}
        />
      )}
    </div>
  );
}

function StatCard({
  title,
  value,
  icon: Icon,
  loading,
  trend,
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  loading?: boolean;
  trend?: string;
}) {
  return (
    <div className="bg-card p-4 rounded-lg border border-border">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          {loading ? (
            <Loader2 className="w-6 h-6 animate-spin mt-2" />
          ) : (
            <div className="flex items-baseline gap-2">
              <p className="text-2xl font-bold mt-1">{value}</p>
              {trend && <span className="text-xs text-green-500">{trend}</span>}
            </div>
          )}
        </div>
        <div className="p-2 bg-primary/10 rounded-lg">
          <Icon className="w-5 h-5 text-primary" />
        </div>
      </div>
    </div>
  );
}

interface AcpAgentModalProps {
  title: string;
  onClose: () => void;
  onSubmit: (data: { agent_id: string; host: string; port: number }) => void;
  isLoading: boolean;
}

function AcpAgentModal({ title, onClose, onSubmit, isLoading }: AcpAgentModalProps) {
  const [formData, setFormData] = useState({
    agent_id: '',
    host: 'localhost',
    port: 8000,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      agent_id: formData.agent_id,
      host: formData.host,
      port: formData.port,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-lg border border-border w-full max-w-md p-6">
        <h2 className="text-xl font-semibold mb-4">{title}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">代理 ID <span className="text-red-500">*</span></label>
            <input
              type="text"
              value={formData.agent_id}
              onChange={(e) => setFormData({ ...formData, agent_id: e.target.value })}
              className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="my-agent"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">主机地址 <span className="text-red-500">*</span></label>
            <input
              type="text"
              value={formData.host}
              onChange={(e) => setFormData({ ...formData, host: e.target.value })}
              className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="localhost"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">端口 <span className="text-red-500">*</span></label>
            <input
              type="number"
              value={formData.port}
              onChange={(e) => setFormData({ ...formData, port: Math.max(1, Math.min(65535, parseInt(e.target.value) || 1)) })}
              className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="8000"
              min={1}
              max={65535}
              required
            />
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-muted-foreground hover:text-foreground transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              连接
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
