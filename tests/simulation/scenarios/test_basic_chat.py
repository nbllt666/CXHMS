"""SubTask 8.1 - 基础聊天场景。

覆盖死区：非流式/流式聊天的基础往返、脚本化回复内容、
thinking 通道输出、session_id 派生。验证响应业务内容而非仅状态码。
"""

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


def test_basic_chat_returns_scripted_reply(sim_actor):
    """非流式聊天返回脚本化回复，内容非空且包含"收到"或回显用户文本。"""
    response = sim_actor.send_message("你好")
    assert response["status"] == "success", f"状态应为 success，实际: {response.get('status')!r}"
    assert response["response"], "响应内容不应为空"
    assert "收到" in response["response"] or "你好" in response["response"], (
        f"响应应包含'收到'或'你好'，实际: {response['response']!r}"
    )


def test_streaming_chat_aggregates_content(sim_actor):
    """流式聊天聚合 content 事件为完整回复文本，raw=True 且无错误。"""
    result = sim_actor.send_streaming_message("今天天气不错")
    assert result["raw"] is True, "应至少收到一个 SSE 事件"
    assert result["error"] is None, f"流式响应不应有错误: {result['error']!r}"
    assert result["content"], "聚合 content 不应为空"
    assert "今天天气不错" in result["content"] or "收到" in result["content"], (
        f"聚合内容应包含完整回复，实际: {result['content']!r}"
    )


def test_streaming_chat_has_thinking(sim_actor):
    """流式聊天先产出 thinking 事件，内容应为"思考中..."。"""
    result = sim_actor.send_streaming_message("随便聊聊")
    assert result["thinking"], "thinking 不应为空"
    assert "思考中" in result["thinking"], (
        f"thinking 应包含'思考中'，实际: {result['thinking']!r}"
    )


def test_chat_returns_session_id(sim_actor):
    """非流式与流式响应均返回非空 session_id（派生自 agent_id）。"""
    # 非流式
    resp = sim_actor.send_message("测试会话")
    assert resp.get("session_id"), f"非流式响应应包含非空 session_id: {resp!r}"

    # 流式
    result = sim_actor.send_streaming_message("测试会话流式")
    assert result.get("session_id"), (
        f"流式响应应包含非空 session_id，events: {result.get('events')!r}"
    )
