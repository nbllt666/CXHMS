import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { formatDate, truncate, getImportanceColor } from '../lib/utils';
import { PageHeader } from '../components/layout';
import { Button, Card, CardBody, Input, Badge, Modal, Textarea, Drawer } from '../components/ui';
import { useHotkey } from '../hooks';
import { GraphManager } from '../components/GraphManager';

import type { Memory } from '../types';

// F8: Memory 类型统一到 types/，此处不再重复声明。

type ViewMode = 'card' | 'list';

export function MemoriesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'memories' | 'graph' | 'diary' | 'acp'>('memories');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'long_term' | 'short_term' | 'permanent'>(
    'all'
  );
  const [currentAgentId, setCurrentAgentId] = useState('default');
  const [viewMode, setViewMode] = useState<ViewMode>('card');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDetailDrawer, setShowDetailDrawer] = useState(false);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [newMemory, setNewMemory] = useState({
    content: '',
    type: 'long_term',
    importance: 3,
    tags: '',
  });

  const [selectedMemories, setSelectedMemories] = useState<Set<number>>(new Set());
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [showBatchTagModal, setShowBatchTagModal] = useState(false);
  const [batchTags, setBatchTags] = useState('');
  const [batchTagOperation, setBatchTagOperation] = useState<'add' | 'remove' | 'set'>('add');

  // 类型标签移入组件以支持 i18n
  const typeLabels: Record<string, string> = {
    permanent: t('memory.typePermanent'),
    long_term: t('memory.typeLongTerm'),
    short_term: t('memory.typeShortTerm'),
  };

  // 重要性标签本地化（替代 lib/utils 的 getImportanceLabel，后者返回中文）
  const getImportanceText = (importance: number): string => {
    const labels: Record<number, string> = {
      1: t('memory.importanceVeryLow'),
      2: t('memory.importanceLow'),
      3: t('memory.importanceMedium'),
      4: t('memory.importanceHigh'),
      5: t('memory.importanceVeryHigh'),
    };
    return labels[importance] ?? t('memory.importanceUnknown');
  };

  useHotkey('Escape', () => {
    if (showDetailDrawer) setShowDetailDrawer(false);
    if (showAddModal) setShowAddModal(false);
    if (showEditModal) setShowEditModal(false);
  });

  const { data: agentsList } = useQuery({
    queryKey: ['agents-for-memory'],
    queryFn: () => api.getAgents(),
    staleTime: 60000,
  });

  const { data: memories, isLoading } = useQuery({
    queryKey: ['memories', filterType, currentAgentId],
    queryFn: async () => {
      const result = await api.getMemories({
        type: filterType === 'all' ? undefined : filterType,
        limit: 1000,
        agent_id: currentAgentId,
      });
      return result;
    },
    // F9: 移除 5s 强轮询，改为 invalidate-on-mutation（见各 mutation onSuccess）
  });

  const { data: diaryData, isLoading: isDiaryLoading } = useQuery({
    queryKey: ['diaryEntries', currentAgentId],
    queryFn: () => api.getDiaryEntries({ limit: 200, agent_id: currentAgentId }),
    enabled: activeTab === 'diary',
    staleTime: 30000,
  });

  // ACP 消息历史（按当前选择的 agent 查询其收到的 ACP 消息）
  const { data: acpMessagesData, isLoading: isAcpLoading } = useQuery({
    queryKey: ['acpMessages', currentAgentId],
    queryFn: () => api.getAcpMessages(currentAgentId, 200),
    enabled: activeTab === 'acp',
    staleTime: 30000,
  });

  // ACP 消息输入与发送
  const [acpInput, setAcpInput] = useState('');
  const sendAcpMessageMutation = useMutation({
    mutationFn: ({ toAgentId, message }: { toAgentId: string; message: string }) =>
      api.sendAcpMessage(toAgentId, message),
    onSuccess: () => {
      setAcpInput('');
      // 刷新消息历史；延迟 5s 再刷一次以拉取自动回复
      queryClient.invalidateQueries({ queryKey: ['acpMessages', currentAgentId] });
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['acpMessages', currentAgentId] });
      }, 5000);
    },
  });

  const handleSendAcpMessage = () => {
    const text = acpInput.trim();
    if (!text) return;
    sendAcpMessageMutation.mutate({ toAgentId: currentAgentId, message: text });
  };

  const handleCreateMemory = async () => {
    try {
      await api.createMemory({
        content: newMemory.content,
        type: newMemory.type,
        importance: newMemory.importance,
        tags: newMemory.tags
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
        agent_id: currentAgentId,
      });
      setShowAddModal(false);
      setNewMemory({ content: '', type: 'long_term', importance: 3, tags: '' });
      queryClient.invalidateQueries({ queryKey: ['memories'] });
    } catch (error) {
      console.error('创建记忆失败:', error);
    }
  };

  const handleDeleteMemory = async (id: number) => {
    if (!confirm(t('memory.confirmDelete'))) return;
    try {
      await api.deleteMemory(id);
      queryClient.invalidateQueries({ queryKey: ['memories'] });
    } catch (error) {
      console.error('删除记忆失败:', error);
    }
  };

  const handleArchiveMemory = async (id: number) => {
    try {
      await api.archiveMemory(id);
      queryClient.invalidateQueries({ queryKey: ['memories'] });
    } catch (error) {
      console.error('归档记忆失败:', error);
    }
  };

  const handleEditMemory = (memory: Memory) => {
    setEditingMemory(memory);
    setShowEditModal(true);
  };

  const handleViewMemory = (memory: Memory) => {
    setSelectedMemory(memory);
    setShowDetailDrawer(true);
  };

  const handleUpdateMemory = async () => {
    if (!editingMemory) return;
    try {
      await api.updateMemory(editingMemory.id, {
        content: editingMemory.content,
        tags: editingMemory.tags,
        importance: editingMemory.importance,
      }, currentAgentId);
      setShowEditModal(false);
      setEditingMemory(null);
      queryClient.invalidateQueries({ queryKey: ['memories'] });
    } catch (error) {
      console.error('更新记忆失败:', error);
    }
  };

  const toggleMemorySelection = (id: number) => {
    const newSelected = new Set(selectedMemories);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedMemories(newSelected);
  };

  const selectAllMemories = () => {
    if (selectedMemories.size === filteredMemories.length) {
      setSelectedMemories(new Set());
    } else {
      setSelectedMemories(new Set(filteredMemories.map((m: Memory) => m.id)));
    }
  };

  const clearSelection = () => {
    setSelectedMemories(new Set());
    setIsBatchMode(false);
  };

  const batchDeleteMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchDeleteMemories(ids, currentAgentId),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      clearSelection();
      // 显示部分/全部失败的提示
      if (data?.status === 'error') {
        alert(t('memory.batchDeleteAllFailed', { count: data?.result?.failed ?? 0 }));
      } else if (data?.status === 'partial') {
        alert(t('memory.batchDeletePartial', { failed: data?.result?.failed ?? 0, success: data?.result?.success ?? 0 }));
      }
    },
  });

  const batchArchiveMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchArchiveMemories(ids, currentAgentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      clearSelection();
    },
  });

  const batchUpdateTagsMutation = useMutation({
    mutationFn: ({
      ids,
      tags,
      operation,
    }: {
      ids: number[];
      tags: string[];
      operation: 'add' | 'remove' | 'set';
    }) => api.batchUpdateTags(ids, tags, operation),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      setShowBatchTagModal(false);
      setBatchTags('');
      clearSelection();
    },
  });

  const handleBatchDelete = () => {
    if (selectedMemories.size === 0) return;
    if (!confirm(t('memory.confirmBatchDelete', { count: selectedMemories.size }))) return;
    batchDeleteMutation.mutate(Array.from(selectedMemories));
  };

  const handleBatchArchive = () => {
    if (selectedMemories.size === 0) return;
    batchArchiveMutation.mutate(Array.from(selectedMemories));
  };

  const handleBatchUpdateTags = () => {
    if (selectedMemories.size === 0) return;
    const tags = batchTags
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);
    if (tags.length === 0) return;
    batchUpdateTagsMutation.mutate({
      ids: Array.from(selectedMemories),
      tags,
      operation: batchTagOperation,
    });
  };

  const filteredMemories =
    memories?.memories?.filter((memory: Memory) => {
      if (!searchQuery) return true;
      return (
        memory.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (memory.tags &&
          memory.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase())))
      );
    }) || [];

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <PageHeader
          title={t('memory.title')}
          description={t('memory.pageDescription')}
        />
        <div className="flex items-center gap-3">
          <div className="flex bg-[var(--color-bg-tertiary)] rounded-[var(--radius-md)] p-1">
            <button
              onClick={() => setActiveTab('memories')}
              className={`px-4 py-1.5 text-sm rounded-[var(--radius-sm)] transition-colors ${
                activeTab === 'memories'
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {t('memory.tabMemories')}
            </button>
            <button
              onClick={() => setActiveTab('diary')}
              className={`px-4 py-1.5 text-sm rounded-[var(--radius-sm)] transition-colors ${
                activeTab === 'diary'
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {t('memory.tabDiary')}
            </button>
            <button
              onClick={() => setActiveTab('graph')}
              className={`px-4 py-1.5 text-sm rounded-[var(--radius-sm)] transition-colors ${
                activeTab === 'graph'
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {t('memory.tabGraph')}
            </button>
            <button
              onClick={() => setActiveTab('acp')}
              className={`px-4 py-1.5 text-sm rounded-[var(--radius-sm)] transition-colors ${
                activeTab === 'acp'
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {t('memory.tabAcp')}
            </button>
          </div>
          {activeTab === 'memories' && (
            <Button onClick={() => setShowAddModal(true)}>
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              {t('memory.newMemory')}
            </Button>
          )}
        </div>
      </div>

      {activeTab === 'graph' ? (
        <GraphManager />
      ) : activeTab === 'diary' ? (
        <>
          <div className="flex items-center justify-end mb-4">
            <label className="text-sm text-[var(--color-text-secondary)] mr-2">
              {t('memory.agent')}:
            </label>
            <select
              value={currentAgentId}
              onChange={(e) => {
                setCurrentAgentId(e.target.value);
              }}
              className="px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm"
            >
              <option value="default">{t('memory.defaultAgent')}</option>
              {agentsList?.agents
                ?.filter((a: { id: string }) => a.id !== 'default')
                .map((agent: { id: string; name: string }) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name || agent.id}
                  </option>
                ))}
            </select>
          </div>
          <DiaryView
            diaryData={diaryData}
            isLoading={isDiaryLoading}
          />
        </>
      ) : activeTab === 'acp' ? (
        <>
          <div className="flex items-center justify-end mb-4">
            <label className="text-sm text-[var(--color-text-secondary)] mr-2">
              {t('memory.agent')}:
            </label>
            <select
              value={currentAgentId}
              onChange={(e) => {
                setCurrentAgentId(e.target.value);
              }}
              className="px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm"
            >
              <option value="default">{t('memory.defaultAgent')}</option>
              {agentsList?.agents
                ?.filter((a: { id: string }) => a.id !== 'default')
                .map((agent: { id: string; name: string }) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name || agent.id}
                  </option>
                ))}
            </select>
          </div>
          {isAcpLoading ? (
            <div className="text-center py-12 text-[var(--color-text-secondary)]">
              {t('common.loading')}
            </div>
          ) : acpMessagesData?.messages?.length ? (
            <div className="space-y-3">
              {acpMessagesData.messages
                .slice()
                .reverse()
                .map((msg) => {
                  const isFromCurrent = msg.from_agent_id === currentAgentId;
                  const contentText =
                    typeof msg.content === 'string'
                      ? msg.content
                      : (msg.content?.text as string) ||
                        (msg.content?.message as string) ||
                        JSON.stringify(msg.content);
                  return (
                    <div
                      key={msg.id}
                      className={`flex ${isFromCurrent ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[75%] rounded-[var(--radius-md)] px-4 py-3 ${
                          isFromCurrent
                            ? 'bg-[var(--color-accent)] text-white'
                            : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)]'
                        }`}
                      >
                        <div className="text-xs opacity-70 mb-1">
                          {isFromCurrent
                            ? `${t('memory.acpSentTo')} ${msg.to_agent_id || ''}`
                            : `${t('memory.acpReceivedFrom')} ${msg.from_agent_name || msg.from_agent_id}`}
                          <span className="ml-2">{formatDate(msg.timestamp)}</span>
                          {msg.is_sent && (
                            <span className="ml-2 px-1.5 py-0.5 text-[10px] bg-black/10 rounded">
                              {t('memory.acpSent')}
                            </span>
                          )}
                        </div>
                        <div className="whitespace-pre-wrap break-words">{contentText}</div>
                      </div>
                    </div>
                  );
                })}
            </div>
          ) : (
            <div className="text-center py-12 text-[var(--color-text-secondary)]">
              {t('memory.acpEmpty')}
            </div>
          )}

          {/* ACP 消息发送区：无论有无消息历史都显示，便于主动发起对话 */}
          <div className="mt-6 pt-4 border-t border-[var(--color-border)]">
            <div className="flex items-center gap-2">
              <input
                value={acpInput}
                onChange={(e) => setAcpInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendAcpMessage();
                  }
                }}
                placeholder={
                  currentAgentId === 'default'
                    ? t('memory.acpInputPlaceholderDisabled')
                    : t('memory.acpInputPlaceholder', { agent: currentAgentId })
                }
                disabled={sendAcpMessageMutation.isPending || currentAgentId === 'default'}
                className="flex-1 px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm focus:outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
              />
              <Button
                onClick={handleSendAcpMessage}
                disabled={
                  sendAcpMessageMutation.isPending ||
                  !acpInput.trim() ||
                  currentAgentId === 'default'
                }
              >
                {sendAcpMessageMutation.isPending
                  ? t('common.sending')
                  : t('memory.acpSend')}
              </Button>
            </div>
            {sendAcpMessageMutation.isError && (
              <div className="mt-2 text-xs text-[var(--color-error)]">
                {t('memory.acpSendError')}
              </div>
            )}
            {currentAgentId === 'default' && (
              <div className="mt-2 text-xs text-[var(--color-text-secondary)]">
                {t('memory.acpSelectAgentFirst')}
              </div>
            )}
          </div>
        </>
      ) : (
      <>
      <div className="flex items-center gap-4 mb-6">
        <div className="flex-1">
          <Input
            placeholder={t('memory.searchContentPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full"
          />
        </div>

        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as typeof filterType)}
          className="px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm"
        >
          <option value="all">{t('memory.filterAllTypes')}</option>
          <option value="permanent">{t('memory.permanentMemory')}</option>
          <option value="long_term">{t('memory.longTermMemory')}</option>
          <option value="short_term">{t('memory.shortTermMemory')}</option>
        </select>

        <select
          value={currentAgentId}
          onChange={(e) => {
            setCurrentAgentId(e.target.value);
            clearSelection();
          }}
          className="px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm"
        >
          <option value="default">{t('memory.defaultAgent')}</option>
          {agentsList?.agents
            ?.filter((a: { id: string }) => a.id !== 'default')
            .map((agent: { id: string; name: string }) => (
              <option key={agent.id} value={agent.id}>
                {agent.name || agent.id}
              </option>
            ))}
        </select>

        <div className="flex items-center border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
          <button
            onClick={() => setViewMode('card')}
            className={`px-3 py-2 text-sm ${viewMode === 'card' ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-primary)]'}`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
              />
            </svg>
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={`px-3 py-2 text-sm ${viewMode === 'list' ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-primary)]'}`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 10h16M4 14h16M4 18h16"
              />
            </svg>
          </button>
        </div>

        <Button
          variant={isBatchMode ? 'primary' : 'secondary'}
          onClick={() => {
            setIsBatchMode(!isBatchMode);
            if (isBatchMode) clearSelection();
          }}
        >
          {isBatchMode ? t('memory.exitBatch') : t('memory.batchMode')}
        </Button>
      </div>

      {isBatchMode && (
        <Card className="mb-4 p-3 bg-[var(--color-accent-light)]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" onClick={selectAllMemories}>
                {selectedMemories.size === filteredMemories.length ? t('memory.deselectAll') : t('memory.selectAll')}
                <span className="ml-2 text-[var(--color-text-secondary)]">
                  ({selectedMemories.size}/{filteredMemories.length})
                </span>
              </Button>
            </div>
            <div className="flex items-center gap-2">
              {selectedMemories.size > 0 && (
                <>
                  <Button variant="secondary" size="sm" onClick={() => setShowBatchTagModal(true)}>
                    {t('memory.batchTags')}
                  </Button>
                  <Button variant="secondary" size="sm" onClick={handleBatchArchive}>
                    {t('memory.archiveAction')}
                  </Button>
                  <Button variant="danger" size="sm" onClick={handleBatchDelete}>
                    {t('common.delete')}
                  </Button>
                </>
              )}
            </div>
          </div>
        </Card>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin w-8 h-8 border-2 border-[var(--color-accent)] border-t-transparent rounded-full" />
        </div>
      ) : filteredMemories.length === 0 ? (
        <Card className="py-12 text-center">
          <div className="text-[var(--color-text-tertiary)]">
            <svg
              className="w-16 h-16 mx-auto mb-4 opacity-50"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
              />
            </svg>
            <h3 className="text-lg font-medium mb-2">{t('memory.noMemories')}</h3>
            <p className="text-sm">{t('memory.noMemoriesHint')}</p>
          </div>
        </Card>
      ) : viewMode === 'card' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredMemories.map((memory: Memory) => (
            <Card
              key={memory.id}
              className={`cursor-pointer transition-all hover:shadow-lg ${
                memory.is_archived ? 'opacity-60' : ''
              } ${isBatchMode && selectedMemories.has(memory.id) ? 'ring-2 ring-[var(--color-accent)]' : ''}`}
              onClick={() => {
                if (isBatchMode) {
                  toggleMemorySelection(memory.id);
                } else {
                  handleViewMemory(memory);
                }
              }}
            >
              <CardBody>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{
                        backgroundColor: `var(--color-${getImportanceColor(memory.importance).replace('bg-', '')})`,
                      }}
                    />
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      {getImportanceText(memory.importance)}
                    </span>
                    <Badge variant="secondary" size="sm">
                      {typeLabels[memory.type] || memory.type}
                    </Badge>
                  </div>
                  {!isBatchMode && (
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleArchiveMemory(memory.id)}
                        className="p-1.5 hover:bg-[var(--color-bg-hover)] rounded-[var(--radius-sm)] transition-colors"
                        title={t('memory.archiveAction')}
                      >
                        <svg
                          className="w-4 h-4 text-[var(--color-text-secondary)]"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
                          />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleEditMemory(memory)}
                        className="p-1.5 hover:bg-[var(--color-bg-hover)] rounded-[var(--radius-sm)] transition-colors"
                        title={t('common.edit')}
                      >
                        <svg
                          className="w-4 h-4 text-[var(--color-text-secondary)]"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                          />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleDeleteMemory(memory.id)}
                        className="p-1.5 hover:bg-[var(--color-error-light)] rounded-[var(--radius-sm)] transition-colors"
                        title={t('common.delete')}
                      >
                        <svg
                          className="w-4 h-4 text-[var(--color-error)]"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
                <p className="text-sm text-[var(--color-text-primary)] mb-3 line-clamp-4">
                  {truncate(memory.content, 200)}
                </p>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1 flex-wrap">
                    {memory.tags?.slice(0, 3).map((tag) => (
                      <Badge key={tag} variant="primary" size="sm">
                        {tag}
                      </Badge>
                    ))}
                    {memory.tags && memory.tags.length > 3 && (
                      <span className="text-xs text-[var(--color-text-tertiary)]">
                        +{memory.tags.length - 3}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-[var(--color-text-tertiary)]">
                    {formatDate(memory.created_at)}
                  </span>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardBody className="p-0">
            <table className="w-full">
              <thead className="bg-[var(--color-bg-tertiary)]">
                <tr>
                  {isBatchMode && (
                    <th className="w-10 px-4 py-3 text-left">
                      <input
                        type="checkbox"
                        checked={selectedMemories.size === filteredMemories.length}
                        onChange={selectAllMemories}
                        className="rounded"
                      />
                    </th>
                  )}
                  <th className="px-4 py-3 text-left text-sm font-medium text-[var(--color-text-secondary)]">
                    {t('common.content')}
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-[var(--color-text-secondary)] w-24">
                    {t('common.type')}
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-[var(--color-text-secondary)] w-24">
                    {t('memory.importance')}
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-[var(--color-text-secondary)] w-32">
                    {t('memory.tags')}
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-[var(--color-text-secondary)] w-32">
                    {t('common.createdAt')}
                  </th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-[var(--color-text-secondary)] w-32">
                    {t('common.actions')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {filteredMemories.map((memory: Memory) => (
                  <tr
                    key={memory.id}
                    className={`hover:bg-[var(--color-bg-hover)] cursor-pointer ${
                      isBatchMode && selectedMemories.has(memory.id)
                        ? 'bg-[var(--color-accent-light)]'
                        : ''
                    }`}
                    onClick={() => {
                      if (isBatchMode) {
                        toggleMemorySelection(memory.id);
                      } else {
                        handleViewMemory(memory);
                      }
                    }}
                  >
                    {isBatchMode && (
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedMemories.has(memory.id)}
                          onChange={() => toggleMemorySelection(memory.id)}
                          className="rounded"
                        />
                      </td>
                    )}
                    <td className="px-4 py-3 text-sm truncate max-w-xs">
                      {truncate(memory.content, 100)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="secondary" size="sm">
                        {typeLabels[memory.type] || memory.type}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-sm">{getImportanceText(memory.importance)}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {memory.tags?.slice(0, 2).map((tag) => (
                          <Badge key={tag} variant="primary" size="sm">
                            {tag}
                          </Badge>
                        ))}
                        {memory.tags && memory.tags.length > 2 && (
                          <span className="text-xs text-[var(--color-text-tertiary)]">
                            +{memory.tags.length - 2}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-[var(--color-text-secondary)]">
                      {formatDate(memory.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div
                        className="flex items-center justify-end gap-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => handleEditMemory(memory)}
                          className="p-1.5 hover:bg-[var(--color-bg-hover)] rounded-[var(--radius-sm)]"
                        >
                          <svg
                            className="w-4 h-4 text-[var(--color-text-secondary)]"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                            />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDeleteMemory(memory.id)}
                          className="p-1.5 hover:bg-[var(--color-error-light)] rounded-[var(--radius-sm)]"
                        >
                          <svg
                            className="w-4 h-4 text-[var(--color-error)]"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      )}

      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title={t('memory.newMemory')}>
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-1.5 block">{t('common.content')}</label>
            <Textarea
              value={newMemory.content}
              onChange={(e) => setNewMemory({ ...newMemory, content: e.target.value })}
              placeholder={t('memory.contentPlaceholder')}
              className="min-h-[100px]"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">{t('common.type')}</label>
              <select
                value={newMemory.type}
                onChange={(e) => setNewMemory({ ...newMemory, type: e.target.value })}
                className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
              >
                <option value="long_term">{t('memory.longTermMemory')}</option>
                <option value="short_term">{t('memory.shortTermMemory')}</option>
                <option value="permanent">{t('memory.permanentMemory')}</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">{t('memory.importance')}</label>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    onClick={() => setNewMemory({ ...newMemory, importance: star })}
                    className="p-1"
                  >
                    <svg
                      className={`w-5 h-5 ${star <= newMemory.importance ? 'fill-yellow-400 text-yellow-400' : 'text-[var(--color-text-tertiary)]'}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                      />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div>
            <label className="text-sm font-medium mb-1.5 block">{t('memory.tagsLabel')}</label>
            <Input
              value={newMemory.tags}
              onChange={(e) => setNewMemory({ ...newMemory, tags: e.target.value })}
              placeholder={t('memory.tagsPlaceholder')}
            />
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleCreateMemory} disabled={!newMemory.content.trim()}>
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal isOpen={showEditModal} onClose={() => setShowEditModal(false)} title={t('memory.edit')}>
        {editingMemory && (
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">{t('common.content')}</label>
              <Textarea
                value={editingMemory.content}
                onChange={(e) => setEditingMemory({ ...editingMemory, content: e.target.value })}
                className="min-h-[100px]"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">{t('memory.importance')}</label>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    onClick={() => setEditingMemory({ ...editingMemory, importance: star })}
                    className="p-1"
                  >
                    <svg
                      className={`w-5 h-5 ${star <= editingMemory.importance ? 'fill-yellow-400 text-yellow-400' : 'text-[var(--color-text-tertiary)]'}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                      />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">{t('memory.tagsLabel')}</label>
              <Input
                value={editingMemory.tags.join(', ')}
                onChange={(e) =>
                  setEditingMemory({
                    ...editingMemory,
                    tags: e.target.value
                      .split(',')
                      .map((tag) => tag.trim())
                      .filter(Boolean),
                  })
                }
              />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <Button variant="secondary" onClick={() => setShowEditModal(false)}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleUpdateMemory}>{t('common.save')}</Button>
            </div>
          </div>
        )}
      </Modal>

      <Drawer isOpen={showDetailDrawer} onClose={() => setShowDetailDrawer(false)} title={t('memory.detailTitle')}>
        {selectedMemory && (
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">{t('common.content')}</h3>
              <p className="text-[var(--color-text-primary)] whitespace-pre-wrap">
                {selectedMemory.content}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">
                  {t('common.type')}
                </h3>
                <Badge variant="secondary">
                  {typeLabels[selectedMemory.type] || selectedMemory.type}
                </Badge>
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">
                  {t('memory.importance')}
                </h3>
                <span>{getImportanceText(selectedMemory.importance)}</span>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">{t('memory.tags')}</h3>
              <div className="flex gap-2 flex-wrap">
                {selectedMemory.tags?.map((tag) => (
                  <Badge key={tag} variant="primary">
                    {tag}
                  </Badge>
                ))}
                {(!selectedMemory.tags || selectedMemory.tags.length === 0) && (
                  <span className="text-[var(--color-text-tertiary)]">{t('memory.noTags')}</span>
                )}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">
                {t('common.createdAt')}
              </h3>
              <span className="text-[var(--color-text-primary)]">
                {formatDate(selectedMemory.created_at)}
              </span>
            </div>
            <div className="flex gap-2 pt-4 border-t border-[var(--color-border)]">
              <Button
                variant="secondary"
                onClick={() => {
                  setShowDetailDrawer(false);
                  handleEditMemory(selectedMemory);
                }}
              >
                {t('common.edit')}
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  handleArchiveMemory(selectedMemory.id);
                  setShowDetailDrawer(false);
                }}
              >
                {t('memory.archiveAction')}
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  handleDeleteMemory(selectedMemory.id);
                  setShowDetailDrawer(false);
                }}
              >
                {t('common.delete')}
              </Button>
            </div>
          </div>
        )}
      </Drawer>

      <Modal
        isOpen={showBatchTagModal}
        onClose={() => setShowBatchTagModal(false)}
        title={t('memory.batchUpdateTagsTitle')}
      >
        <div className="space-y-4">
          <p className="text-sm text-[var(--color-text-secondary)]">
            {t('memory.batchTagOperationDesc', { count: selectedMemories.size })}
          </p>
          <div>
            <label className="text-sm font-medium mb-1.5 block">{t('memory.operationType')}</label>
            <select
              value={batchTagOperation}
              onChange={(e) => setBatchTagOperation(e.target.value as typeof batchTagOperation)}
              className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
            >
              <option value="add">{t('memory.addTags')}</option>
              <option value="remove">{t('memory.removeTags')}</option>
              <option value="set">{t('memory.setTags')}</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium mb-1.5 block">{t('memory.tagsLabel')}</label>
            <Input
              value={batchTags}
              onChange={(e) => setBatchTags(e.target.value)}
              placeholder={t('memory.tagsPlaceholder')}
            />
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setShowBatchTagModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleBatchUpdateTags} disabled={!batchTags.trim()}>
              {t('common.confirm')}
            </Button>
          </div>
        </div>
      </Modal>
      </>
      )}
    </div>
  );
}

// ========== 记录视图组件 ==========

interface DiaryEntry {
  id: number;
  content: string;
  metadata?: {
    date?: string;
    title?: string;
    mood?: string;
    body?: string;
    summarized_message_range?: string;
    source?: string;
  };
  created_at: string;
}

interface DiaryGroup {
  date: string;
  entries: DiaryEntry[];
}

interface DiaryViewProps {
  diaryData?: { diary_groups?: DiaryGroup[]; count?: number };
  isLoading: boolean;
}

interface TimelineEntry extends DiaryEntry {
  groupDate: string;
}

function DiaryView({ diaryData, isLoading }: DiaryViewProps) {
  const { t } = useTranslation();
  const [expandedEntryIds, setExpandedEntryIds] = useState<Set<number>>(new Set());

  const groups = diaryData?.diary_groups || [];

  // Flatten date-grouped entries into a single list sorted by created_at descending.
  // The API already returns groups in date-descending order, but we re-sort defensively.
  const allEntries: TimelineEntry[] = groups
    .flatMap((group) =>
      group.entries.map((entry) => ({ ...entry, groupDate: group.date }))
    )
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );

  const toggleEntry = (id: number) => {
    setExpandedEntryIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin w-8 h-8 border-2 border-[var(--color-accent)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (allEntries.length === 0) {
    return (
      <Card className="py-12 text-center">
        <div className="text-[var(--color-text-tertiary)]">
          <svg
            className="w-16 h-16 mx-auto mb-4 opacity-50"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
          <h3 className="text-lg font-medium mb-2">{t('memory.noDiary')}</h3>
          <p className="text-sm">{t('memory.noDiaryHint')}</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="relative pl-8">
      {/* Vertical timeline connector line */}
      <div className="absolute left-[7px] top-3 bottom-3 w-px bg-[var(--color-border)]" />

      <div className="space-y-4">
        {allEntries.map((entry) => {
          const meta = entry.metadata || {};
          const isExpanded = expandedEntryIds.has(entry.id);
          const hasExpandableDetail = Boolean(
            meta.body || meta.summarized_message_range
          );
          const previewBody = meta.body ?? entry.content;

          return (
            <div key={entry.id} className="relative">
              {/* Timeline node dot */}
              <div
                className={`absolute -left-[1.95rem] top-4 w-3.5 h-3.5 rounded-full ring-4 ring-[var(--color-bg-primary)] transition-colors ${
                  isExpanded
                    ? 'bg-[var(--color-accent)]'
                    : 'bg-[var(--color-text-tertiary)]'
                }`}
              />

              <Card
                className={`transition-all hover:shadow-lg ${
                  hasExpandableDetail ? 'cursor-pointer' : ''
                } ${isExpanded ? 'ring-1 ring-[var(--color-accent)]' : ''}`}
                onClick={() => hasExpandableDetail && toggleEntry(entry.id)}
              >
                <CardBody>
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="text-xs font-medium text-[var(--color-text-secondary)]">
                      {entry.groupDate}
                    </span>
                    {meta.mood && (
                      <Badge variant="primary" size="sm">
                        {meta.mood}
                      </Badge>
                    )}
                    {meta.source && (
                      <span className="text-xs text-[var(--color-text-tertiary)]">
                        · {meta.source}
                      </span>
                    )}
                    {hasExpandableDetail && (
                      <svg
                        className={`w-4 h-4 ml-auto text-[var(--color-text-secondary)] transition-transform ${
                          isExpanded ? 'rotate-180' : ''
                        }`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 9l-7 7-7-7"
                        />
                      </svg>
                    )}
                  </div>

                  {meta.title && (
                    <h4 className="text-base font-semibold text-[var(--color-text-primary)] mb-1.5">
                      {meta.title}
                    </h4>
                  )}

                  <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed whitespace-pre-wrap">
                    {isExpanded ? previewBody : truncate(previewBody, 120)}
                  </p>

                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-[var(--color-border)] space-y-2">
                      {meta.summarized_message_range && (
                        <div className="flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
                          <span className="font-medium">{t('memory.messageRange')}</span>
                          <span>{meta.summarized_message_range}</span>
                        </div>
                      )}
                      <div className="flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
                        <svg
                          className="w-3.5 h-3.5"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                        <span className="font-medium">{t('memory.fullTime')}</span>
                        <span>{formatDate(entry.created_at)}</span>
                      </div>
                    </div>
                  )}
                </CardBody>
              </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
}
