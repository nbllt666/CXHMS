import { useState } from 'react'
import { 
  Database, 
  Server, 
  Brain, 
  Save,
  CheckCircle2,
  AlertCircle
} from 'lucide-react'
import { cn } from '../lib/utils'

interface SettingSection {
  id: string
  title: string
  icon: React.ElementType
  description: string
}

const sections: SettingSection[] = [
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
  },
  {
    id: 'system',
    title: '系统设置',
    icon: Server,
    description: '系统级配置选项'
  }
]

export function SettingsPage() {
  const [activeSection, setActiveSection] = useState('vector')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

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
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000))
    setSaveStatus('saved')
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
      <div className="flex-1 pl-6">
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

        {/* System Settings */}
        {activeSection === 'system' && (
          <div className="max-w-2xl space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-1">系统设置</h3>
              <p className="text-sm text-muted-foreground">
                系统级配置和高级选项
              </p>
            </div>

            <div className="space-y-4">
              <div className="p-4 bg-muted rounded-lg">
                <h4 className="font-medium mb-2">关于 CXHMS</h4>
                <p className="text-sm text-muted-foreground">
                  CXHMS (晨曦人格化记忆系统) 是一个智能记忆管理平台，
                  支持长期记忆存储、语义搜索、自动归档等功能。
                </p>
              </div>

              <div className="p-4 bg-muted rounded-lg">
                <h4 className="font-medium mb-2">版本信息</h4>
                <div className="text-sm text-muted-foreground space-y-1">
                  <p>前端版本: 1.0.0</p>
                  <p>后端版本: 1.0.0</p>
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
