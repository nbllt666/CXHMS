import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatRelativeTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  
  if (days > 0) return `${days}天前`
  if (hours > 0) return `${hours}小时前`
  if (minutes > 0) return `${minutes}分钟前`
  return '刚刚'
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

export function getImportanceColor(importance: number): string {
  switch (importance) {
    case 5:
      return 'bg-red-500'
    case 4:
      return 'bg-orange-500'
    case 3:
      return 'bg-yellow-500'
    case 2:
      return 'bg-blue-500'
    default:
      return 'bg-gray-500'
  }
}

export function getImportanceLabel(importance: number): string {
  switch (importance) {
    case 5:
      return '极高'
    case 4:
      return '高'
    case 3:
      return '中'
    case 2:
      return '低'
    default:
      return '极低'
  }
}
