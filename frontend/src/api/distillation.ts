// ========== Distillation APIs ==========
// RADIX-Lite v1.3.0 蒸馏服务 API 客户端
// 对应后端 /api/v1/distillation/* 端点（合并到主后端 8001）
// 包含原 4 个端点 + v1.3.0 新增 3 个批量切分/agent 创建端点

import { apiClient } from './client';

// ========== 类型定义 ==========

export type DistillationSourceType = 'text' | 'character_card' | 'image' | 'conversation_log';
export type DistillationGoal = 'memory' | 'agent' | 'memory_and_agent';
export type DistillationState =
  | 'S_INIT'
  | 'S_PREREAD'
  | 'S_QUESTION'
  | 'S_REFLECT'
  | 'S_CROSSVALIDATE'
  | 'S_EXTRACT'
  | 'S_STORAGE_DECISION'
  | 'S_FINALIZE'
  | 'S_REJECT';
export type AgentAction =
  | 'ask_user'
  | 'proceed'
  | 'reflect'
  | 'cross_validate'
  | 'extract'
  | 'decide'
  | 'finalize'
  | 'reject';

export interface StartDistillationRequest {
  source_type: DistillationSourceType;
  source_ref?: string;
  template_id: string;
  max_turns?: number;
  ask_user_on_ambiguity?: boolean;
}

export interface StartDistillationResponse {
  session_id: string;
  initial_state: string;
  preread_summary: string | null;
}

export interface AdvanceDistillationRequest {
  user_response?: string;
}

export interface AdvanceDistillationResponse {
  session_id: string;
  current_state: DistillationState;
  agent_action: AgentAction;
  next_needed: boolean;
  // 扩展字段（蒸馏过程中的中间产物）
  preread_summary?: string | null;
  ambiguity_questions?: string[];
  extracted_content?: string | null;
  quality_score?: number | null;
  turn_count?: number;
  message?: string;
}

export interface FinalizeDistillationRequest {
  override_decision?: string;
}

export interface FinalizeDistillationResponse {
  stored: boolean;
  location: 'memories' | 'permanent_memories' | 'rejected';
  memory_id: number | null;
  metadata: Record<string, unknown>;
  reason: string;
}

export interface SessionStatusResponse {
  session_id: string;
  source_type: DistillationSourceType;
  state: DistillationState;
  template_id: string;
  max_turns: number;
  ask_user_on_ambiguity: boolean;
  turns: Array<Record<string, unknown>>;
  preread_summary: string | null;
  ambiguity_questions: string[];
  extracted_content: string | null;
  quality_score: number | null;
  created_at: string;
  updated_at: string | null;
  finalized_at: string | null;
  is_finalized: boolean;
  error_message: string | null;
}

// v1.3.0 批量切分相关类型
export interface BatchStartRequest {
  source_type: DistillationSourceType;
  source_ref: string;
  template_id: string;
  max_turns?: number;
  ask_user_on_ambiguity?: boolean;
  chunk_size?: number;
  distillation_goal: DistillationGoal;
  target_agent_id?: string; // 记忆蒸馏注入的目标 agent（必须选择）
}

export interface BatchSessionItem {
  session_id: string;
  chunk_index: number;
  chunk_preview: string;
  initial_state: string;
}

export interface BatchStartResponse {
  session_group_id: string;
  total_chunks: number;
  sessions: BatchSessionItem[];
  distillation_goal: DistillationGoal;
}

export interface GroupSessionStatus {
  session_id: string;
  chunk_index: number;
  state: DistillationState;
  is_finalized: boolean;
  extracted_content: string | null;
  quality_score: number | null;
}

export interface GroupStatusResponse {
  group_id: string;
  total_count: number;
  completed_count: number;
  sessions: GroupSessionStatus[];
}

export interface FinalizeAgentResponse {
  // 原终结响应
  stored: boolean;
  location: string;
  memory_id: number | null;
  metadata: Record<string, unknown>;
  reason: string;
  // agent 创建结果（蒸馏直接创建 agent，无角色卡中间产物）
  agent_creation_result: {
    success: boolean;
    agent_id?: string;
    agent_name?: string;
    error?: string;
    character_card?: {
      name: string;
      description?: string;
    };
  };
}

// v1.4.0 角色卡导入相关类型
export interface CharacterCardData {
  spec?: string;
  spec_version?: string;
  name: string;
  description?: string;
  personality?: string;
  scenario?: string;
  first_mes?: string;
  mes_example?: string;
  alternate_greetings?: string[];
  creator_notes?: string;
  system_prompt?: string;
  post_history_instructions?: string;
  character_book?: Record<string, unknown>;
  extensions?: Record<string, unknown>;
  extra_fields?: Record<string, unknown>;
}

export interface ParseCharacterCardResponse {
  status: string;
  character_card_data: CharacterCardData;
  source_ref: string;
  source_ref_length: number;
}

// ========== API 方法 ==========

export const distillationApi = {
  // ========== 原 4 个端点 ==========

  /** 启动单次蒸馏会话 */
  async startDistillation(data: StartDistillationRequest): Promise<StartDistillationResponse> {
    const response = await apiClient.post('/api/v1/distillation/start', data);
    return response.data;
  },

  /** 推进蒸馏状态机 */
  async advanceDistillation(
    sessionId: string,
    data: AdvanceDistillationRequest
  ): Promise<AdvanceDistillationResponse> {
    const response = await apiClient.post(
      `/api/v1/distillation/${sessionId}/advance`,
      data
    );
    return response.data;
  },

  /** 终结蒸馏会话（仅记忆蒸馏） */
  async finalizeDistillation(
    sessionId: string,
    data: FinalizeDistillationRequest = {}
  ): Promise<FinalizeDistillationResponse> {
    const response = await apiClient.post(
      `/api/v1/distillation/${sessionId}/finalize`,
      data
    );
    return response.data;
  },

  /** 查询会话状态 */
  async getSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
    const response = await apiClient.get(`/api/v1/distillation/${sessionId}`);
    return response.data;
  },

  // ========== v1.3.0 新增 3 个端点 ==========

  /** 批量切分启动蒸馏（超长文本智能切分 + 多 session） */
  async startBatchDistillation(data: BatchStartRequest): Promise<BatchStartResponse> {
    const response = await apiClient.post('/api/v1/distillation/start-batch', data);
    return response.data;
  },

  /** 查询批量切分组状态 */
  async getGroupStatus(groupId: string): Promise<GroupStatusResponse> {
    const response = await apiClient.get(`/api/v1/distillation/group/${groupId}`);
    return response.data;
  },

  /** 终结并创建角色卡 agent */
  async finalizeWithAgentCreation(
    sessionId: string,
    data: FinalizeDistillationRequest = {}
  ): Promise<FinalizeAgentResponse> {
    const response = await apiClient.post(
      `/api/v1/distillation/${sessionId}/finalize-agent`,
      data
    );
    return response.data;
  },

  // ========== v1.4.0 角色卡导入 2 个端点 ==========

  /** 解析 PNG 角色卡（文件上传） */
  async parseCharacterCardFromFile(file: File): Promise<ParseCharacterCardResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post(
      '/api/v1/distillation/parse-character-card',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data;
  },

  /** 解析 JSON 角色卡（JSON 内容） */
  async parseCharacterCardFromJson(
    jsonContent: string | object
  ): Promise<ParseCharacterCardResponse> {
    const response = await apiClient.post(
      '/api/v1/distillation/parse-character-card',
      { json_content: jsonContent }
    );
    return response.data;
  },
};
