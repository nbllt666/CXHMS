import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import { useChatStore } from '../store/chatStore';
import { formatRelativeTime } from '../lib/utils';
import { PageHeader } from '../components/layout';
import { Button, Card, CardBody, Modal, Input, Textarea, Badge } from '../components/ui';
import { useHotkey } from '../hooks';

import type { Agent, AgentTemplate } from '../types';

// F8: Agent / AgentTemplate 类型统一到 types/，此处不再重复声明。

export function AgentsPage() {
  const { t } = useTranslation();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [availableModels, setAvailableModels] = useState<{ name: string }[]>([]);
  const [providers, setProviders] = useState<{ id: string; name: string; provider: string }[]>([]);

  // 模板移入组件以支持 i18n；system_prompt 为 LLM 指令，保留原文不翻译
  const AGENT_TEMPLATES: AgentTemplate[] = [
    {
      id: 'general',
      name: t('agent.templates.general.name'),
      description: t('agent.templates.general.desc'),
      icon: '🤖',
      system_prompt: '你是一个有帮助的AI助手。请用中文回答用户的问题，保持友好和专业。当用户分享重要信息时，主动记住；当用户询问之前的内容时，主动搜索回忆。',
      temperature: 0.7,
      memory_scene: 'chat',
    },
    {
      id: 'coder',
      name: t('agent.templates.coder.name'),
      description: t('agent.templates.coder.desc'),
      icon: '💻',
      system_prompt:
        '你是一个专业的编程助手。帮助用户编写、调试和优化代码。提供清晰的代码示例和解释，遵循最佳实践。用中文回答问题，代码注释使用英文。',
      temperature: 0.3,
      memory_scene: 'task',
    },
    {
      id: 'writer',
      name: t('agent.templates.writer.name'),
      description: t('agent.templates.writer.desc'),
      icon: '✍️',
      system_prompt:
        '你是一个专业的写作助手。帮助用户撰写各类文章、文案、故事等。注重文字的流畅性、逻辑性和创意表达。用中文回复。',
      temperature: 0.8,
      memory_scene: 'chat',
    },
    {
      id: 'analyst',
      name: t('agent.templates.analyst.name'),
      description: t('agent.templates.analyst.desc'),
      icon: '📊',
      system_prompt:
        '你是一个数据分析专家。帮助用户分析数据、生成报告、提供洞察。善于使用工具进行数据处理和计算。用中文回复。',
      temperature: 0.4,
      memory_scene: 'task',
    },
    {
      id: 'translator',
      name: t('agent.templates.translator.name'),
      description: t('agent.templates.translator.desc'),
      icon: '🌐',
      system_prompt:
        '你是一个专业的翻译助手。准确翻译各种语言，保持原文的风格和语境。支持中文、英文、日文等多种语言。翻译时保持自然流畅。',
      temperature: 0.5,
      memory_scene: 'chat',
    },
    {
      id: 'vision',
      name: t('agent.templates.vision.name'),
      description: t('agent.templates.vision.desc'),
      icon: '👁️',
      system_prompt:
        '你是一个支持视觉理解的AI助手。可以分析图像内容，回答关于图片的问题，并提供视觉相关的建议。用中文回复。',
      temperature: 0.7,
      memory_scene: 'chat',
    },
  ];

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    system_prompt: '你是一个有帮助的AI助手。请用中文回答用户的问题。',
    model: '',
    temperature: 0.7,
    max_tokens: 0,
    memory_scene: 'chat',
    decay_model: 'exponential',
  });

  useHotkey('Escape', () => {
    if (showCreateModal) setShowCreateModal(false);
    if (showTemplateModal) setShowTemplateModal(false);
    if (editingAgent) {
      setEditingAgent(null);
      resetForm();
    }
  });

  useEffect(() => {
    loadAgents();
    loadModels();
  }, []);

  const loadModels = async () => {
    try {
      const data = await api.getAvailableModels();
      if (data.providers) {
        setProviders(data.providers);
      }
      if (data.ollama_models) {
        setAvailableModels(data.ollama_models);
      }
    } catch (error) {
      console.error('加载模型列表失败:', error);
    }
  };

  const loadAgents = async () => {
    try {
      setLoading(true);
      const data = await api.getAgents();
      const agentsList = data.agents || [];
      const filteredAgents = agentsList.filter((agent: Agent) => agent.id !== 'memory-agent');
      setAgents(filteredAgents);
    } catch (error) {
      console.error('加载 Agent 失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      await api.createAgent({
        ...formData,
        model: 'main',
        use_memory: true,
        use_tools: true,
        vision_enabled: true,
      });
      setShowCreateModal(false);
      resetForm();
      loadAgents();
      useChatStore.getState().fetchAgents();
    } catch (error) {
      console.error('创建 Agent 失败:', error);
      alert(t('agent.createFailed'));
    }
  };

  const handleUpdate = async () => {
    if (!editingAgent) return;
    try {
      await api.updateAgent(editingAgent.id, {
        ...formData,
        model: 'main',
        use_memory: true,
        use_tools: true,
        vision_enabled: true,
      });
      setEditingAgent(null);
      resetForm();
      loadAgents();
      useChatStore.getState().fetchAgents();
    } catch (error) {
      console.error('更新 Agent 失败:', error);
      alert(t('agent.updateFailed'));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t('agent.confirmDelete'))) return;
    try {
      await api.deleteAgent(id);
      loadAgents();
      useChatStore.getState().fetchAgents();
    } catch (error) {
      console.error('删除 Agent 失败:', error);
      alert(t('agent.deleteFailed'));
    }
  };

  const handleClone = async (agent: Agent) => {
    try {
      await api.cloneAgent(agent.id);
      loadAgents();
      useChatStore.getState().fetchAgents();
    } catch (error) {
      console.error('克隆 Agent 失败:', error);
      alert(t('agent.cloneFailed'));
    }
  };

  const handleSelectTemplate = (template: AgentTemplate) => {
    setFormData({
      name: template.name,
      description: template.description,
      system_prompt: template.system_prompt,
      model: availableModels.length > 0 ? availableModels[0].name : '',
      temperature: template.temperature,
      max_tokens: 0,
      memory_scene: template.memory_scene,
      decay_model: 'exponential',
    });
    setShowTemplateModal(false);
    setShowCreateModal(true);
  };

  const startEdit = (agent: Agent) => {
    setEditingAgent(agent);
    setFormData({
      name: agent.name,
      description: agent.description || '',
      system_prompt: agent.system_prompt || '',
      model: agent.model || '',
      temperature: agent.temperature ?? 0.7,
      max_tokens: agent.max_tokens ?? 0,
      memory_scene: agent.memory_scene || 'chat',
      decay_model: agent.decay_model || 'exponential',
    });
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      system_prompt: '你是一个有帮助的AI助手。请用中文回答用户的问题。',
      model: availableModels.length > 0 ? availableModels[0].name : '',
      temperature: 0.7,
      max_tokens: 0,
      memory_scene: 'chat',
      decay_model: 'exponential',
    });
  };

  const closeModal = () => {
    setShowCreateModal(false);
    setEditingAgent(null);
    resetForm();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <PageHeader
        title={t('agent.pageTitle')}
        description={t('agent.pageDescription')}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setShowTemplateModal(true)}>
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"
                />
              </svg>
              {t('agent.createFromTemplate')}
            </Button>
            <Button onClick={() => setShowCreateModal(true)}>
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              {t('agent.newAgent')}
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent) => {
          const sceneLabel =
            agent.memory_scene === 'chat'
              ? t('agent.sceneChat')
              : agent.memory_scene === 'task'
                ? t('agent.sceneTask')
                : t('agent.sceneFirstInteraction');
          return (
            <Card
              key={agent.id}
              className={`${agent.is_default ? 'ring-2 ring-[var(--color-accent)]' : ''}`}
            >
              <CardBody>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-[var(--color-accent-light)] flex items-center justify-center">
                      <svg
                        className="w-5 h-5 text-[var(--color-accent)]"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                        />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-semibold text-[var(--color-text-primary)]">{agent.name}</h3>
                      {agent.is_default && (
                        <Badge variant="primary" size="sm">
                          {t('agent.defaultBadge')}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    {!agent.is_default && (
                      <>
                        <button
                          onClick={() => startEdit(agent)}
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
                          onClick={() => handleClone(agent)}
                          className="p-1.5 hover:bg-[var(--color-bg-hover)] rounded-[var(--radius-sm)] transition-colors"
                          title={t('agent.clone')}
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
                              d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                            />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDelete(agent.id)}
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
                      </>
                    )}
                    {agent.is_default && (
                      <button
                        onClick={() => startEdit(agent)}
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
                    )}
                  </div>
                </div>

                <p className="text-sm text-[var(--color-text-secondary)] mb-4 line-clamp-2">
                  {agent.description || t('agent.noDescription')}
                </p>

                <div className="space-y-2 text-xs text-[var(--color-text-tertiary)]">
                  <div className="flex items-center gap-2">
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
                        d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                      />
                    </svg>
                    <span>{t('agent.model')}: {agent.model || t('agent.defaultModel')}</span>
                  </div>
                  <div className="flex items-center gap-2">
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
                        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                    </svg>
                    <span>
                      {t('agent.temperature')}: {agent.temperature} · {t('agent.scene')}: {sceneLabel}
                    </span>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)]">
                  {t('agent.updatedAt', { time: formatRelativeTime(agent.updated_at || agent.created_at || '') })}
                </div>
              </CardBody>
            </Card>
          );
        })}
      </div>

      <Modal
        isOpen={showTemplateModal}
        onClose={() => setShowTemplateModal(false)}
        title={t('agent.selectTemplate')}
      >
        <div className="grid grid-cols-2 gap-3">
          {AGENT_TEMPLATES.map((template) => (
            <button
              key={template.id}
              onClick={() => handleSelectTemplate(template)}
              className="p-4 text-left border border-[var(--color-border)] rounded-[var(--radius-lg)] hover:border-[var(--color-accent)] hover:bg-[var(--color-bg-hover)] transition-all"
            >
              <div className="flex items-center gap-3 mb-2">
                <span className="text-2xl">{template.icon}</span>
                <h3 className="font-medium text-[var(--color-text-primary)]">{template.name}</h3>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)]">{template.description}</p>
            </button>
          ))}
        </div>
      </Modal>

      <Modal
        isOpen={showCreateModal || !!editingAgent}
        onClose={closeModal}
        title={editingAgent ? t('agent.editAgent') : t('agent.newAgent')}
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">{t('agent.nameRequired')}</label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder={t('agent.namePlaceholder')}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">{t('agent.model')}</label>
              <select
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
              >
                <optgroup label={t('agent.providersOptgroup')}>
                  {providers.map((p) => (
                    <option key={p.id} value={p.name}>
                      {p.name} ({p.provider})
                    </option>
                  ))}
                </optgroup>
                {availableModels.length > 0 && (
                  <optgroup label={t('agent.ollamaModelsOptgroup')}>
                    {availableModels.map((m) => (
                      <option key={m.name} value={m.name}>
                        {m.name}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">{t('common.description')}</label>
            <Input
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder={t('agent.descPlaceholder')}
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">{t('agent.systemPrompt')}</label>
            <Textarea
              value={formData.system_prompt}
              onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
              placeholder={t('agent.systemPromptPlaceholder')}
              className="min-h-[100px]"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                {t('agent.temperature')}: {formData.temperature}
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={formData.temperature}
                onChange={(e) =>
                  setFormData({ ...formData, temperature: parseFloat(e.target.value) })
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-[var(--color-text-tertiary)]">
                <span>{t('agent.tempPrecise')}</span>
                <span>{t('agent.tempBalanced')}</span>
                <span>{t('agent.tempCreative')}</span>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">{t('agent.maxTokens')}</label>
              <Input
                type="number"
                value={formData.max_tokens}
                onChange={(e) =>
                  setFormData({ ...formData, max_tokens: parseInt(e.target.value) || 0 })
                }
                min="0"
                placeholder={t('agent.maxTokensPlaceholder')}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">{t('agent.memoryScene')}</label>
            <select
              value={formData.memory_scene}
              onChange={(e) => setFormData({ ...formData, memory_scene: e.target.value })}
              className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
            >
              <option value="chat">{t('agent.sceneChatFull')}</option>
              <option value="task">{t('agent.sceneTaskFull')}</option>
              <option value="first_interaction">{t('agent.sceneFirstInteractionFull')}</option>
            </select>
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={closeModal}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={editingAgent ? handleUpdate : handleCreate}
              disabled={!formData.name.trim()}
            >
              {editingAgent ? t('common.save') : t('common.create')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
