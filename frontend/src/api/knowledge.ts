// ========== Knowledge APIs ==========
// 独立知识库（模块11）前端 API 客户端。
// 对应后端路由 /api/knowledge/*（apiClient baseURL 为根地址，路径必须显式带 /api 前缀，
// 与 frontend/src/api/memory.ts 的 /api/memories 保持一致）。
// 错误不吞：所有方法直接透传 axios 异常，由调用方（React Query）统一处理。

import type { AxiosProgressEvent } from 'axios';
import { apiClient } from './client';

// ========== 冻结类型 ==========

export interface KnowledgeItem {
  item_id: string;
  agent_id: string;
  item_type: 'doc_chunk' | 'experience';
  title?: string;
  content: string;
  tags: string[];
  importance: number;
  document_id?: string | null;
  created_at: string;
}

export interface KnowledgeDocument {
  document_id: string;
  agent_id: string;
  filename: string;
  mime: string;
  size_bytes: number;
  parse_status: 'pending' | 'parsing' | 'parsed' | 'failed' | 'unsupported';
  parse_error?: string | null;
  created_at: string;
}

export interface KnowledgeSearchHit extends KnowledgeItem {
  score: number;
}

// ========== 内部工具 ==========

/** 构造 agent_id 查询参数；未指定时不发送该键 */
const agentParams = (agentId?: string): { params: { agent_id?: string } } => ({
  params: agentId ? { agent_id: agentId } : {},
});

// ========== API 方法 ==========

export const knowledgeApi = {
  /** 上传文档（multipart/form-data）；后台解析，返回文档摘要 */
  async uploadDocument(
    formData: FormData,
    onProgress?: (p: number) => void
  ): Promise<{
    document_id: string;
    parse_status: KnowledgeDocument['parse_status'];
    deduplicated: boolean;
  }> {
    const response = await apiClient.post('/api/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress
        ? (event: AxiosProgressEvent) => {
            const total = event.total ?? 0;
            const percent = total > 0 ? Math.round((event.loaded / total) * 100) : 0;
            onProgress(percent);
          }
        : undefined,
    });
    return response.data;
  },

  /** 写入经验条目（item_type=experience） */
  async createEntry(body: {
    agent_id?: string;
    title?: string;
    content: string;
    tags?: string[];
    importance?: number;
  }): Promise<KnowledgeItem & { deduplicated?: boolean }> {
    const response = await apiClient.post('/api/knowledge/entries', body);
    return response.data;
  },

  /** 条目列表（支持类型/标签/关键词/分页过滤） */
  async listItems(params: {
    agent_id?: string;
    item_type?: string;
    tags?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ items: KnowledgeItem[]; total: number }> {
    const response = await apiClient.get('/api/knowledge/items', { params });
    return response.data;
  },

  /** 条目详情 */
  async getItem(itemId: string, agentId?: string): Promise<KnowledgeItem> {
    const response = await apiClient.get(
      `/api/knowledge/items/${encodeURIComponent(itemId)}`,
      agentParams(agentId)
    );
    return response.data;
  },

  /** 软删除条目（同时删除其向量） */
  async deleteItem(itemId: string, agentId?: string): Promise<{ success: boolean }> {
    const response = await apiClient.delete(
      `/api/knowledge/items/${encodeURIComponent(itemId)}`,
      agentParams(agentId)
    );
    return response.data;
  },

  /** 混合检索（向量 + FTS，服务端降级并返回 fallback 标记） */
  async search(body: {
    agent_id?: string;
    query: string;
    top_k?: number;
    tags?: string[];
    item_type?: string;
  }): Promise<{ hits: KnowledgeSearchHit[]; total?: number; fallback?: boolean }> {
    const response = await apiClient.post('/api/knowledge/search', body);
    return response.data;
  },

  /** 文档列表与解析状态 */
  async listDocuments(params?: {
    agent_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ documents: KnowledgeDocument[]; total: number }> {
    const response = await apiClient.get('/api/knowledge/documents', { params: params ?? {} });
    return response.data;
  },

  /** 文档详情：解析状态 + 文本预览 + 分块数 */
  async getDocument(
    documentId: string,
    agentId?: string
  ): Promise<KnowledgeDocument & { text_preview?: string | null; chunk_count?: number }> {
    const response = await apiClient.get(
      `/api/knowledge/documents/${encodeURIComponent(documentId)}`,
      agentParams(agentId)
    );
    return response.data;
  },

  /** 删除文档（级联删分块 + 向量 + 物理文件） */
  async deleteDocument(documentId: string, agentId?: string): Promise<{ success: boolean }> {
    const response = await apiClient.delete(
      `/api/knowledge/documents/${encodeURIComponent(documentId)}`,
      agentParams(agentId)
    );
    return response.data;
  },

  /** 知识库健康状态 */
  async getHealth(agentId?: string): Promise<{
    enabled: boolean;
    vector_enabled: boolean;
    fts_enabled: boolean;
    asr_provider?: string | null;
    ffmpeg_available: boolean;
  }> {
    const response = await apiClient.get('/api/knowledge/health', agentParams(agentId));
    return response.data;
  },
};
