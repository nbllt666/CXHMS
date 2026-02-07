import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Database,
  Server,
  Brain,
  Save,
  CheckCircle2,
  AlertCircle,
  Play,
  RotateCcw,
  Terminal,
  Activity,
  Square,
  Loader2
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
  const [activeSection, setActiveSection] = useState<'service' | 'vector' | 'llm'>('service')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [logs, setLogs] = useState('')
  const [isBackendRunning, setIsBackendRunning] = useState(false)
  const [isControlServiceReady, setIsControlServiceReady] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)

  // Check control service health
  const checkControlService = useCallback(async () => {
    try {
      await api.getControlServiceHealth()
      setIsControlServiceReady(true)
      return true
    } catch {
      setIsControlServiceReady(false)
      return false
    }
  }, [])

  // Check main backend status via control service
  const checkBackendStatus = useCallback(async () => {
    try {
      const status = await api.getMainBackendStatus()
      setIsBackendRunning(status.running)
      return status.running
    } catch {
      setIsBackendRunning(false)
      return false
    }
  }, [])

  // Initial checks
  useEffect(() => {
    checkControlService()
    checkBackendStatus()

    const interval = setInterval(() => {
      checkControlService()
      checkBackendStatus()
    }, 3000)

    return () => clearInterval(interval)
  }, [checkControlService, checkBackendStatus])

  // Service config query (only when backend is running)
  const { data: serviceConfig } = useQuery({
    queryKey: ['serviceConfig'],
    queryFn: () => api.getServiceConfig(),
    enabled: isBackendRunning
  })

  // Load logs (only when backend is running)
  const loadLogs = useCallback(async () => {
    if (!isBackendRunning) {
      setLogs('后端服务未运行')
      return
    }
    try {
      const data = await api.getServiceLogs(50)
      setLogs(data.logs || '暂无日志')
    } catch {
      setLogs('无法加载日志')
    }
  }, [isBackendRunning])

  useEffect(() => {
    if (activeSection === 'service') {
      loadLogs()
      const interval = setInterval(loadLogs, 3000)
      return () => clearInterval(interval)
    }
  }, [activeSection, loadLogs])

  // Start main backend service
  const handleStartBackend = async () => {
    if (!isControlServiceReady) {
      alert('控制服务未就绪，请稍后再试')
      return
    }
    setIsProcessing(true)
    try {
      await api.startMainBackend()
      // Wait a moment for the service to start
      await new Promise(resolve => setTimeout(resolve, 2000))
      await checkBackendStatus()
    } catch (error) {
      console.error('Failed to start backend:', error)
      alert('启动后端服务失败，请检查控制台日志')
    } finally {
      setIsProcessing(false)
    }
  }

  // Stop main backend service
  const handleStopBackend = async () => {
    if (!isControlServiceReady) {
      alert('控制服务未就绪')
      return
    }
    setIsProcessing(true)
    try {
      await api.stopMainBackend()
      await new Promise(resolve => setTimeout(resolve, 1000))
      await checkBackendStatus()
    } catch (error) {
      console.error('Failed to stop backend:', error)
      alert('停止后端服务失败')
    } finally {
      setIsProcessing(false)
    }
  }

  // Restart main backend service
  const handleRestartBackend = async () => {
    if (!isControlServiceReady) {
      alert('控制服务未就绪')
      return
    }
    setIsProcessing(true)
    try {
      await api.restartMainBackend()
      await new Promise(resolve => setTimeout(resolve, 3000))
      await checkBackendStatus()
    } catch (error) {
      console.error('Failed to restart backend:', error)
      alert('重启后端服务失败')
    } finally {
      setIsProcessing(false)
    }
  }

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
    if (!isBackendRunning) {
      alert('后端服务未运行，无法保存配置')
      return
    }
    setSaveStatus('saving')
    try {
      // 保存向量配置
      if (activeSection === 'vector') {
        await api.updateServiceConfig({
          vector: {
            backend: vectorConfig.backend,
            weaviate_host: vectorConfig.weaviateHost,
            weaviate_port: vectorConfig.weaviatePort,
            vector_size: vectorConfig.vectorSize
          }
        })
      }
      // 保存LLM配置
      else if (activeSection === 'llm') {
        await api.updateServiceConfig({
          llm: {
            provider: llmConfig.provider,
            host: llmConfig.host,
            model: llmConfig.model,
            temperature: llmConfig.temperature,
            max_tokens: llmConfig.maxTokens
          }
        })
      }
      setSaveStatus('saved')
    } catch {
      setSaveStatus('error')
    }
    setTimeout(() => setSaveStatus('idle'), 2000)
  }

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <div className="w-64 border-r border-border pr-6">
        <h3 className="font-semibold mb-4">设置</h3>
        <nav className="space-y-1">
          {sections.map((section) => (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id as 'service' | 'vector' | 'llm')}
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
                通过控制服务管理 CXHMS 后端服务的启动、停止和重启
              </p>
            </div>

            {/* Control Service Status */}
            <div className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "w-3 h-3 rounded-full",
                  isControlServiceReady ? "bg-green-500" : "bg-red-500"
                )} />
                <span className="text-sm">
                  控制服务状态:
                  <span className={cn(
                    "font-medium ml-1",
                    isControlServiceReady ? "text-green-500" : "text-red-500"
                  )}>
                    {isControlServiceReady ? '运行中 (端口 8765)' : '未就绪'}
                  </span>
                </span>
              </div>
              {!isControlServiceReady && (
                <p className="text-xs text-muted-foreground mt-2">
                  控制服务随前端自动启动，请等待几秒钟...
                </p>
              )}
            </div>

            {/* Main Backend Status Card */}
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-4">
                  <div className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center",
                    isBackendRunning ? "bg-green-500/10" : "bg-red-500/10"
                  )}>
                    <Activity className={cn(
                      "w-6 h-6",
                      isBackendRunning ? "text-green-500" : "text-red-500"
                    )} />
                  </div>
                  <div>
                    <h4 className="font-semibold">
                      {isBackendRunning ? '主后端服务运行中' : '主后端服务已停止'}
                    </h4>
                    <p className="text-sm text-muted-foreground">
                      {isBackendRunning
                        ? `后端服务正在运行，访问 http://localhost:8000`
                        : '后端服务未运行，点击启动按钮开启服务'
                      }
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {isBackendRunning ? (
                    <>
                      <button
                        onClick={handleRestartBackend}
                        disabled={isProcessing || !isControlServiceReady}
                        className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isProcessing ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RotateCcw className="w-4 h-4" />
                        )}
                        重启
                      </button>
                      <button
                        onClick={handleStopBackend}
                        disabled={isProcessing || !isControlServiceReady}
                        className="flex items-center gap-2 px-4 py-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isProcessing ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Square className="w-4 h-4" />
                        )}
                        停止
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={handleStartBackend}
                      disabled={isProcessing || !isControlServiceReady}
                      className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isProcessing ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                      启动后端服务
                    </button>
                  )}
                </div>
              </div>

              {/* Service Config */}
              {isBackendRunning ? (
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
              ) : (
                <div className="grid grid-cols-2 gap-4 p-4 bg-muted rounded-lg opacity-60">
                  <div>
                    <span className="text-xs text-muted-foreground">主机</span>
                    <p className="font-medium">0.0.0.0</p>
                  </div>
                  <div>
                    <span className="text-xs text-muted-foreground">端口</span>
                    <p className="font-medium">8000</p>
                  </div>
                  <div>
                    <span className="text-xs text-muted-foreground">日志级别</span>
                    <p className="font-medium">info</p>
                  </div>
                  <div>
                    <span className="text-xs text-muted-foreground">调试模式</span>
                    <p className="font-medium">关闭</p>
                  </div>
                </div>
              )}
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

            {!isBackendRunning && (
              <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                <p className="text-sm text-yellow-600">
                  后端服务未运行，配置保存后将在服务启动时生效
                </p>
              </div>
            )}

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

            {!isBackendRunning && (
              <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                <p className="text-sm text-yellow-600">
                  后端服务未运行，配置保存后将在服务启动时生效
                </p>
              </div>
            )}

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
