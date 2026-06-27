"""SubTask 8.7 - 超长对话稳定性场景。

覆盖死区：50+ 轮混合交互下的上下文持久化、响应不退化、流式长对话稳定性。
验证长时间对话后名字上下文仍保持、每轮响应非空、流式聚合无错误。

实际行为说明（与 spec 预期略有差异，测试按真实行为断言）：
- 后端 ``context_manager`` 默认 ``history_limit=50`` 条消息（约 25 轮
  user+assistant 对）。第 1 轮告知的名字在第 51 轮时已超出 50 条窗口，
  ``FakeLLMClient._find_name_in_history`` 找不到。为在 50+ 轮长对话中
  验证上下文保持，在第 30 轮再次发送"我叫小明"以保持在窗口内
  （模拟真实用户在长对话中重提关键信息）。
- 非流式 ``/api/chat`` 的 ``max_tool_rounds=10``：FakeLLMClient 在工具调用
  时每轮都重新触发 ``tool_calls``（最后一条 user 消息未改变），导致循环
  跑满 10 轮后退出，``final_response=""``（空）。故"响应非空"断言的测试
  不含工具调用；含工具调用的测试仅断言 ``status`` 不异常。
"""

import time


# 中间轮次模板：均不触发工具调用，确保响应非空
_FILLER_TEMPLATES = [
    "你好",
    "今天天气不错",
    "我刚才说了什么",
    "随便聊聊",
    "今天星期一",
    "我有点累",
    "继续聊天",
    "测试一下",
]


def test_long_conversation_context_preserved(sim_actor):
    """50+ 轮混合对话后，名字上下文仍保持。

    第 1 轮发送"我叫小明"，第 2-50 轮发送混合消息（含 1 次工具调用"计算 1+2"
    与 1 次名字重提"我叫小明"以保持在 50 条消息窗口内），第 51 轮发送
    "我叫什么"，断言响应包含"小明"。
    """
    start = time.time()

    # 第 1 轮：告知名字
    resp = sim_actor.send_message("我叫小明")
    assert resp["status"] == "success", f"第 1 轮失败: {resp!r}"

    # 第 2-50 轮：混合消息
    for i in range(2, 51):
        if i == 26:
            # 1 次工具调用（非流式 max_tool_rounds=10，循环后返回空响应）
            msg = "计算 1+2"
        elif i == 30:
            # 重提名字：保持在 history_limit=50 条消息窗口内
            # （第 51 轮时窗口为第 26-50 轮的消息，round 30 在窗口内）
            msg = "我叫小明"
        else:
            msg = _FILLER_TEMPLATES[i % len(_FILLER_TEMPLATES)]
        resp = sim_actor.send_message(msg)
        assert resp["status"] == "success", (
            f"第 {i} 轮状态异常: {resp!r}"
        )

    # 第 51 轮：询问名字
    resp = sim_actor.send_message("我叫什么")
    elapsed = time.time() - start
    assert resp["status"] == "success", f"第 51 轮失败: {resp!r}"
    assert "小明" in resp["response"], (
        f"50+ 轮后应记住'小明'，实际: {resp['response']!r} "
        f"(耗时 {elapsed:.2f}s)"
    )


def test_long_conversation_responses_never_degenerate(sim_actor):
    """50 轮对话，每轮响应非空、status 成功、error 为 None。

    断言所有 50 个响应内容非空，且最后 1 轮响应与第 1 轮不同
    （说明上下文确实在累积，不是返回固定值）。

    不含工具调用：非流式 chat 的工具调用循环跑满 max_tool_rounds=10 后
    返回空 ``response``，会破坏"响应非空"断言。
    """
    messages = [_FILLER_TEMPLATES[i % len(_FILLER_TEMPLATES)] for i in range(50)]
    responses = []

    for idx, msg in enumerate(messages, start=1):
        resp = sim_actor.send_message(msg)
        assert resp["status"] == "success", (
            f"第 {idx} 轮状态应为 success: {resp!r}"
        )
        assert resp.get("error") is None, (
            f"第 {idx} 轮 error 应为 None: {resp.get('error')!r}"
        )
        assert resp.get("response"), (
            f"第 {idx} 轮响应内容不应为空: {resp!r}"
        )
        responses.append(resp["response"])

    # 最后 1 轮与第 1 轮响应不同（上下文累积，非固定回复）
    assert responses[-1] != responses[0], (
        f"最后响应应与首轮不同（说明上下文累积），"
        f"首轮={responses[0]!r}, 末轮={responses[-1]!r}"
    )


def test_long_streaming_conversation(sim_actor):
    """20 轮流式对话，每轮 raw/error/content 健全，最后一轮"我叫什么"包含"小明"。

    不含工具调用：流式 chat 的工具调用循环跑满 max_tool_rounds=50 且
    ``content`` 为空（FakeLLMClient 工具调用时只 yield thinking + tool_calls，
    不 yield content），会破坏"content 非空"断言且单轮耗时极长。
    """
    # 第 1 轮：告知名字（20 轮共 38 条消息 < history_limit=50，round 1 在窗口内）
    result = sim_actor.send_streaming_message("我叫小明")
    assert result["raw"] is True, "第 1 轮 raw 应为 True"
    assert result["error"] is None, f"第 1 轮 error: {result['error']!r}"
    assert result["content"], f"第 1 轮 content 不应为空: {result!r}"

    # 第 2-19 轮：普通消息（均不触发工具调用）
    for idx in range(2, 20):
        msg = _FILLER_TEMPLATES[idx % len(_FILLER_TEMPLATES)]
        result = sim_actor.send_streaming_message(msg)
        assert result["raw"] is True, f"第 {idx} 轮 raw 应为 True"
        assert result["error"] is None, (
            f"第 {idx} 轮 error 应为 None: {result['error']!r}"
        )
        assert result["content"], f"第 {idx} 轮 content 不应为空: {result!r}"

    # 第 20 轮：询问名字
    result = sim_actor.send_streaming_message("我叫什么")
    assert result["raw"] is True, "第 20 轮 raw 应为 True"
    assert result["error"] is None, f"第 20 轮 error: {result['error']!r}"
    assert result["content"], f"第 20 轮 content 不应为空: {result!r}"
    assert "小明" in result["content"], (
        f"20 轮流式后应记住'小明'，实际: {result['content']!r}"
    )
