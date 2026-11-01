// ========== knowledgeApi 单元测试 ==========
// Task 8：覆盖上传 FormData、经验写入、条目查询/删除、检索载荷、文档查询/删除、健康检查与错误透传。
// 约定：apiClient baseURL 为根地址，因此请求路径一律为 /api/api/knowledge/*（与 memory.ts 一致）。

import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}));

vi.mock('./client', () => ({
  apiClient: {
    get: mocks.get,
    post: mocks.post,
    put: mocks.put,
    delete: mocks.del,
  },
}));

import { knowledgeApi } from './knowledge';
import type { KnowledgeDocument } from './knowledge';

const docSummary: {
  document_id: string;
  parse_status: KnowledgeDocument['parse_status'];
  deduplicated: boolean;
} = {
  document_id: 'doc-1',
  parse_status: 'pending',
  deduplicated: false,
};

describe('knowledgeApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('uploadDocument', () => {
    it('POST /api/knowledge/upload 以 multipart 发送 FormData', async () => {
      const formData = new FormData();
      formData.append('file', new File(['hello'], 'a.txt', { type: 'text/plain' }));
      formData.append('agent_id', 'agent-1');
      mocks.post.mockResolvedValueOnce({ data: docSummary });

      const result = await knowledgeApi.uploadDocument(formData);

      expect(result).toEqual(docSummary);
      expect(mocks.post).toHaveBeenCalledTimes(1);
      const [url, body, config] = mocks.post.mock.calls[0];
      expect(url).toBe('/api/knowledge/upload');
      expect(body).toBe(formData);
      expect(config.headers).toEqual({ 'Content-Type': 'multipart/form-data' });
      expect(config.onUploadProgress).toBeUndefined();
    });

    it('onProgress 回调收到 0-100 百分比', async () => {
      const formData = new FormData();
      formData.append('file', new File(['hello'], 'b.txt', { type: 'text/plain' }));
      mocks.post.mockResolvedValueOnce({ data: { ...docSummary, document_id: 'doc-2' } });
      const onProgress = vi.fn();

      const result = await knowledgeApi.uploadDocument(formData, onProgress);
      expect(result.document_id).toBe('doc-2');

      const config = mocks.post.mock.calls[0][2];
      config.onUploadProgress({ loaded: 40, total: 100 });
      expect(onProgress).toHaveBeenCalledWith(40);

      config.onUploadProgress({ loaded: 100, total: 100 });
      expect(onProgress).toHaveBeenLastCalledWith(100);
    });

    it('total 缺失时进度回落为 0', async () => {
      mocks.post.mockResolvedValueOnce({ data: docSummary });
      const onProgress = vi.fn();
      await knowledgeApi.uploadDocument(new FormData(), onProgress);

      const config = mocks.post.mock.calls[0][2];
      config.onUploadProgress({ loaded: 10 });
      expect(onProgress).toHaveBeenCalledWith(0);
    });

    it('错误直接透传，不做静默兜底', async () => {
      mocks.post.mockRejectedValueOnce({ response: { status: 413 } });
      await expect(knowledgeApi.uploadDocument(new FormData())).rejects.toEqual({
        response: { status: 413 },
      });
    });
  });

  describe('entries', () => {
    it('createEntry → POST /api/knowledge/entries 原样发送载荷', async () => {
      const payload = {
        agent_id: 'agent-1',
        title: '经验标题',
        content: '经验内容',
        tags: ['t1', 't2'],
        importance: 4,
      };
      const data = { item_id: 'i-1', ...payload, item_type: 'experience', created_at: 'now' };
      mocks.post.mockResolvedValueOnce({ data });

      const result = await knowledgeApi.createEntry(payload);

      expect(result.item_id).toBe('i-1');
      expect(mocks.post).toHaveBeenCalledWith('/api/knowledge/entries', payload);
    });
  });

  describe('items', () => {
    it('listItems → GET /api/knowledge/items 携带全部查询参数', async () => {
      const data = { items: [], total: 0 };
      mocks.get.mockResolvedValueOnce({ data });
      const params = {
        agent_id: 'agent-1',
        item_type: 'doc_chunk',
        tags: 't1,t2',
        q: '关键词',
        limit: 20,
        offset: 0,
      };

      const result = await knowledgeApi.listItems(params);

      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/items', { params });
    });

    it('getItem → GET /api/knowledge/items/{itemId} 且 agent_id 走 query', async () => {
      const data = { item_id: 'i-1', content: 'c' };
      mocks.get.mockResolvedValueOnce({ data });

      const result = await knowledgeApi.getItem('i-1', 'agent-1');

      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/items/i-1', {
        params: { agent_id: 'agent-1' },
      });
    });

    it('getItem 未指定 agent 时不发送 agent_id 键', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await knowledgeApi.getItem('i-1');
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/items/i-1', { params: {} });
    });

    it('deleteItem → DELETE /api/knowledge/items/{itemId}', async () => {
      mocks.del.mockResolvedValueOnce({ data: { success: true } });
      const result = await knowledgeApi.deleteItem('i-1', 'agent-1');

      expect(result).toEqual({ success: true });
      expect(mocks.del).toHaveBeenCalledWith('/api/knowledge/items/i-1', {
        params: { agent_id: 'agent-1' },
      });
    });
  });

  describe('search', () => {
    it('search → POST /api/knowledge/search 原样发送检索载荷', async () => {
      const payload = {
        agent_id: 'agent-1',
        query: '记忆衰减',
        top_k: 5,
        tags: ['记忆'],
        item_type: 'experience',
      };
      const data = {
        hits: [{ item_id: 'i-1', score: 0.87 }],
        total: 1,
        fallback: false,
      };
      mocks.post.mockResolvedValueOnce({ data });

      const result = await knowledgeApi.search(payload);

      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/knowledge/search', payload);
    });

    it('search 错误透传', async () => {
      const error = new Error('search failed');
      mocks.post.mockRejectedValueOnce(error);
      await expect(knowledgeApi.search({ query: 'q' })).rejects.toThrow('search failed');
    });
  });

  describe('documents', () => {
    it('listDocuments → GET /api/knowledge/documents 携带分页参数', async () => {
      const data = { documents: [], total: 0 };
      mocks.get.mockResolvedValueOnce({ data });

      const result = await knowledgeApi.listDocuments({
        agent_id: 'agent-1',
        limit: 10,
        offset: 0,
      });

      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/documents', {
        params: { agent_id: 'agent-1', limit: 10, offset: 0 },
      });
    });

    it('listDocuments 无参数时发送空 params', async () => {
      mocks.get.mockResolvedValueOnce({ data: { documents: [], total: 0 } });
      await knowledgeApi.listDocuments();
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/documents', { params: {} });
    });

    it('getDocument → GET /api/knowledge/documents/{documentId}', async () => {
      const data = { document_id: 'doc-1', parse_status: 'parsed', chunk_count: 3 };
      mocks.get.mockResolvedValueOnce({ data });

      const result = await knowledgeApi.getDocument('doc-1', 'agent-1');

      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/documents/doc-1', {
        params: { agent_id: 'agent-1' },
      });
    });

    it('deleteDocument → DELETE /api/knowledge/documents/{documentId}', async () => {
      mocks.del.mockResolvedValueOnce({ data: { success: true } });
      const result = await knowledgeApi.deleteDocument('doc-1', 'agent-1');

      expect(result).toEqual({ success: true });
      expect(mocks.del).toHaveBeenCalledWith('/api/knowledge/documents/doc-1', {
        params: { agent_id: 'agent-1' },
      });
    });
  });

  describe('health', () => {
    it('getHealth → GET /api/knowledge/health 携带 agent_id', async () => {
      const data = {
        enabled: true,
        vector_enabled: true,
        fts_enabled: false,
        asr_provider: 'faster_whisper',
        ffmpeg_available: true,
      };
      mocks.get.mockResolvedValueOnce({ data });

      const result = await knowledgeApi.getHealth('agent-1');

      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/health', {
        params: { agent_id: 'agent-1' },
      });
    });

    it('getHealth 无 agent 时 params 为空对象', async () => {
      mocks.get.mockResolvedValueOnce({ data: { enabled: false } });
      await knowledgeApi.getHealth();
      expect(mocks.get).toHaveBeenCalledWith('/api/knowledge/health', { params: {} });
    });

    it('getHealth 错误透传（503 知识库未启用）', async () => {
      mocks.get.mockRejectedValueOnce({ response: { status: 503 } });
      await expect(knowledgeApi.getHealth()).rejects.toEqual({ response: { status: 503 } });
    });
  });
});
