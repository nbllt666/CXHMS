import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Wrench,
  Plus,
  Trash2,
  Edit3,
  CheckCircle2,
  Loader2,
  Settings,
  Terminal,
  Globe,
  Database,
  FileText,
  Code,
  ToggleLeft,
  ToggleRight,
  Play,
  AlertCircle
} from 'lucide-react'
import { api } from '../api/client'
import { cn } from '../lib/utils'

interface Tool {
  id: string
  name: string
  description: string
  type: 'mcp' | 'native' | 'custom'
  status: 'active' | 'inactive' | 'error'
  config: Record<string, unknown>
  icon?: string
  created_at: string
  last_used?: string
  use_count: number
}

interface ToolStats {
  total_tools: number
  active_tools: number
  mcp_tools: number
  native_tools: number
  total_calls: number
}

const toolIcons: Record<string, React.ElementType> = {
  terminal: Terminal,
  globe: Globe,
  database: Database,
  file: FileText,
  code: Code,
  wrench: Wrench,
  settings: Settings
}

export function ToolsPage() {
  const queryClient = useQueryClient()
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [isTestModalOpen, setIsTestModalOpen] = useState(false)
  const [filter, setFilter] = useState<'all' | 'mcp' | 'native' | 'custom'>('all')

  // Fetch tools stats
  const { data: stats, isLoading: statsLoading } = useQuery<ToolStats>({
    queryKey: ['tools-stats'],
    queryFn: async () => {
      const response = await api.getToolsStats()
      return response
    },
    refetchInterval: 10000
  })

  // Fetch tools list
  const { data: tools, isLoading: toolsLoading } = useQuery<Tool[]>({
    queryKey: ['tools', filter],
    queryFn: async () => {
      const response = await api.getTools(filter === 'all' ? undefined : filter)
      return response.tools || []
    }
  })

  // Create tool mutation
  const createToolMutation = useMutation({
    mutationFn: api.createTool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] })
      queryClient.invalidateQueries({ queryKey: ['tools-stats'] })
      setIsCreateModalOpen(false)
    }
  })

  // Update tool mutation
  const updateToolMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; description?: string; type?: 'mcp' | 'native' | 'custom'; icon?: string; config?: Record<string, unknown>; status?: 'active' | 'inactive' } }) =>
      api.updateTool(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] })
      setIsEditModalOpen(false)
      setSelectedTool(null)
    }
  })

  // Delete tool mutation
  const deleteToolMutation = useMutation({
    mutationFn: api.deleteTool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] })
      queryClient.invalidateQueries({ queryKey: ['tools-stats'] })
      setSelectedTool(null)
    }
  })

  // Toggle tool status
  const toggleToolStatus = (tool: Tool) => {
    updateToolMutation.mutate({
      id: tool.id,
      data: { status: tool.status === 'active' ? 'inactive' : 'active' }
    })
  }

  // Filter tools
  const filteredTools = tools?.filter(tool => 
    filter === 'all' || tool.type === filter
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wrench className="w-6 h-6 text-primary" />
            工具管理
          </h1>
          <p className="text-muted-foreground mt-1">
            管理 MCP 工具、原生工具和自定义工具
          </p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          添加工具
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          title="总工具数"
          value={stats?.total_tools || 0}
          icon={Wrench}
          loading={statsLoading}
        />
        <StatCard
          title="活跃工具"
          value={stats?.active_tools || 0}
          icon={CheckCircle2}
          loading={statsLoading}
          trend={stats ? `${Math.round((stats.active_tools / stats.total_tools) * 100)}%` : undefined}
        />
        <StatCard
          title="MCP 工具"
          value={stats?.mcp_tools || 0}
          icon={Code}
          loading={statsLoading}
        />
        <StatCard
          title="总调用次数"
          value={stats?.total_calls || 0}
          icon={Terminal}
          loading={statsLoading}
        />
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2">
        {(['all', 'mcp', 'native', 'custom'] as const).map((type) => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              filter === type
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-accent"
            )}
          >
            {type === 'all' ? '全部' : type === 'mcp' ? 'MCP' : type === 'native' ? '原生' : '自定义'}
          </button>
        ))}
      </div>

      {/* Tools Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {toolsLoading ? (
          <div className="col-span-full flex justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : filteredTools && filteredTools.length > 0 ? (
          filteredTools.map((tool) => {
            const IconComponent = toolIcons[tool.icon || ''] || Wrench
            return (
              <div
                key={tool.id}
                className={cn(
                  "bg-card rounded-lg border border-border p-4 hover:border-primary/50 transition-colors",
                  selectedTool?.id === tool.id && "border-primary"
                )}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center",
                      tool.status === 'active' ? "bg-green-500/10" :
                      tool.status === 'error' ? "bg-red-500/10" : "bg-gray-500/10"
                    )}>
                      <IconComponent className={cn(
                        "w-5 h-5",
                        tool.status === 'active' ? "text-green-500" :
                        tool.status === 'error' ? "text-red-500" : "text-gray-500"
                      )} />
                    </div>
                    <div>
                      <h3 className="font-medium">{tool.name}</h3>
                      <p className="text-sm text-muted-foreground line-clamp-2">{tool.description}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full",
                          tool.type === 'mcp' ? "bg-blue-500/10 text-blue-600" :
                          tool.type === 'native' ? "bg-purple-500/10 text-purple-600" :
                          "bg-orange-500/10 text-orange-600"
                        )}>
                          {tool.type === 'mcp' ? 'MCP' : tool.type === 'native' ? '原生' : '自定义'}
                        </span>
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full",
                          tool.status === 'active' ? "bg-green-500/10 text-green-600" :
                          tool.status === 'error' ? "bg-red-500/10 text-red-600" :
                          "bg-gray-500/10 text-gray-600"
                        )}>
                          {tool.status === 'active' ? '活跃' :
                           tool.status === 'error' ? '错误' : '停用'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col gap-1">
                    <button
                      onClick={() => toggleToolStatus(tool)}
                      className="p-1.5 hover:bg-accent rounded-lg transition-colors"
                      title={tool.status === 'active' ? '停用' : '启用'}
                    >
                      {tool.status === 'active' ? (
                        <ToggleRight className="w-5 h-5 text-green-500" />
                      ) : (
                        <ToggleLeft className="w-5 h-5 text-gray-400" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-border">
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>调用次数: {tool.use_count}</span>
                    {tool.last_used && (
                      <span>最后使用: {new Date(tool.last_used).toLocaleDateString()}</span>
                    )}
                  </div>
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => {
                        setSelectedTool(tool)
                        setIsTestModalOpen(true)
                      }}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-muted rounded-lg hover:bg-accent transition-colors"
                    >
                      <Play className="w-4 h-4" />
                      测试
                    </button>
                    <button
                      onClick={() => {
                        setSelectedTool(tool)
                        setIsEditModalOpen(true)
                      }}
                      className="flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-muted rounded-lg hover:bg-accent transition-colors"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm('确定要删除此工具吗？')) {
                          deleteToolMutation.mutate(tool.id)
                        }
                      }}
                      className="flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-muted rounded-lg hover:bg-red-500/10 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            )
          })
        ) : (
          <div className="col-span-full text-center py-12 text-muted-foreground">
            <Wrench className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>暂无工具</p>
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="mt-4 text-primary hover:underline"
            >
              添加第一个工具
            </button>
          </div>
        )}
      </div>

      {/* Create Modal */}
      {isCreateModalOpen && (
        <ToolModal
          title="添加工具"
          onClose={() => setIsCreateModalOpen(false)}
          onSubmit={(data) => createToolMutation.mutate(data)}
          isLoading={createToolMutation.isPending}
        />
      )}

      {/* Edit Modal */}
      {isEditModalOpen && selectedTool && (
        <ToolModal
          title="编辑工具"
          tool={selectedTool}
          onClose={() => {
            setIsEditModalOpen(false)
            setSelectedTool(null)
          }}
          onSubmit={(data) => updateToolMutation.mutate({ id: selectedTool.id, data })}
          isLoading={updateToolMutation.isPending}
        />
      )}

      {/* Test Modal */}
      {isTestModalOpen && selectedTool && (
        <TestToolModal
          tool={selectedTool}
          onClose={() => {
            setIsTestModalOpen(false)
            setSelectedTool(null)
          }}
        />
      )}
    </div>
  )
}

// Stat Card Component
function StatCard({
  title,
  value,
  icon: Icon,
  loading,
  trend
}: {
  title: string
  value: string | number
  icon: React.ElementType
  loading?: boolean
  trend?: string
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
              {trend && (
                <span className="text-xs text-green-500">{trend}</span>
              )}
            </div>
          )}
        </div>
        <div className="p-2 bg-primary/10 rounded-lg">
          <Icon className="w-5 h-5 text-primary" />
        </div>
      </div>
    </div>
  )
}

// Tool Modal Component
interface ToolModalProps {
  title: string
  tool?: Tool
  onClose: () => void
  onSubmit: (data: { name: string; description?: string; type: 'mcp' | 'native' | 'custom'; icon?: string; config?: Record<string, unknown> }) => void
  isLoading: boolean
}

function ToolModal({ title, tool, onClose, onSubmit, isLoading }: ToolModalProps) {
  const [formData, setFormData] = useState({
    name: tool?.name || '',
    description: tool?.description || '',
    type: (tool?.type as 'mcp' | 'native' | 'custom') || 'custom',
    icon: tool?.icon || 'wrench',
    config: JSON.stringify(tool?.config || {}, null, 2)
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const config = JSON.parse(formData.config)
      onSubmit({
        name: formData.name,
        description: formData.description,
        type: formData.type,
        icon: formData.icon,
        config
      })
    } catch {
      alert('配置 JSON 格式错误')
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-lg border border-border w-full max-w-lg p-6 max-h-[90vh] overflow-auto">
        <h2 className="text-xl font-semibold mb-4">{title}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">名称</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">描述</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              rows={2}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">类型</label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value as 'mcp' | 'native' | 'custom' })}
                className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                <option value="mcp">MCP</option>
                <option value="native">原生</option>
                <option value="custom">自定义</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">图标</label>
              <select
                value={formData.icon}
                onChange={(e) => setFormData({ ...formData, icon: e.target.value })}
                className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                <option value="wrench">工具</option>
                <option value="terminal">终端</option>
                <option value="globe">网络</option>
                <option value="database">数据库</option>
                <option value="file">文件</option>
                <option value="code">代码</option>
                <option value="settings">设置</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">配置 (JSON)</label>
            <textarea
              value={formData.config}
              onChange={(e) => setFormData({ ...formData, config: e.target.value })}
              className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 font-mono text-sm"
              rows={6}
              placeholder='{"key": "value"}'
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
              {tool ? '保存' : '添加'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Test Tool Modal
interface TestToolModalProps {
  tool: Tool
  onClose: () => void
}

function TestToolModal({ tool, onClose }: TestToolModalProps) {
  const [params, setParams] = useState('{}')
  const [result, setResult] = useState<string | null>(null)
  const [isTesting, setIsTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleTest = async () => {
    setIsTesting(true)
    setError(null)
    setResult(null)

    try {
      const parsedParams = JSON.parse(params)
      const response = await api.testTool(tool.id, parsedParams)
      setResult(JSON.stringify(response, null, 2))
    } catch (e) {
      setError(e instanceof Error ? e.message : '测试失败')
    } finally {
      setIsTesting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-lg border border-border w-full max-w-2xl p-6 max-h-[90vh] overflow-auto">
        <h2 className="text-xl font-semibold mb-4">测试工具: {tool.name}</h2>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">参数 (JSON)</label>
            <textarea
              value={params}
              onChange={(e) => setParams(e.target.value)}
              className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 font-mono text-sm"
              rows={4}
              placeholder='{"param1": "value1"}'
            />
          </div>

          <button
            onClick={handleTest}
            disabled={isTesting}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {isTesting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {isTesting ? '测试中...' : '运行测试'}
          </button>

          {error && (
            <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
              <div className="flex items-center gap-2 text-red-600">
                <AlertCircle className="w-5 h-5" />
                <span className="font-medium">错误</span>
              </div>
              <p className="mt-2 text-sm text-red-600/80">{error}</p>
            </div>
          )}

          {result && (
            <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
              <div className="flex items-center gap-2 text-green-600">
                <CheckCircle2 className="w-5 h-5" />
                <span className="font-medium">结果</span>
              </div>
              <pre className="mt-2 text-sm text-green-600/80 overflow-auto max-h-64 font-mono">
                {result}
              </pre>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-muted-foreground hover:text-foreground transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
