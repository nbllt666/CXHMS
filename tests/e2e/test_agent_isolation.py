"""G7 E2E: 多 Agent 隔离端到端测试。

覆盖死区：
    - 不同 agent_id 的记忆不互相串扰（写入 agent-A，搜索 agent-B 应为空）
    - 不同 agent_id 的上下文不互相串扰（agent-A 聊天内容不出现在 agent-B 历史中）
    - memory-agent 流式聊天可用（POST /api/memory-agent/chat/stream）

断言风格：语义断言（id 不交叉、秘密词不泄漏、SSE 聚合非空）。
隔离用 agent_id 全部以 e2e-test- 前缀标识，测试结束后 try/finally 清理。
"""

import uuid

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _e2e_memory_agent_id(prefix: str) -> str:
    """Generate a unique e2e-test agent_id for memory-isolation tests."""
    return f"e2e-test-{prefix}-{uuid.uuid4().hex[:8]}"


def _write_memory(real_app, agent_id: str, content: str, tags=None) -> int:
    """Write a long_term memory via POST /api/memories, return memory_id."""
    body = {
        "content": content,
        "type": "long_term",
        "importance": 3,
        "tags": tags or [],
        "metadata": {},
        "permanent": False,
        "workspace_id": "default",
        "agent_id": agent_id,
    }
    resp = real_app.post("/api/memories", json=body)
    assert resp.status_code == 200, f"写入记忆失败: {resp.status_code} {resp.text}"
    return resp.json()["memory_id"]


def _search_memories(real_app, agent_id: str, **kwargs):
    """Search memories via POST /api/memories/search, return response dict."""
    body = {"agent_id": agent_id, "workspace_id": "default", "limit": 20}
    body.update(kwargs)
    resp = real_app.post("/api/memories/search", json=body)
    assert resp.status_code == 200, f"搜索记忆失败: {resp.status_code} {resp.text}"
    return resp.json()


def _delete_memory(real_app, mem_id: int, agent_id: str) -> None:
    """Hard-delete a memory (best-effort, no assert)."""
    try:
        real_app.delete(
            f"/api/memories/{mem_id}",
            params={"soft_delete": "false", "agent_id": agent_id},
        )
    except Exception:
        pass


def _create_e2e_chat_agent(real_app, name_suffix: str) -> str:
    """Create a temporary E2E chat agent (use_memory/tools off for isolation)."""
    resp = real_app.post(
        "/api/agents",
        json={
            "name": f"e2e-test-iso-{name_suffix}",
            "description": "G7 E2E agent isolation agent (auto-cleaned)",
            "system_prompt": "你是 CXHMS 测试助手，请用中文简短回答。",
            "model": "main",
            "temperature": 0.3,
            "use_memory": False,
            "use_tools": False,
        },
    )
    assert resp.status_code == 200, f"创建 agent 失败: {resp.status_code} {resp.text}"
    return resp.json()["agent"]["id"]


def _delete_e2e_agent(real_app, agent_id: str) -> None:
    """Delete a temporary E2E agent (best-effort, no assert)."""
    try:
        real_app.delete(f"/api/agents/{agent_id}/context")
    except Exception:
        pass
    try:
        real_app.delete(f"/api/agents/{agent_id}")
    except Exception:
        pass


def test_memory_agent_isolation(real_app, vllm_available):
    """写入 agent-A 的记忆不应出现在 agent-B 的搜索结果中。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_a = _e2e_memory_agent_id("isoA")
    agent_b = _e2e_memory_agent_id("isoB")
    marker = f"IsoMarker-{uuid.uuid4().hex[:6]}"
    mem_id_a = None
    try:
        mem_id_a = _write_memory(
            real_app, agent_a, f"这是 agent-A 的隔离测试记忆 {marker}。"
        )
        assert mem_id_a > 0

        # Search in agent-B's memory store — should NOT contain agent-A's memory
        data_b = _search_memories(real_app, agent_b, query=marker, limit=20)
        assert data_b["status"] == "success"
        memories_b = data_b.get("memories") or []
        assert not any(m.get("id") == mem_id_a for m in memories_b), (
            f"agent-B 的搜索结果不应包含 agent-A 的记忆 id={mem_id_a}，"
            f"实际: {memories_b!r}"
        )

        # Sanity check: agent-A's search SHOULD find it
        data_a = _search_memories(real_app, agent_a, query=marker, limit=20)
        assert data_a["status"] == "success"
        memories_a = data_a.get("memories") or []
        assert any(m.get("id") == mem_id_a for m in memories_a), (
            f"agent-A 应能搜到自己的记忆 id={mem_id_a}，实际: {memories_a!r}"
        )
    finally:
        if mem_id_a:
            _delete_memory(real_app, mem_id_a, agent_a)


def test_context_agent_isolation(real_actor, real_app, vllm_available):
    """agent-A 的聊天内容不应出现在 agent-B 的历史中。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    secret = f"SecretCodeword-{uuid.uuid4().hex[:6]}"
    agent_a = _create_e2e_chat_agent(real_app, "ctxA")
    agent_b = _create_e2e_chat_agent(real_app, "ctxB")
    try:
        # Agent A chats with a secret codeword
        resp_a = real_actor.send_message(
            f"请记住这个秘密词：{secret}。", agent_id=agent_a
        )
        assert resp_a["status"] == "success", (
            f"agent-A 聊天状态异常: {resp_a.get('status')!r}"
        )

        # Agent B's history should not contain agent A's secret
        session_b = f"agent-{agent_b}"
        history_b = real_actor.get_history(session_b, limit=50)
        assert history_b["status"] == "success"
        messages_b = history_b.get("messages") or []
        contents_b = [m.get("content", "") for m in messages_b]
        assert not any(secret in c for c in contents_b), (
            f"agent-B 的历史不应包含 agent-A 的秘密词 {secret}，实际 messages: {contents_b!r}"
        )

        # Sanity check: agent-A's history SHOULD contain the secret
        session_a = f"agent-{agent_a}"
        history_a = real_actor.get_history(session_a, limit=50)
        assert history_a["status"] == "success"
        messages_a = history_a.get("messages") or []
        contents_a = [m.get("content", "") for m in messages_a]
        assert any(secret in c for c in contents_a), (
            f"agent-A 的历史应包含秘密词 {secret}，实际 messages: {contents_a!r}"
        )
    finally:
        _delete_e2e_agent(real_app, agent_a)
        _delete_e2e_agent(real_app, agent_b)


def test_memory_agent_stream_chat(real_actor, vllm_available):
    """memory-agent 流式聊天可用，聚合 content 非空或产出 tool 活动。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    # memory-agent uses the fixed memory-agent config (no temp agent needed)
    result = real_actor.memory_agent_chat("你好，请用一句话告诉我记忆库当前的状态。")
    assert result["raw"] is True, "应至少收到一个 SSE 事件"
    assert result["error"] is None, (
        f"memory-agent 流式聊天不应有错误: {result['error']!r}"
    )
    # memory-agent may emit tool_calls/tool_results (assistant-category tools) instead of
    # direct content; accept either content or tool activity as evidence of a working stream.
    assert result["content"] or result["tool_calls"] or result["tool_results"], (
        f"应至少有 content/tool_calls/tool_results 之一，实际: {result!r}"
    )
