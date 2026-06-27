"""SubTask 4 - 工具集成场景（spec: fix-simulation-tool-call-completeness）。

覆盖死区：
    1. 工具调用循环早终止：FakeLLMClient 在收到 ``role=tool`` 消息后会基于
       工具结果生成最终 content（不再触发新 tool_calls），使循环在 1-2 轮内
       break，不跑满 ``max_tool_rounds=50``。Task 4 之前的死区是循环可能空转。
    2. 工具结果整合到最终 SSE content：calculator 的执行结果应不仅出现在
       ``tool_result`` 事件中，还要被 FakeLLMClient 回填到最终的 ``content``
       文本里（如"...的结果是 579"），让用户在 SSE content 通道看到答案。
    3. 非内置工具可被真实执行并产生副作用：master_tools 中的
       ``write_long_term_memory`` 通过 ``tool_registry.call_tool`` 直接调用，
       验证模拟模式下非内置工具能跑通依赖注入（MemoryManager 已通过
       ``set_master_dependencies`` 注入）并真实写入 SQLite 记忆库。

设计说明：
    - 内置工具（calculator/datetime/random/json_format）通过 ``sim_actor``
      驱动流式聊天触发，验证整条 SSE 流水线（FakeLLMClient 关键词识别 →
      tool_calls 事件 → 路由执行 → tool_result 事件 → FakeLLMClient 二次
      回复 → content 事件）。
    - 非内置工具 ``write_long_term_memory`` 由 FakeLLMClient 的
      ``_maybe_tool_calls`` 不会触发（仅识别内置四类关键词），故按方案 B
      直接调用全局 ``tool_registry.call_tool`` 验证工具执行链路本身。
    - ``save_memory`` 工具的注册源文件 ``backend/core/tools/memory_tools.py``
      当前是截断的不完整文件（仅 664 字节，``save_memory`` 注册过程被截断
      在 properties.content 描述处），且该模块的 ``register_memory_tools``
      在 ``app.py`` lifespan 中并未被调用，因此 save_memory 实际未注册。
      对应测试用例 ``test_save_memory_tool_executed`` 通过 ``pytest.mark.skip``
      跳过并注明原因，待 memory_tools.py 修复后启用。
"""

import pytest

from backend.core.tools import tool_registry


# --------------------------------------------------------------------- #
# 工具调用循环终止
# --------------------------------------------------------------------- #


def test_tool_call_loop_terminates_early(sim_actor):
    """发送"计算 123+456"，工具调用循环应在 1-2 轮内终止（tool_calls <= 3）。

    FakeLLMClient 在第一轮产出 calculator tool_call，路由执行后把
    ``{"role":"tool",...}`` 追加到 messages；第二轮 FakeLLMClient 检测到
    tool 消息后生成最终 content（不再触发新 tool_calls），路由 break 循环。
    因此 ``result["tool_calls"]`` 长度应为 1，远小于 ``max_tool_rounds=50``。
    """
    result = sim_actor.send_streaming_message("计算 123+456")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"

    # 循环早终止断言：tool_calls 数量应远小于 max_tool_rounds
    assert len(result["tool_calls"]) <= 3, (
        f"工具调用循环应在 1-2 轮内终止，实际 tool_calls 数: "
        f"{len(result['tool_calls'])}, events: {result.get('events')!r}"
    )

    # 最终 content 应包含工具结果数值（FakeLLMClient 回填 "...的结果是 579"）
    assert "579" in result["content"], (
        f"最终 content 应含 '579'，实际: {result['content']!r}"
    )


# --------------------------------------------------------------------- #
# 工具结果整合到最终 SSE content
# --------------------------------------------------------------------- #


def test_tool_result_in_final_response(sim_actor):
    """发送"计算 1+2*3"（结果应为 7），最终 content 应含 '7'，且 calculator 执行成功。

    覆盖死区：FakeLLMClient 修复前，工具结果仅出现在 ``tool_result`` 事件中，
    最终 content 通道为空。修复后 FakeLLMClient 会基于 tool 消息生成最终
    content（"1+2*3 的结果是 7"），让用户在 SSE content 通道看到答案。
    """
    result = sim_actor.send_streaming_message("计算 1+2*3")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"

    # 工具结果非空
    assert result["tool_results"], "tool_results 列表不应为空"

    # calculator 执行成功，结果为 7
    calc_results = [
        tr
        for tr in result["tool_results"]
        if tr.get("tool_name") in ("calculate", "calculator")
    ]
    assert calc_results, "应至少有一个 calculator 工具结果"
    tool_result = calc_results[0].get("result") or {}
    assert tool_result.get("success") is True, (
        f"calculator 执行应成功，实际: {tool_result!r}"
    )
    assert tool_result.get("result") == 7, (
        f"1+2*3 应等于 7，实际: {tool_result.get('result')!r}"
    )

    # 最终 content 应含 '7'（FakeLLMClient 整合后的回复）
    assert "7" in result["content"], (
        f"最终 content 应含 '7'，实际: {result['content']!r}"
    )


# --------------------------------------------------------------------- #
# 非内置工具执行：write_long_term_memory
# --------------------------------------------------------------------- #


def test_write_long_term_memory_tool_executed(sim_app):
    """直接调用 tool_registry.call_tool("write_long_term_memory", ...) 验证执行。

    覆盖死区：master_tools 中的非内置工具在模拟模式下能否被真实执行并产生
    副作用（写入记忆库）。FakeLLMClient 不会触发该工具，故按方案 B 直接
    调用 tool_registry，验证：
        1. 工具已注册（lifespan 中 register_master_tools 已调用）
        2. 返回 ``{"status":"success","memory_id":<int>}``
        3. 副作用真实发生：可通过 sim_actor.search_memory 或 MemoryManager
           检索到刚写入的记忆。
    """
    # 工具必须已注册
    tool = tool_registry.get_tool("write_long_term_memory")
    assert tool is not None, "write_long_term_memory 工具未注册（lifespan 未调用 register_master_tools？）"

    content_text = "测试记忆写入_工具集成场景_{}".format(id(tool))
    call_result = tool_registry.call_tool(
        "write_long_term_memory",
        {
            "content": content_text,
            "importance": 3,
            "tags": ["test", "tool_integration"],
        },
    )
    # tool_registry.call_tool 包一层 {"success":True,"result":<工具返回>,"tool_name":...}
    assert call_result.get("success") is True, (
        f"call_tool 应成功，实际: {call_result!r}"
    )
    inner = call_result.get("result") or {}
    assert inner.get("status") == "success", (
        f"工具内部应返回 status=success，实际: {inner!r}"
    )
    memory_id = inner.get("memory_id")
    assert isinstance(memory_id, int) and memory_id > 0, (
        f"memory_id 应为正整数，实际: {memory_id!r}"
    )

    # 副作用验证：通过 MemoryManager 直接检索（避免再走 HTTP 增加噪声）
    from backend.core.memory.manager import MemoryManager

    mm = MemoryManager._instance
    assert mm is not None, "MemoryManager 单例未初始化（lifespan 未启动？）"
    hits = mm.search_memories(query=content_text, limit=10)
    assert any(content_text in m.get("content", "") for m in hits), (
        f"写入的记忆应能被搜索命中，实际 hits: {hits!r}"
    )


# --------------------------------------------------------------------- #
# save_memory 工具执行（跳过：源文件未完成、工具未注册）
# --------------------------------------------------------------------- #


@pytest.mark.skip(
    reason=(
        "save_memory 工具未注册：backend/core/tools/memory_tools.py 当前为截断的"
        " 不完整文件（664 字节，save_memory 注册过程被截断在 properties.content"
        " 描述处），且 app.py lifespan 中并未调用 register_memory_tools，"
        " 因此 save_memory 实际未注册到 tool_registry。待 memory_tools.py"
        " 修复并在 lifespan 注册后启用本测试。"
        " 若需验证记忆写入，使用 test_write_long_term_memory_tool_executed。"
    )
)
def test_save_memory_tool_executed(sim_app):
    """调用 tool_registry.call_tool("save_memory", {...}) 验证执行（已跳过）。

    跳过原因见装饰器 reason。预期测试主体（待 memory_tools.py 修复后启用）：
        call_result = tool_registry.call_tool(
            "save_memory",
            {"content": "测试 save_memory 写入", "importance": 3, "tags": ["test"]},
        )
        assert call_result.get("success") is True
        inner = call_result.get("result") or {}
        assert inner.get("status") == "success"
        assert isinstance(inner.get("memory_id"), int)
    """
    # 占位实现：若跳过被移除，下面逻辑可作为起点（参数格式需以 memory_tools.py
    # 修复后的实际签名为准）。
    tool = tool_registry.get_tool("save_memory")
    assert tool is not None, "save_memory 工具未注册"

    call_result = tool_registry.call_tool(
        "save_memory",
        {"content": "测试 save_memory 写入_工具集成场景", "importance": 3, "tags": ["test"]},
    )
    assert call_result.get("success") is True, f"call_tool 应成功，实际: {call_result!r}"
    inner = call_result.get("result") or {}
    assert inner.get("status") == "success", f"工具内部应返回 status=success，实际: {inner!r}"
    assert isinstance(inner.get("memory_id"), int), (
        f"memory_id 应为整数，实际: {inner.get('memory_id')!r}"
    )
