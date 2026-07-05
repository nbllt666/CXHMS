// ========== 共享类型：Tool ==========
// F8: 统一 Tool / ToolStats 类型定义。
// 唯一权威来源；pages/ToolsPage.tsx re-export 此处定义。

/**
 * 工具实体。与后端 /api/tools 返回结构对齐。
 */
export interface Tool {
  id: string;
  name: string;
  description: string;
  type: 'builtin' | 'mcp' | 'custom';
  status: 'active' | 'inactive' | 'error';
  config: Record<string, unknown>;
  icon?: string;
  created_at: string;
  last_used?: string;
  use_count: number;
  parameters?: Record<string, unknown>;
  examples?: string[];
  tags?: string[];
}

/**
 * 工具统计。与后端 /api/tools/stats 返回结构对齐。
 */
export interface ToolStats {
  total_tools: number;
  active_tools: number;
  mcp_tools: number;
  native_tools: number;
  total_calls: number;
}
