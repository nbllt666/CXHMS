// ========== agentApi 单元测试 ==========
// G6: 覆盖 Agent / Tools / ACP 三组方法。
// G4 对齐：updateTool 走 PUT /api/tools/{name}（对齐后端 update_tool 端点）；
// 含字段映射：status→enabled, config→parameters；type/icon 后端不支持更新（忽略）。
// E5 回归：updateAcpAgent 抛错（不再静默返回 error）。

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

import { agentApi } from './agent';

describe('agentApi', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.put.mockReset();
    mocks.del.mockReset();
  });

  describe('Chat Agent APIs', () => {
    it('getAgents → GET /api/agents', async () => {
      const data = [{ id: 'default', name: 'Default' }];
      mocks.get.mockResolvedValueOnce({ data });
      const result = await agentApi.getAgents();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/agents');
    });

    it('getAgent → GET /api/agents/{id}', async () => {
      const data = { id: 'default', name: 'Default' };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await agentApi.getAgent('default');
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/agents/default');
    });

    it('createAgent → POST /api/agents with payload', async () => {
      const data = { id: 'new', name: 'New' };
      mocks.post.mockResolvedValueOnce({ data });
      const payload = { name: 'New', model: 'gpt-4', temperature: 0.7 };
      const result = await agentApi.createAgent(payload);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/agents', payload);
    });

    it('updateAgent → PUT /api/agents/{id}', async () => {
      const data = { id: 'default', name: 'Updated' };
      mocks.put.mockResolvedValueOnce({ data });
      const result = await agentApi.updateAgent('default', { name: 'Updated' });
      expect(result.name).toBe('Updated');
      expect(mocks.put).toHaveBeenCalledWith('/api/agents/default', { name: 'Updated' });
    });

    it('deleteAgent → DELETE /api/agents/{id}', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await agentApi.deleteAgent('agent-1');
      expect(mocks.del).toHaveBeenCalledWith('/api/agents/agent-1');
    });

    it('cloneAgent → POST /api/agents/{id}/clone', async () => {
      const data = { id: 'cloned', name: 'Default (Copy)' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await agentApi.cloneAgent('default');
      expect(result.id).toBe('cloned');
      expect(mocks.post).toHaveBeenCalledWith('/api/agents/default/clone');
    });
  });

  describe('Tools APIs', () => {
    it('getToolsStats → GET /api/tools/stats', async () => {
      const data = { total: 10, active: 8 };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await agentApi.getToolsStats();
      expect(result).toEqual(data);
      expect(mocks.get).toHaveBeenCalledWith('/api/tools/stats');
    });

    it('getTools with type → GET /api/tools with category param', async () => {
      mocks.get.mockResolvedValueOnce({ data: [] });
      await agentApi.getTools('mcp');
      expect(mocks.get).toHaveBeenCalledWith('/api/tools', { params: { category: 'mcp' } });
    });

    it('getTools with builtin → include_builtin param', async () => {
      mocks.get.mockResolvedValueOnce({ data: [] });
      await agentApi.getTools('builtin');
      expect(mocks.get).toHaveBeenCalledWith('/api/tools', { params: { include_builtin: 'true' } });
    });

    it('getTools with all → empty params', async () => {
      mocks.get.mockResolvedValueOnce({ data: [] });
      await agentApi.getTools('all');
      expect(mocks.get).toHaveBeenCalledWith('/api/tools', { params: {} });
    });

    it('createTool → POST /api/tools', async () => {
      const data = { id: 't1', name: 'New Tool' };
      mocks.post.mockResolvedValueOnce({ data });
      const payload = { name: 'New Tool', type: 'mcp' as const };
      const result = await agentApi.createTool(payload);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/tools', payload);
    });

    // G4 对齐：updateTool 走 PUT /api/tools/{name}（对齐后端 update_tool 端点）。
    // 字段映射：status→enabled, config→parameters, type/icon 忽略。
    it('updateTool → PUT /api/tools/{id} with mapped fields (G4 alignment)', async () => {
      const data = { status: 'success', message: '工具 test-tool 更新成功' };
      mocks.put.mockResolvedValueOnce({ data });
      const result = await agentApi.updateTool('test-tool', { description: 'Updated' });
      expect(result.status).toBe('success');
      expect(mocks.put).toHaveBeenCalledWith('/api/tools/test-tool', {
        description: 'Updated',
      });
    });

    it('updateTool maps status→enabled (active=true, inactive=false)', async () => {
      mocks.put.mockResolvedValueOnce({ data: { status: 'success' } });
      await agentApi.updateTool('tool-1', { status: 'inactive' });
      expect(mocks.put).toHaveBeenCalledWith('/api/tools/tool-1', {
        enabled: false,
      });
    });

    it('updateTool maps config→parameters', async () => {
      mocks.put.mockResolvedValueOnce({ data: { status: 'success' } });
      const config = { timeout: 5000 };
      await agentApi.updateTool('tool-1', { config });
      expect(mocks.put).toHaveBeenCalledWith('/api/tools/tool-1', {
        parameters: config,
      });
    });

    it('updateTool ignores type/icon (backend does not support)', async () => {
      mocks.put.mockResolvedValueOnce({ data: { status: 'success' } });
      await agentApi.updateTool('tool-1', {
        type: 'mcp' as const,
        icon: '🔧',
        description: 'Updated',
      });
      expect(mocks.put).toHaveBeenCalledWith('/api/tools/tool-1', {
        description: 'Updated',
      });
    });

    it('deleteTool → DELETE /api/tools/{id}', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await agentApi.deleteTool('tool-1');
      expect(mocks.del).toHaveBeenCalledWith('/api/tools/tool-1');
    });

    it('testTool → POST /api/tools/{id}/test', async () => {
      const data = { success: true, output: 'ok' };
      mocks.post.mockResolvedValueOnce({ data });
      const result = await agentApi.testTool('tool-1', { param: 'value' });
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/tools/tool-1/test', { param: 'value' });
    });
  });

  describe('ACP APIs', () => {
    it('getAcpStats → GET /api/acp/stats', async () => {
      const data = { total_agents: 5 };
      mocks.get.mockResolvedValueOnce({ data });
      const result = await agentApi.getAcpStats();
      expect(result).toEqual(data);
    });

    it('getAcpAgents → GET /api/acp/agents', async () => {
      const data = [{ id: 'a1', name: 'Agent 1' }];
      mocks.get.mockResolvedValueOnce({ data });
      const result = await agentApi.getAcpAgents();
      expect(result).toEqual(data);
    });

    it('createAcpAgent → POST /api/acp/connect with payload', async () => {
      const data = { id: 'c1', status: 'success' };
      mocks.post.mockResolvedValueOnce({ data });
      const payload = { agent_id: 'remote', host: 'localhost', port: 8080 };
      const result = await agentApi.createAcpAgent(payload);
      expect(result).toEqual(data);
      expect(mocks.post).toHaveBeenCalledWith('/api/acp/connect', payload);
    });

    // E5 回归：updateAcpAgent 抛错而非静默返回 {status:'error'}。
    // 调用方（React Query onError）能感知失败，避免 UI 误报更新成功。
    it('updateAcpAgent throws (E5 regression)', async () => {
      await expect(
        agentApi.updateAcpAgent('agent-1', { name: 'Updated' })
      ).rejects.toThrow(/更新 ACP agent 不被支持/);
      expect(mocks.put).not.toHaveBeenCalled();
      expect(mocks.post).not.toHaveBeenCalled();
    });

    it('deleteAcpAgent → DELETE /api/acp/connect/{id}', async () => {
      mocks.del.mockResolvedValueOnce({ data: {} });
      await agentApi.deleteAcpAgent('connection-1');
      expect(mocks.del).toHaveBeenCalledWith('/api/acp/connect/connection-1');
    });
  });
});
