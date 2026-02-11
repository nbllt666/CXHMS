import { useState, useEffect } from 'react'
import { Bot, Plus, Edit2, Trash2, Copy, MessageSquare, Settings, X } from 'lucide-react'
import { api } from '../api/client'
import { formatRelativeTime } from '../lib/utils'

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
  vision_enabled?: boolean  // 多模态支持
  memory_scene: string
  decay_model: string  // 记忆衰减模型
  is_default: boolean
  created_at: string
  updated_at: string
}

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null)

  // 表单状态
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    system_prompt: '你是一个有帮助的AI助手。请用中文回答用户的问题。',
    model: 'main',  // 默认为主模型
    temperature: 0.7,
    max_tokens: 0,  // 0 表示不限制，使用模型默认
    use_memory: true,
    use_tools: true,
    vision_enabled: false,  // 默认不启用多模态
    memory_scene: 'chat',
    decay_model: 'exponential'  // 默认使用双阶段指数衰减
  })

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      setLoading(true)
      const data = await api.getAgents()
      // 过滤掉 memory-agent，不在列表中显示
      const filteredAgents = data.filter((agent: Agent) => agent.id !== 'memory-agent')
      setAgents(filteredAgents)
    } catch (error) {
      console.error('加载 Agent 失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
      await api.createAgent(formData)
      setShowCreateModal(false)
      resetForm()
      loadAgents()
    } catch (error) {
      console.error('创建 Agent 失败:', error)
      alert('创建失败，请检查名称是否重复')
    }
  }

  const handleUpdate = async () => {
    if (!editingAgent) return
    try {
      await api.updateAgent(editingAgent.id, formData)
      setEditingAgent(null)
      resetForm()
      loadAgents()
    } catch (error) {
      console.error('更新 Agent 失败:', error)
      alert('更新失败')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除这个 Agent 吗？')) return
    try {
      await api.deleteAgent(id)
      loadAgents()
    } catch (error) {
      console.error('删除 Agent 失败:', error)
      alert('删除失败')
    }
  }

  const handleClone = async (agent: Agent) => {
    try {
      await api.cloneAgent(agent.id)
      loadAgents()
    } catch (error) {
      console.error('克隆 Agent 失败:', error)
      alert('克隆失败')
    }
  }

  const startEdit = (agent: Agent) => {
    setEditingAgent(agent)
    setFormData({
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      model: agent.model,
      temperature: agent.temperature,
      max_tokens: agent.max_tokens,
      use_memory: agent.use_memory,
      use_tools: agent.use_tools,
      memory_scene: agent.memory_scene,
      decay_model: agent.decay_model || 'exponential',
      vision_enabled: agent.vision_enabled || false
    })
  }

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      system_prompt: '你是一个有帮助的AI助手。请用中文回答用户的问题。',
      model: 'main',
      temperature: 0.7,
      max_tokens: 0,  // 0 表示不限制
      use_memory: true,
      use_tools: true,
      memory_scene: 'chat',
      decay_model: 'exponential',
      vision_enabled: false
    })
  }

  const closeModal = () => {
    setShowCreateModal(false)
    setEditingAgent(null)
    resetForm()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">AI 助手管理</h1>
          <p className="text-muted-foreground mt-1">
            创建和管理不同的 AI 助手，每个助手可以有独立的系统提示词和配置
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          新建助手
        </button>
      </div>

      {/* Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 overflow-y-auto">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className={`p-4 rounded-xl border transition-all hover:shadow-md ${
              agent.is_default ? 'border-primary/50 bg-primary/5' : 'border-border bg-card'
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Bot className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold">{agent.name}</h3>
                  {agent.is_default && (
                    <span className="text-xs text-primary">默认助手</span>
                  )}
                </div>
              </div>
              <div className="flex gap-1">
                {!agent.is_default && (
                  <>
                    <button
                      onClick={() => startEdit(agent)}
                      className="p-1.5 hover:bg-accent rounded-lg transition-colors"
                      title="编辑"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleClone(agent)}
                      className="p-1.5 hover:bg-accent rounded-lg transition-colors"
                      title="克隆"
                    >
                      <Copy className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(agent.id)}
                      className="p-1.5 hover:bg-destructive/10 text-destructive rounded-lg transition-colors"
                      title="删除"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </>
                )}
                {agent.is_default && (
                  <button
                    onClick={() => startEdit(agent)}
                    className="p-1.5 hover:bg-accent rounded-lg transition-colors"
                    title="编辑"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>

            <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
              {agent.description || '暂无描述'}
            </p>

            <div className="space-y-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <Settings className="w-3.5 h-3.5" />
                <span>模型: {agent.model}</span>
              </div>
              <div className="flex items-center gap-2">
                <MessageSquare className="w-3.5 h-3.5" />
                <span>场景: {agent.memory_scene}</span>
              </div>
              <div className="flex items-center gap-4">
                <span>温度: {agent.temperature}</span>
                <span>Max Tokens: {agent.max_tokens}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className={agent.use_memory ? 'text-green-600' : 'text-gray-400'}>
                  {agent.use_memory ? '✓ 记忆' : '✗ 记忆'}
                </span>
                <span className={agent.use_tools ? 'text-green-600' : 'text-gray-400'}>
                  {agent.use_tools ? '✓ 工具' : '✗ 工具'}
                </span>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-border text-xs text-muted-foreground">
              更新于 {formatRelativeTime(agent.updated_at)}
            </div>
          </div>
        ))}
      </div>

      {/* Create/Edit Modal */}
      {(showCreateModal || editingAgent) && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4">
            <div className="p-6 border-b border-border flex items-center justify-between">
              <h2 className="text-xl font-semibold">
                {editingAgent ? '编辑助手' : '新建助手'}
              </h2>
              <button onClick={closeModal} className="p-2 hover:bg-accent rounded-lg">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {/* 基本信息 */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">名称 *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="助手名称"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">模型类型</label>
                  <select
                    value={formData.model || 'main'}
                    onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                    className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  >
                    <option value="main">主模型 (Main)</option>
                    <option value="summary">摘要模型 (Summary)</option>
                    <option value="memory">记忆管理模型 (Memory)</option>
                  </select>
                  <p className="text-xs text-muted-foreground mt-1">
                    选择模型类型决定 Agent 使用的 LLM 和可用工具
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">描述</label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder="助手的简短描述"
                />
              </div>

              {/* 系统提示词 */}
              <div>
                <label className="block text-sm font-medium mb-1">系统提示词</label>
                <textarea
                  value={formData.system_prompt}
                  onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[100px] resize-y"
                  placeholder="定义助手的行为和角色..."
                />
                <p className="text-xs text-muted-foreground mt-1">
                  系统提示词定义了助手的行为方式，会在每次对话开始时发送给模型
                </p>
              </div>

              {/* 参数配置 */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">
                    温度: {formData.temperature}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={formData.temperature}
                    onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>精确</span>
                    <span>平衡</span>
                    <span>创意</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">最大 Tokens</label>
                  <input
                    type="number"
                    value={formData.max_tokens}
                    onChange={(e) => setFormData({ ...formData, max_tokens: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    min="0"
                    placeholder="0 表示使用模型默认"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    0 表示使用模型默认设置
                  </p>
                </div>
              </div>

              {/* 记忆场景 */}
              <div>
                <label className="block text-sm font-medium mb-1">记忆场景</label>
                <select
                  value={formData.memory_scene}
                  onChange={(e) => setFormData({ ...formData, memory_scene: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="chat">闲聊 (Chat)</option>
                  <option value="task">任务 (Task)</option>
                  <option value="first_interaction">首次交互 (First Interaction)</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  不同场景会影响记忆检索的权重策略
                </p>
              </div>

              {/* 记忆衰减模型 */}
              <div>
                <label className="block text-sm font-medium mb-1">记忆衰减模型</label>
                <select
                  value={formData.decay_model}
                  onChange={(e) => setFormData({ ...formData, decay_model: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="exponential">双阶段指数衰减 (推荐)</option>
                  <option value="ebbinghaus">艾宾浩斯遗忘曲线 (实验性)</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  艾宾浩斯模型更符合人类记忆规律，但仍在实验阶段
                </p>
              </div>

              {/* 功能开关 */}
              <div className="flex gap-6 flex-wrap">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.use_memory}
                    onChange={(e) => setFormData({ ...formData, use_memory: e.target.checked })}
                    className="w-4 h-4 rounded border-border"
                  />
                  <span className="text-sm">启用记忆</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.use_tools}
                    onChange={(e) => setFormData({ ...formData, use_tools: e.target.checked })}
                    className="w-4 h-4 rounded border-border"
                  />
                  <span className="text-sm">启用工具</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.vision_enabled}
                    onChange={(e) => setFormData({ ...formData, vision_enabled: e.target.checked })}
                    className="w-4 h-4 rounded border-border"
                  />
                  <span className="text-sm">启用多模态 (Vision)</span>
                </label>
              </div>
            </div>

            <div className="p-6 border-t border-border flex justify-end gap-3">
              <button
                onClick={closeModal}
                className="px-4 py-2 text-muted-foreground hover:bg-accent rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={editingAgent ? handleUpdate : handleCreate}
                disabled={!formData.name.trim()}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {editingAgent ? '保存' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
