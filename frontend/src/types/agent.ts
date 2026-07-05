// ========== 共享类型：Agent ==========
// F8: 统一 Agent / AgentTemplate 类型定义。
// 唯一权威来源；api/agent.ts、pages/AgentsPage.tsx、store/chatStore.ts 均 re-export 此处定义。
// 严禁在业务文件中重复声明 `interface Agent`。

/**
 * Agent 实体。字段取各消费方的并集，可选字段统一标注 ?。
 * 与后端 /api/agents 返回结构对齐。
 */
export interface Agent {
  id: string;
  name: string;
  description?: string;
  is_default?: boolean;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  system_prompt?: string;
  use_memory?: boolean;
  memory_scene?: string;
  tools?: string[];
  capabilities?: string[];
  decay_model?: string;
  use_tools?: boolean;
  vision_enabled?: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * Agent 模板（预设）。用于 AgentsPage 的新建引导。
 */
export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  icon: string;
  system_prompt: string;
  temperature: number;
  memory_scene: string;
}
