import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { 
  Database, 
  Server, 
  Brain, 
  Save,
  CheckCircle2,
  AlertCircle,
  Play,
  Square,
  RotateCcw,
  Terminal,
  Activity,
  Package
} from 'lucide-react'
import { api } from '../api/client'
import { cn } from '../lib/utils'

interface SettingSection {
  id: string
  title: string
  icon: React.ElementType
  description: string
}

const sections: SettingSection[] = [
  {
    id: 'service',
    title: '服务管理',
    icon: Server,
    description: '启动/停止后端服务'
  },
  {
    id: 'vector',
    title: '向量存储',
    icon: Database,
    description: '配置向量数据库连接'
  },
  {
    id: 'llm',
    title: '模型设置',
    icon: Brain,
    description: '配置大语言模型参数'
  }
]

export function SettingsPage() {
  const [activeSection, setActiveSection] = useState('service')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [logs, setLogs] = useState('')
  const [useConda, setUseConda] = useState(true)

  // Service status query
  const { data: serviceStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['serviceStatus'],
    queryFn: () => api.getServiceStatus(),
    refetchInterval: 5000
  })

  // Service config query
  const { data: serviceConfig } = useQuery({
    queryKey: ['serviceConfig'],
    queryFn: () => api.getServiceConfig()
  })

  // Environment info query
  const { data: envInfo } = useQuery({
    queryKey: ['environmentInfo'],
    queryFn: () => api.getEnvironmentInfo()
  })

  // Service mutations
  const startService = useMutation({
    mutationFn: () => api.startService({
      host: serviceConfig?.config?.host || '0.0.0.0',
      port: serviceConfig?.config?.port || 8000,
      log_level: serviceConfig?.config?.log_level || 'info',
      use_conda: useConda
    }),
    onSuccess: () => refetchStatus()
  })

  const stopService = useMutation({
    mutationFn: () => api.stopService(),
    onSuccess: () => refetchStatus()
  })

  const restartService = useMutation({
    mutationFn: () => api.restartService({
      host: serviceConfig?.config?.host || '0.0.0.0',
      port: serviceConfig?.config?.port || 8000,
      log_level: serviceConfig?.config?.log_level || 'info',
      use_conda: useConda
    }),
    onSuccess: () => refetchStatus()
  })

  // Load logs
  const loadLogs = async () => {
    try {
      const data = await api.getServiceLogs(50)
      setLogs(data.logs || '暂无日志')
    } catch {
      setLogs('无法加载日志')
    }
  }

  useEffect(() => {
    if (activeSection === 'service') {
      loadLogs()
      const interval = setInterval(loadLogs, 3000)
      return () => clearInterval(interval)
    }
  }, [activeSection])

  // Set default useConda based on availability
  useEffect(() => {
    if (serviceConfig?.config?.conda_available !== undefined) {
      setUseConda(serviceConfig.config.conda_available)
    }
  }, [serviceConfig])

  const [vectorConfig, setVectorConfig] = useState({
    backend: 'weaviate_embedded',
    weaviateHost: 'localhost',
    weaviatePort: 8080,
    vectorSize: 768
  })

  const [llmConfig, setLlmConfig] = useState({
    provider: 'ollama',
    host: 'http://localhost:11434',
    model: 'llama3.2:3b',
    temperature: 0.7,
    maxTokens: 2048
  })

  const handleSave = async () => {
    setSaveStatus('saving')
    await new Promise(resolve => setTimeout(resolve, 1000))
    setSaveStatus('saved')
    setTimeout(() => setSaveStatus('idle'), 2000)
  }

  const isRunning = serviceStatus?.running || false
  const condaAvailable = serviceConfig?.config?.conda_available || false
  const isUsingConda = serviceStatus?.using_conda || false

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <div className="w-64 border-r border-border pr-6">
        <h3 className="font-semibold mb-4">设置</h3>
        <nav className="space-y-1">
          {sections.map((section) => (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left',
                activeSection === section.id
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              )}
            >
              <section.icon className="w-5 h-5" />
              <div>
                <div>{section.title}</div>
                <div className="text-xs text-muted-foreground font-normal">
                  {section.description}
                </div>
              </div>
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <div className="flex-1 pl-6 overflow-auto">
        {/* Service Management */}
        {activeSection === 'service' && (
          <div className="max-w-3xl space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-1">服务管理</h3>
              <p className="text-sm text-muted-foreground">
                管理 CXHMS 后端服务的启动、停止和重启
              </p>
            </div>

            {/* Status Card */}
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-4">
                  <div className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center",
                    isRunning ? "bg-green-500/10" : "bg-red-500/10"
                  )}>
                    <Activity className={cn(
                      "w-6 h-6",
                      isRunning ? "text-green-500" : "text-red-500"
                    )} />
                  </div>
                  <div>
                    <h4 className="font-semibold">
                      {isRunning ? '服务运行中' : '服务已停止'}
                    </h4>
                    <p className="text-sm text-muted-foreground">
                      {isRunning 
                        ? `PID: ${serviceStatus?.pid} | 端口: ${serviceStatus?.port} ${isUsingConda ? '| Conda环境' : '| 系统Python'}`
                        : '点击启动按钮启动后端服务'
                      }
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {!isRunning ? (
                    <button
                      onClick={() => startService.mutate()}
                      disabled={startService.isPending}
                      className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 transition-colors"
                    >
                      <Play className="w-4 h-4" />
                      {startService.isPending ? '启动中...' : '启动服务'}
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => restartService.mutate()}
                        disabled={restartService.isPending}
                        className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                      >
                        <RotateCcw className={cn("w-4 h-4", restartService.isPending && "animate-spin")} />
                        重启
                      </button>
                      <button
                        onClick={() => stopService.mutate()}
                        disabled={stopService.isPending}
                        className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 transition-colors"
                      >
                        <Square className="w-4 h-4" />
                        停止
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Environment Selection */}
              {condaAvailable && (
                <div className="mb-4 p-4 bg-muted rounded-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Package className="w-5 h-5 text-primary" />
                      <div>
                        <h5 className="font-medium">Python 环境</h5>
                        <p className="text-xs text-muted-foreground">
                          选择启动服务使用的 Python 环境
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="python-env"
                          checked={useConda}
                          onChange={() => setUseConda(true)}
                          disabled={isRunning}
                          className="w-4 h-4"
                        />
                        <span className="text-sm">Conda 环境</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer ml-4">
                        <input
                          type="radio"
                          name="python-env"
                          checked={!useConda}
                          onChange={() => setUseConda(false)}
                          disabled={isRunning}
                          className="w-4 h-4"
                        />
                        <span className="text-sm">系统 Python</span>
                      </label>
                    </div>
                  </div>
                  {envInfo?.environment?.conda_python_path && (
                    <p className="text-xs text-muted-foreground mt-2 pl-8">
                      Conda 路径: {envInfo.environment.conda_python_path}
                    </p>
                  )}
                </div>
              )}

              {/* Service Config */}
              <div className="grid grid-cols-2 gap-4 p-4 bg-muted rounded-lg">
                <div>
                  <span className="text-xs text-muted-foreground">主机</span>
                  <p className="font-medium">{serviceConfig?.config?.host || '0.0.0.0'}</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">端口</span>
                  <p className="font-medium">{serviceConfig?.config?.port || 8000}</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">日志级别</span>
                  <p className="font-medium">{serviceConfig?.config?.log_level || 'info'}</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">调试模式</span>
                  <p className="font-medium">{serviceConfig?.config?.debug ? '开启' : '关闭'}</p>
                </div>
              </div>
            </div>

            {/* Logs */}
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <Terminal className="w-5 h-5" />
                <h4 className="font-semibold">服务日志</h4>
              </div>
              <div className="bg-black rounded-lg p-4 font-mono text-sm text-green-400 h-64 overflow-auto">
                <pre>{logs}</pre>
              </div>
            </div>
          </div>
        )}

        {/* Vector Settings */}
        {activeSection === 'vector' && (
          <div className="max-w-2xl space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-1">向量存储配置</h3>
              <p className="text-sm text-muted-foreground">
                选择并配置向量数据库后端，支持 Weaviate Embedded 和普通 Weaviate
              </p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-2 block">向量存储后端</label>
                <select
                  value={vectorConfig.backend}
                  onChange={(e) => setVectorConfig({ ...vectorConfig, backend: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="weaviate_embedded">Weaviate Embedded (推荐)</option>
                  <option value="weaviate">Weaviate (独立服务)</option>
                  <option value="milvus_lite">Milvus Lite</option>
                  <option value="qdrant">Qdrant</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  Weaviate Embedded 无需额外配置，零部署即可使用
                </p>
              </div>

              {vectorConfig.backend === 'weaviate' && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm font-medium mb-2 block">主机地址</label>
                      <input
                        type="text"
                        value={vectorConfig.weaviateHost}
                        onChange={(e) => setVectorConfig({ ...vectorConfig, weaviateHost: e.target.value })}
                        className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-2 block">端口</label>
                      <input
                        type="number"
                        value={vectorConfig.weaviatePort}
                        onChange={(e) => setVectorConfig({ ...vectorConfig, weaviatePort: parseInt(e.target.value) })}
                        className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                      />
                    </div>
                  </div>
                </>
              )}

              <div>
                <label className="text-sm font-medium mb-2 block">向量维度</label>
                <select
                  value={vectorConfig.vectorSize}
                  onChange={(e) => setVectorConfig({ ...vectorConfig, vectorSize: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value={384}>384 (小型模型)</option>
                  <option value={768}>768 (中型模型)</option>
                  <option value={1024}>1024 (大型模型)</option>
                  <option value={1536}>1536 (OpenAI)</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  向量维度应与嵌入模型输出维度匹配
                </p>
              </div>
            </div>
          </div>
        )}

        {/* LLM Settings */}
        {activeSection === 'llm' && (
          <div className="max-w-2xl space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-1">模型配置</h3>
              <p className="text-sm text-muted-foreground">
                配置大语言模型提供商和参数
              </p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-2 block">模型提供商</label>
                <select
                  value={llmConfig.provider}
                  onChange={(e) => setLlmConfig({ ...llmConfig, provider: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="ollama">Ollama (本地)</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="deepseek">DeepSeek</option>
                </select>
              </div>

              <div>
                <label className="text-sm font-medium mb-2 block">服务地址</label>
                <input
                  type="text"
                  value={llmConfig.host}
                  onChange={(e) => setLlmConfig({ ...llmConfig, host: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>

              <div>
                <label className="text-sm font-medium mb-2 block">模型名称</label>
                <input
                  type="text"
                  value={llmConfig.model}
                  onChange={(e) => setLlmConfig({ ...llmConfig, model: e.target.value })}
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">温度 (Temperature)</label>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={llmConfig.temperature}
                    onChange={(e) => setLlmConfig({ ...llmConfig, temperature: parseFloat(e.target.value) })}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-muted-foreground mt-1">
                    <span>0</span>
                    <span>{llmConfig.temperature}</span>
                    <span>2</span>
                  </div>
                </div>

                <div>
                  <label className="text-sm font-medium mb-2 block">最大 Token</label>
                  <input
                    type="number"
                    value={llmConfig.maxTokens}
                    onChange={(e) => setLlmConfig({ ...llmConfig, maxTokens: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Save Button */}
        <div className="mt-8 pt-6 border-t border-border">
          <button
            onClick={handleSave}
            disabled={saveStatus === 'saving'}
            className={cn(
              'flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-colors',
              saveStatus === 'saved'
                ? 'bg-green-500 text-white'
                : saveStatus === 'error'
                ? 'bg-destructive text-destructive-foreground'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            )}
          >
            {saveStatus === 'saving' ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                保存中...
              </>
            ) : saveStatus === 'saved' ? (
              <>
                <CheckCircle2 className="w-4 h-4" />
                已保存
              </>
            ) : saveStatus === 'error' ? (
              <>
                <AlertCircle className="w-4 h-4" />
                保存失败
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                保存设置
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
