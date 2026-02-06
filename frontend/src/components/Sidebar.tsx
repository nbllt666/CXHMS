import { NavLink } from 'react-router-dom'
import {
  MessageSquare,
  Brain,
  Archive,
  Settings,
  Sun,
  Moon,
  Monitor,
} from 'lucide-react'
import { useThemeStore } from '../store/themeStore'
import { cn } from '../lib/utils'

const navigation = [
  { name: '对话', href: '/', icon: MessageSquare },
  { name: '记忆', href: '/memories', icon: Brain },
  { name: '归档', href: '/archive', icon: Archive },
  { name: '设置', href: '/settings', icon: Settings },
]

export function Sidebar() {
  const { theme, setTheme } = useThemeStore()

  return (
    <div className="w-64 bg-card border-r border-border flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <Brain className="w-5 h-5 text-primary-foreground" />
          </div>
          <div>
            <h1 className="font-semibold text-lg leading-tight">CXHMS</h1>
            <p className="text-xs text-muted-foreground">晨曦人格化记忆系统</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {navigation.map((item) => (
          <NavLink
            key={item.name}
            to={item.href}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              )
            }
          >
            <item.icon className="w-5 h-5" />
            {item.name}
          </NavLink>
        ))}
      </nav>

      {/* Theme Toggle */}
      <div className="p-4 border-t border-border">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">主题</span>
          <div className="flex bg-muted rounded-lg p-1">
            <button
              onClick={() => setTheme('light')}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                theme === 'light' ? 'bg-background shadow-sm' : 'hover:bg-accent'
              )}
              title="浅色"
            >
              <Sun className="w-4 h-4" />
            </button>
            <button
              onClick={() => setTheme('dark')}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                theme === 'dark' ? 'bg-background shadow-sm' : 'hover:bg-accent'
              )}
              title="深色"
            >
              <Moon className="w-4 h-4" />
            </button>
            <button
              onClick={() => setTheme('system')}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                theme === 'system' ? 'bg-background shadow-sm' : 'hover:bg-accent'
              )}
              title="跟随系统"
            >
              <Monitor className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
