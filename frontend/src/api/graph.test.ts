// ========== graphApi 单元测试 ==========
// G6: 覆盖图节点/边/遍历/算法/导出。
// B9 回归契约：写操作（createNode/updateNode/deleteNode/createEdge/traverse*）使用 POST/PUT/DELETE。

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

import { graphApi } from './graph';

describe('graphApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('Nodes', () => {
    it('createNode → POST /api/nodes with agent_id injected', async () => {
      const data = { id: 'n1', type: 'concept' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await graphApi.createNode(
        { type: 'concept', properties: { name: 'X' } },
        'agent-1'
      );
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/nodes', {
        type: 'concept',
        properties: { name: 'X' },
        agent_id: 'agent-1',
      });
    });

    it('createNode defaults agent_id to "default"', async () => {
      mocks.post.mockResolvedValueOnce({ data: {} });
      await graphApi.createNode({ type: 'concept' });
      expect(mocks.post).toHaveBeenCalledWith('/api/nodes', { type: 'concept', agent_id: 'default' });
    });

    it('getNodes → GET /api/nodes/search with params', async () => {
      mocks.get.mockResolvedValueOnce({ data: [] });
      await graphApi.getNodes({ node_type: 'concept', limit: 10 });
      expect(mocks.get).toHaveBeenCalledWith('/api/nodes/search', {
        params: { node_type: 'concept', limit: 10 },
      });
    });

    it('getNode → GET /api/nodes/{id} with agent_id param', async () => {
      mocks.get.mockResolvedValueOnce({ data: { id: 'n1' } });
      await graphApi.getNode('n1', 'agent-1');
      expect(mocks.get).toHaveBeenCalledWith('/api/nodes/n1', { params: { agent_id: 'agent-1' } });
    });

    it('updateNode → PUT /api/nodes/{id} with agent_id', async () => {
      mocks.put.mockResolvedValueOnce({ data: {} });
      await graphApi.updateNode('n1', { type: 'updated' }, 'agent-1');
      expect(mocks.put).toHaveBeenCalledWith('/api/nodes/n1', { type: 'updated', agent_id: 'agent-1' });
    });

    it('deleteNode → DELETE /api/nodes/{id} with cascade + agent_id', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await graphApi.deleteNode('n1', true, 'agent-1');
      expect(mocks.del).toHaveBeenCalledWith('/api/nodes/n1', {
        params: { cascade: true, agent_id: 'agent-1' },
      });
    });
  });

  describe('Edges', () => {
    it('createEdge → POST /api/edges with agent_id', async () => {
      const data = { id: 'e1' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await graphApi.createEdge(
        { source_id: 'n1', target_id: 'n2', relation_type: 'relates_to' },
        'agent-1'
      );
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/edges', {
        source_id: 'n1',
        target_id: 'n2',
        relation_type: 'relates_to',
        agent_id: 'agent-1',
      });
    });

    it('getEdges → GET /api/edges/search with params', async () => {
      mocks.get.mockResolvedValueOnce({ data: [] });
      await graphApi.getEdges({ relation_type: 'relates_to', limit: 5 });
      expect(mocks.get).toHaveBeenCalledWith('/api/edges/search', {
        params: { relation_type: 'relates_to', limit: 5 },
      });
    });

    it('deleteEdge → DELETE /api/edges/{id} with agent_id', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await graphApi.deleteEdge('e1', 'agent-1');
      expect(mocks.del).toHaveBeenCalledWith('/api/edges/e1', { params: { agent_id: 'agent-1' } });
    });
  });

  describe('Traversal & Search', () => {
    it('traverseBFS → POST /api/traverse/bfs', async () => {
      const data = { visited: ['n1', 'n2'] };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await graphApi.traverseBFS({ start_id: 'n1', max_depth: 2 });
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/traverse/bfs', { start_id: 'n1', max_depth: 2 });
    });

    it('traverseDFS → POST /api/traverse/dfs', async () => {
      mocks.post.mockResolvedValueOnce({ data: {} });
      await graphApi.traverseDFS({ start_id: 'n1' });
      expect(mocks.post).toHaveBeenCalledWith('/api/traverse/dfs', { start_id: 'n1' });
    });

    it('getShortestPath → GET /api/paths/shortest with params', async () => {
      mocks.get.mockResolvedValueOnce({ data: { path: [] } });
      await graphApi.getShortestPath({ start_id: 'n1', end_id: 'n2' });
      expect(mocks.get).toHaveBeenCalledWith('/api/paths/shortest', {
        params: { start_id: 'n1', end_id: 'n2' },
      });
    });

    it('graphSemanticSearch → POST /api/semantic/search', async () => {
      mocks.post.mockResolvedValueOnce({ data: [] });
      await graphApi.graphSemanticSearch({ query: 'concept', limit: 5 });
      expect(mocks.post).toHaveBeenCalledWith('/api/semantic/search', { query: 'concept', limit: 5 });
    });

    it('graphHybridSearch → POST /api/semantic/hybrid', async () => {
      mocks.post.mockResolvedValueOnce({ data: [] });
      await graphApi.graphHybridSearch({ query: 'x', limit: 10 });
      expect(mocks.post).toHaveBeenCalledWith('/api/semantic/hybrid', { query: 'x', limit: 10 });
    });
  });

  describe('Stats & Algorithms', () => {
    it('getGraphStats → GET /api/stats with agent_id', async () => {
      mocks.get.mockResolvedValueOnce({ data: { nodes: 10, edges: 5 } });
      await graphApi.getGraphStats('agent-1');
      expect(mocks.get).toHaveBeenCalledWith('/api/stats', { params: { agent_id: 'agent-1' } });
    });

    it('getGraphHealth → GET /api/health with agent_id', async () => {
      mocks.get.mockResolvedValueOnce({ data: { healthy: true } });
      await graphApi.getGraphHealth('agent-1');
      expect(mocks.get).toHaveBeenCalledWith('/api/health', { params: { agent_id: 'agent-1' } });
    });

    it('pageRank → GET /api/algorithm/pagerank', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await graphApi.pageRank({ damping: 0.85 });
      expect(mocks.get).toHaveBeenCalledWith('/api/algorithm/pagerank', { params: { damping: 0.85 } });
    });

    it('exportGraph → GET /api/export/{format}', async () => {
      mocks.get.mockResolvedValueOnce({ data: {} });
      await graphApi.exportGraph('json', 'agent-1');
      expect(mocks.get).toHaveBeenCalledWith('/api/export/json', { params: { agent_id: 'agent-1' } });
    });
  });
});
