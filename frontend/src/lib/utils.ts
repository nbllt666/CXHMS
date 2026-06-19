import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * 合并 className，结合 clsx 与 tailwind-merge
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * 将日期格式化为可读形式，例如 "2024-01-15 14:30"
 */
export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

/**
 * 将日期格式化为相对时间，例如 "3分钟前"、"昨天"
 */
export function formatRelativeTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  if (Number.isNaN(d.getTime())) return '';
  const diffMs = Date.now() - d.getTime();
  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days === 1) return '昨天';
  if (days < 7) return `${days}天前`;
  return formatDate(d);
}

/**
 * 截断文本并添加省略号
 */
export function truncate(text: string, maxLength: number): string {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

/**
 * 根据重要性等级（1-5）返回对应的背景色 class
 * 返回值形如 "bg-info"，消费方会通过 replace('bg-', '') 映射到 CSS 变量
 */
export function getImportanceColor(importance: number): string {
  const colors: Record<number, string> = {
    1: 'bg-info',
    2: 'bg-success',
    3: 'bg-warning',
    4: 'bg-accent',
    5: 'bg-error',
  };
  return colors[importance] ?? 'bg-info';
}

/**
 * 根据重要性等级（1-5）返回对应的中文标签
 */
export function getImportanceLabel(importance: number): string {
  const labels: Record<number, string> = {
    1: '极低',
    2: '低',
    3: '中',
    4: '高',
    5: '极高',
  };
  return labels[importance] ?? '未知';
}
