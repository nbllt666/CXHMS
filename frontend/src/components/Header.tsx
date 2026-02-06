import { useLocation } from 'react-router-dom'
import { Bell, Search, User } from 'lucide-react'

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
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="全局搜索..."
            className="pl-9 pr-4 py-2 bg-muted rounded-lg text-sm w-64 focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
        
        <button className="p-2 hover:bg-accent rounded-lg relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-primary rounded-full" />
        </button>
        
        <button className="p-2 hover:bg-accent rounded-lg">
          <User className="w-5 h-5" />
        </button>
      </div>
    </header>
  )
}
