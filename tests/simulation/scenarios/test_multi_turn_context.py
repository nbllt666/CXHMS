"""SubTask 8.2 - 多轮上下文保持场景。

覆盖死区：跨轮次上下文持久化、名字回溯、上一条消息回溯、
无历史时的兜底回复。验证 FakeLLMClient 的上下文感知逻辑经真实路由生效。
"""

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


def test_context_aware_name_recall(sim_actor):
    """非流式：先告知名字，再询问名字，应从历史中回溯出"小明"。"""
    sim_actor.send_message("我叫小明")
    resp = sim_actor.send_message("我叫什么")
    assert resp["status"] == "success", f"状态应为 success，实际: {resp.get('status')!r}"
    assert "小明" in resp["response"], (
        f"应从历史中回溯出'小明'，实际: {resp['response']!r}"
    )


def test_streaming_context_aware_name_recall(sim_actor):
    """流式：先告知名字，再询问名字，应从历史中回溯出"小明"。"""
    sim_actor.send_streaming_message("我叫小明")
    result = sim_actor.send_streaming_message("我叫什么")
    assert result["error"] is None, f"流式响应不应有错误: {result['error']!r}"
    assert "小明" in result["content"], (
        f"流式应从历史中回溯出'小明'，实际: {result['content']!r}"
    )


def test_context_aware_last_message_recall(sim_actor):
    """询问"我刚才说了什么"，应回显上一条用户消息内容。"""
    sim_actor.send_message("今天我去了公园")
    resp = sim_actor.send_message("我刚才说了什么")
    assert resp["status"] == "success", f"状态应为 success，实际: {resp.get('status')!r}"
    assert "今天我去了公园" in resp["response"], (
        f"应回显上一条消息，实际: {resp['response']!r}"
    )


def test_no_previous_context_returns_default_unknown(sim_actor):
    """单轮询问名字（无历史），应返回"我还不知道你的名字"。"""
    resp = sim_actor.send_message("我叫什么")
    assert resp["status"] == "success", f"状态应为 success，实际: {resp.get('status')!r}"
    assert "我还不知道你的名字" in resp["response"], (
        f"无历史时应返回默认未知回复，实际: {resp['response']!r}"
    )
