import { useLocation } from 'react-router-dom'
import { Bell, Bot, ChevronDown } from 'lucide-react'
import { useChatStore } from '../store/chatStore'
import { useState, useRef, useEffect } from 'react'
import { cn } from '../lib/utils'
import { LanguageSwitcher } from './LanguageSwitcher'
import { useTranslation } from 'react-i18next'

const getPageTitles = (t: Function): Record<string, string> => ({
  '/': t('nav.chat'),
  '/agents': t('agent.title'),
  '/memories': t('memory.title'),
  '/archive': t('archive.title'),
  '/acp': t('acp.title'),
  '/tools': t('tools.title'),
  '/settings': t('settings.title'),
})

export function Header() {
  const { t } = useTranslation()
  const location = useLocation()
  const pageTitles = getPageTitles(t)
  const title = pageTitles[location.pathname] || 'CXHMS'
  const isChatPage = location.pathname === '/'
  
  const { agents, currentAgentId, setCurrentAgentId } = useChatStore()
  const [showAgentSelector, setShowAgentSelector] = useState(false)
  const agentSelectorRef = useRef<HTMLDivElement>(null)
  
  const currentAgent = agents.find(a => a.id === currentAgentId)

  // 点击外部关闭选择器
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (agentSelectorRef.current && !agentSelectorRef.current.contains(event.target as Node)) {
        setShowAgentSelector(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <header className="h-16 border-b border-border bg-card/50 backdrop-blur-sm flex items-center justify-between px-6">
      <h2 className="text-xl font-semibold">{title}</h2>

      <div className="flex items-center gap-4">
        {/* Agent 选择器 - 仅在对话页面显示 */}
        {isChatPage && (
          <div className="relative" ref={agentSelectorRef}>
            <button
              onClick={() => setShowAgentSelector(!showAgentSelector)}
              className="flex items-center gap-2 px-3 py-1.5 bg-muted rounded-lg hover:bg-accent transition-colors"
            >
              <Bot className="w-4 h-4" />
              <span className="text-sm">{currentAgent?.name || '默认助手'}</span>
              <ChevronDown className={cn('w-4 h-4 transition-transform', showAgentSelector && 'rotate-180')} />
            </button>

            {showAgentSelector && (
              <div className="absolute top-full right-0 mt-1 w-56 bg-popover border border-border rounded-lg shadow-lg z-50">
                <div className="p-1 max-h-64 overflow-y-auto">
                  {agents.map((agent) => (
                    <button
                      key={agent.id}
                      onClick={() => {
                        setCurrentAgentId(agent.id)
                        setShowAgentSelector(false)
                      }}
                      className={cn(
                        'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                        currentAgentId === agent.id
                          ? 'bg-primary/10 text-primary'
                          : 'hover:bg-accent'
                      )}
                    >
                      <div className="font-medium">{agent.name}</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {agent.description || '无描述'}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 语言切换器 */}
        <LanguageSwitcher />

        <a
          href="https://afdian.com/a/nbllt666"
          target="_blank"
          rel="noopener noreferrer"
          className="p-2 rounded-lg hover:bg-accent transition-colors relative group"
          title="支持开发者"
        >
          <Bell className="w-5 h-5 text-muted-foreground group-hover:text-foreground" />
          <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-popover text-popover-foreground text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
            支持开发者
          </span>
        </a>
        <span className="text-sm text-muted-foreground">
          CXHMS v1.0
        </span>
      </div>
    </header>
  )
}
