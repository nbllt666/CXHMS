import { useLocation } from 'react-router-dom'
import { Bell } from 'lucide-react'

const pageTitles: Record<string, string> = {
  '/': '对话',
  '/memories': '记忆管理',
  '/archive': '归档管理',
  '/settings': '系统设置',
}

export function Header() {
  const location = useLocation()
  const title = pageTitles[location.pathname] || 'CXHMS'

  return (
    <header className="h-16 border-b border-border bg-card/50 backdrop-blur-sm flex items-center justify-between px-6">
      <h2 className="text-xl font-semibold">{title}</h2>

      <div className="flex items-center gap-4">
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
