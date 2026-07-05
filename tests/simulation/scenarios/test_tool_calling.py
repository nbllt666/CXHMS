"""SubTask 8.4 - 工具调用场景。

覆盖死区：计算/时间/随机数/JSON 格式化工具的关键词触发、tool_call 事件结构、
工具结果在 SSE 流中的整合，以及 FakeLLMClient 工具调用循环的终止行为。

断言升级（Task 3 of spec `fix-simulation-tool-call-completeness`）：
早期版本仅断言"工具被触发"（tool_calls 中存在对应 name）。本次升级将断言
扩展为"触发 + 执行成功 + 结果整合"三段式：
    1. 触发：tool_calls 中包含预期工具名（datetime/random/json_format/calculator）。
    2. 执行成功：tool_results 中对应工具的 result.success == True，且关键字段存在
       （calculator.result / datetime.formatted / random.value / json_format.formatted）。
    3. 结果整合：FakeLLMClient 在检测到 messages 末尾 role=tool 消息后，基于工具
       结果生成最终 content，使工具调用循环在 1-2 轮内终止（不再触发新 tool_calls）。
       本测试断言最终 content 含工具结果关键字段，且 tool_calls 数量 <= 2。

FakeLLMClient 行为对齐（Task 2 已完成）：
- 时间工具触发名从 "get_current_time" 改为 "datetime"（对齐 BUILTIN_TOOL_NAMES）。
- 新增 "random"（关键词"随机数"/"random"）与 "json_format"（关键词"格式化 json"/
  "json 格式化"/"format json"）触发。
- 工具调用循环终止：检测 messages 末尾 role=tool 消息后基于工具结果生成最终 content。
"""

import json

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


def _first_tool_call(result):
    """取首个非 None 的 tool_call dict。"""
    for tc in result.get("tool_calls", []):
        if tc:
            return tc
    return None


def _tool_names(result):
    """收集所有 tool_calls 中的工具名（忽略 None / 空项）。"""
    names = []
    for tc in result.get("tool_calls", []):
        if not tc:
            continue
        name = tc.get("function", {}).get("name")
        if name:
            names.append(name)
    return names


def _results_for(result, tool_name):
    """从 tool_results 中筛选出指定工具的结果列表。"""
    return [
        tr for tr in result.get("tool_results", [])
        if tr.get("tool_name") == tool_name
    ]


def test_calculate_tool_triggered(sim_actor):
    """发送"计算 123+456"，应触发 calculator 工具调用，参数含 expression="123+456"。"""
    result = sim_actor.send_streaming_message("计算 123+456")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"
    assert result["tool_calls"], "tool_calls 列表不应为空"

    tc = _first_tool_call(result)
    assert tc is not None, "应至少有一个非空 tool_call"
    func = tc.get("function", {})
    name = func.get("name", "")
    assert name in ("calculate", "calculator"), (
        f"工具名应为 calculate/calculator，实际: {name!r}"
    )

    args_raw = func.get("arguments", "{}")
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
    except json.JSONDecodeError:
        args = {}
    assert args.get("expression") == "123+456", (
        f"arguments.expression 应为 '123+456'，实际: {args!r}"
    )


def test_datetime_tool_triggered(sim_actor):
    """发送"现在几点了"，应触发 datetime 工具调用（对齐 BUILTIN_TOOL_NAMES）。

    断言升级：除触发外，还断言 tool_results 中 datetime 工具执行 success == True。
    """
    result = sim_actor.send_streaming_message("现在几点了")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"
    assert result["tool_calls"], "tool_calls 列表不应为空"

    tc = _first_tool_call(result)
    assert tc is not None, "应至少有一个非空 tool_call"
    func = tc.get("function", {})
    assert func.get("name") == "datetime", (
        f"工具名应为 datetime，实际: {func.get('name')!r}"
    )

    # 断言执行成功：datetime 在 BUILTIN_TOOL_NAMES 中，tool_registry.call_tool 应成功
    datetime_results = _results_for(result, "datetime")
    assert datetime_results, "应至少有一个 datetime 工具结果"
    tool_result = datetime_results[0].get("result") or {}
    assert tool_result.get("success") is True, (
        f"datetime 执行应成功，实际: {tool_result!r}"
    )


def test_tool_result_integrated(sim_actor):
    """计算工具执行后，tool_results 中应包含 calculator 的成功结果（result=579）。

    断言升级：
        - 保留 calculator 执行成功、result == 579 断言。
        - 新增：最终 content 含 "579"（FakeLLMClient 基于工具结果生成
          "123+456 的结果是 579"）。
        - 新增：tool_calls 数量 <= 2（循环应在 1-2 轮内终止，不跑满
          max_tool_rounds=50）。
    """
    result = sim_actor.send_streaming_message("计算 123+456")
    assert result["tool_results"], "tool_results 列表不应为空"

    calc_results = [
        tr for tr in result["tool_results"]
        if tr.get("tool_name") in ("calculate", "calculator")
    ]
    assert calc_results, "应至少有一个 calculator 工具结果"

    first = calc_results[0]
    tool_result = first.get("result") or {}
    assert tool_result.get("success") is True, (
        f"calculator 执行应成功，实际: {tool_result!r}"
    )
    assert tool_result.get("result") == 579, (
        f"123+456 应等于 579，实际: {tool_result.get('result')!r}"
    )

    # 最终 content 应整合工具结果（FakeLLMClient 检测到 role=tool 消息后生成）
    assert "579" in result["content"], (
        f"最终 content 应含 '579'，实际: {result['content']!r}"
    )

    # 工具调用循环应在 1-2 轮内终止
    assert len(result["tool_calls"]) <= 2, (
        f"tool_calls 数量应 <= 2（循环应快速终止），实际: "
        f"{len(result['tool_calls'])} -> {result['tool_calls']!r}"
    )


def test_no_tool_for_plain_message(sim_actor):
    """发送"你好"（无工具关键词），tool_calls 应为空列表。"""
    result = sim_actor.send_streaming_message("你好")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"
    assert result["tool_calls"] == [], (
        f"普通消息不应触发工具调用，实际: {result['tool_calls']!r}"
    )


def test_datetime_tool_executed(sim_actor):
    """发送"现在几点了"，datetime 工具应被触发并执行成功，结果含 "formatted" 字段。"""
    result = sim_actor.send_streaming_message("现在几点了")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"

    names = _tool_names(result)
    assert "datetime" in names, (
        f"tool_calls 应包含 datetime，实际: {names!r}"
    )

    datetime_results = _results_for(result, "datetime")
    assert datetime_results, "应至少有一个 datetime 工具结果"
    tool_result = datetime_results[0].get("result") or {}
    assert tool_result.get("success") is True, (
        f"datetime 执行应成功，实际: {tool_result!r}"
    )
    # datetime_tool 返回 "formatted" 字段（亦含 timestamp/iso/year 等时间字段）
    assert "formatted" in tool_result, (
        f"datetime 结果应含 'formatted' 字段，实际: {tool_result!r}"
    )


def test_random_tool_triggered(sim_actor):
    """发送"生成一个随机数"，random 工具应被触发并执行成功，结果含 "value" 字段。"""
    result = sim_actor.send_streaming_message("生成一个随机数")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"

    names = _tool_names(result)
    assert "random" in names, (
        f"tool_calls 应包含 random，实际: {names!r}"
    )

    random_results = _results_for(result, "random")
    assert random_results, "应至少有一个 random 工具结果"
    tool_result = random_results[0].get("result") or {}
    assert tool_result.get("success") is True, (
        f"random 执行应成功，实际: {tool_result!r}"
    )
    assert "value" in tool_result, (
        f"random 结果应含 'value' 字段，实际: {tool_result!r}"
    )


def test_json_format_tool_triggered(sim_actor):
    """发送"格式化 json"，json_format 工具应被触发并执行成功，结果含 "formatted" 字段。"""
    result = sim_actor.send_streaming_message("格式化 json")
    assert result["error"] is None, f"流式不应有错误: {result['error']!r}"

    names = _tool_names(result)
    assert "json_format" in names, (
        f"tool_calls 应包含 json_format，实际: {names!r}"
    )

    json_results = _results_for(result, "json_format")
    assert json_results, "应至少有一个 json_format 工具结果"
    tool_result = json_results[0].get("result") or {}
    assert tool_result.get("success") is True, (
        f"json_format 执行应成功，实际: {tool_result!r}"
    )
    assert "formatted" in tool_result, (
        f"json_format 结果应含 'formatted' 字段，实际: {tool_result!r}"
    )
