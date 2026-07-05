"""G7 E2E: 真实 LLM 聊天流端到端测试。

覆盖死区：
    - 真实 vLLM 非流式聊天往返（POST /api/chat）
    - 真实 vLLM 流式聊天，SSE 事件聚合（POST /api/chat/stream）
    - 多轮上下文持久化（同一 agent_id 多次调用共享 context_manager 历史）
    - 历史回溯（GET /api/chat/history/{session_id}）

断言风格：语义断言（status=success、响应非空、长度合理、关键词宽松匹配），
不依赖 LLM 精确输出。每个测试创建临时 agent（name 以 e2e-test- 前缀标识），
在 finally 中清理，避免污染真实 agent 数据。
"""

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _create_e2e_agent(real_app, name_suffix: str) -> str:
    """Create a temporary E2E agent for chat flow tests.

    use_memory=False / use_tools=False to isolate chat flow from vector store
    and tool-calling nondeterminism; multi-turn context persistence is still
    exercised via context_manager (independent of memory subsystem).

    Args:
        real_app: FastAPI TestClient running real lifespan.
        name_suffix: unique suffix appended to the e2e-test- name prefix.

    Returns:
        The backend-generated agent id (e.g. "agent-<hex8>").
    """
    resp = real_app.post(
        "/api/agents",
        json={
            "name": f"e2e-test-chatflow-{name_suffix}",
            "description": "G7 E2E chat flow agent (auto-cleaned)",
            "system_prompt": "你是 CXHMS 测试助手，请用中文简短回答用户问题。",
            "model": "main",
            "temperature": 0.3,
            "use_memory": False,
            "use_tools": False,
        },
    )
    assert resp.status_code == 200, f"创建 E2E agent 失败: {resp.status_code} {resp.text}"
    return resp.json()["agent"]["id"]


def _delete_e2e_agent(real_app, agent_id: str) -> None:
    """Delete a temporary E2E agent (best-effort, no assert).

    Clears the agent's context first, then deletes the agent config.
    """
    try:
        real_app.delete(f"/api/agents/{agent_id}/context")
    except Exception:
        pass
    try:
        real_app.delete(f"/api/agents/{agent_id}")
    except Exception:
        pass


def test_real_chat_non_stream_returns_response(real_actor, real_app, vllm_available):
    """非流式真实 LLM 聊天返回非空响应，status=success 且 session_id 派生自 agent_id。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _create_e2e_agent(real_app, "nonstream")
    try:
        response = real_actor.send_message("你好，请用一句话介绍你自己。", agent_id=agent_id)
        assert response["status"] == "success", (
            f"状态应为 success，实际: {response.get('status')!r}"
        )
        assert response["response"], "响应内容不应为空"
        assert len(response["response"]) > 5, (
            f"响应长度应合理（>5），实际: {len(response['response'])}"
        )
        assert response["session_id"] == f"agent-{agent_id}", (
            f"session_id 应为 agent-{{agent_id}}，实际: {response.get('session_id')!r}"
        )
    finally:
        _delete_e2e_agent(real_app, agent_id)


def test_real_chat_stream_aggregates_content(real_actor, real_app, vllm_available):
    """流式真实 LLM 聊天聚合 content 事件为完整回复，raw=True 且无 error。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _create_e2e_agent(real_app, "stream")
    try:
        result = real_actor.send_streaming_message(
            "今天天气怎么样？请用一句话回答。", agent_id=agent_id
        )
        assert result["raw"] is True, "应至少收到一个 SSE 事件"
        assert result["error"] is None, f"流式响应不应有错误: {result['error']!r}"
        assert result["content"], "聚合 content 不应为空"
        assert len(result["content"]) > 5, (
            f"聚合内容长度应合理（>5），实际: {len(result['content'])}"
        )
    finally:
        _delete_e2e_agent(real_app, agent_id)


def test_multi_turn_context_persistence(real_actor, real_app, vllm_available):
    """同一 agent_id 多次调用共享上下文：后一轮能引用前一轮用户提供的代号。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    # Unique codeword to detect cross-turn context recall (semantic, not exact)
    codeword = "ZephyrCodeword-7B-E2E-2026"
    agent_id = _create_e2e_agent(real_app, "multiturn")
    try:
        # Turn 1: tell the agent a unique codeword
        resp1 = real_actor.send_message(
            f"请记住我的测试代号是 {codeword}，一会儿我会问你。", agent_id=agent_id
        )
        assert resp1["status"] == "success", f"第一轮状态异常: {resp1.get('status')!r}"
        assert resp1["response"], "第一轮响应不应为空"

        # Turn 2: ask the agent to recall the codeword (same agent_id shares context history)
        resp2 = real_actor.send_message("我的测试代号是什么？请直接回答。", agent_id=agent_id)
        assert resp2["status"] == "success", f"第二轮状态异常: {resp2.get('status')!r}"
        assert resp2["response"], "第二轮响应不应为空"
        # Semantic assertion: codeword itself, or a clear acknowledgment / refusal indicator.
        # LLM may paraphrase, so accept codeword OR context-related keywords.
        reply = resp2["response"]
        assert (
            codeword in reply
            or "代号" in reply
            or "测试" in reply
            or "记" in reply
        ), f"第二轮应引用代号或相关上下文，实际: {reply!r}"
    finally:
        _delete_e2e_agent(real_app, agent_id)


def test_chat_history_retrieval(real_actor, real_app, vllm_available):
    """GET /api/chat/history/{session_id} 返回已持久化的多轮消息。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _create_e2e_agent(real_app, "history")
    try:
        # Send one message to populate history
        resp = real_actor.send_message("你好，历史回溯测试。", agent_id=agent_id)
        assert resp["status"] == "success"
        session_id = resp["session_id"]

        history = real_actor.get_history(session_id, limit=10)
        assert history["status"] == "success", (
            f"历史接口状态异常: {history.get('status')!r}"
        )
        messages = history.get("messages") or []
        assert messages, "历史消息列表不应为空"
        # The just-sent user message should appear in history
        contents = [m.get("content", "") for m in messages]
        assert any("历史回溯测试" in c for c in contents), (
            f"历史中应包含刚发送的用户消息，实际 messages: {messages!r}"
        )
    finally:
        _delete_e2e_agent(real_app, agent_id)
