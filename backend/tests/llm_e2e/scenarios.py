"""Built-in test scenarios for the CXHMS LLM-based E2E testing framework."""

from __future__ import annotations

import asyncio
import random
import time

from .client import CXHMSClient, StreamResponse
from .judge import JudgeAgent, JudgeResult
from .metrics import MetricsCollector
from .config import TestConfig
from .runner import ScenarioResult, StepResult


async def scenario_basic_chat(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """基础聊天 - 发送简单问题，验证回复质量。"""
    steps: list[StepResult] = []
    message = "你好，请介绍一下你自己"

    try:
        resp = await client.chat_with_fallback(message)

        # 记录性能指标
        if resp.ttft_ms > 0:
            metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
        if resp.tps > 0:
            metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
        metrics.record_response_time("chat_stream", resp.total_time_ms, threshold_ms=config.performance_threshold_ms)

        # 验证回复非空
        content_ok = bool(resp.content and resp.content.strip())
        content_preview = (resp.content[:200] + "...") if resp.content and len(resp.content) > 200 else (resp.content or "")
        step_check = StepResult(
            name="回复非空检查",
            passed=content_ok,
            score=5.0 if content_ok else 1.0,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"content_length": len(resp.content), "content_preview": content_preview, "session_id": resp.session_id},
            error=None if content_ok else "回复内容为空",
        )
        steps.append(step_check)

        # 评判回复质量
        judge_result = await judge.judge_response(message, resp.content)
        step_judge = StepResult(
            name="回复质量评判",
            passed=judge_result.passed,
            score=judge_result.score,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"reason": judge_result.reason},
            error=None if judge_result.passed else judge_result.reason,
        )
        steps.append(step_judge)

    except Exception as exc:
        steps.append(StepResult(
            name="基础聊天异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_basic_chat",
        description="基础聊天 - 发送简单问题，验证回复质量",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


async def scenario_multi_turn(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """多轮对话 - 测试上下文记忆和连贯性。"""
    steps: list[StepResult] = []
    messages = [
        "我叫小明，今年25岁",
        "我喜欢编程和音乐",
        "你还记得我叫什么名字吗？",
        "我的爱好是什么？",
        "总结一下我们刚才聊的内容",
    ]
    conversation: list[dict[str, str]] = []

    for i, msg in enumerate(messages):
        try:
            resp = await client.chat_with_fallback(msg)
            conversation.append({"role": "user", "content": msg})
            conversation.append({"role": "assistant", "content": resp.content})

            if resp.ttft_ms > 0:
                metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
            if resp.tps > 0:
                metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
            metrics.record_response_time(
                f"chat_stream.turn_{i+1}", resp.total_time_ms, threshold_ms=config.performance_threshold_ms
            )

            # 评判回复质量
            judge_result = await judge.judge_response(msg, resp.content)
            step = StepResult(
                name=f"第{i+1}轮回复评判",
                passed=judge_result.passed,
                score=judge_result.score,
                response_time_ms=resp.total_time_ms,
                ttft_ms=resp.ttft_ms,
                tps=resp.tps,
                details={"message": msg, "reason": judge_result.reason},
                error=None if judge_result.passed else judge_result.reason,
            )
            steps.append(step)

            # 第3-5轮额外评判上下文连贯性
            if i >= 2:
                coherence_result = await judge.judge_context_coherence(conversation, resp.content)
                step_coherence = StepResult(
                    name=f"第{i+1}轮上下文连贯性",
                    passed=coherence_result.passed,
                    score=coherence_result.score,
                    response_time_ms=resp.total_time_ms,
                    ttft_ms=resp.ttft_ms,
                    tps=resp.tps,
                    details={"reason": coherence_result.reason},
                    error=None if coherence_result.passed else coherence_result.reason,
                )
                steps.append(step_coherence)

        except Exception as exc:
            steps.append(StepResult(
                name=f"第{i+1}轮对话异常",
                passed=False,
                score=0.0,
                error=str(exc),
            ))

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_multi_turn",
        description="多轮对话 - 测试上下文记忆和连贯性",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


async def scenario_memory_write_and_search(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """记忆写入与检索 - 测试记忆存储和搜索功能。"""
    steps: list[StepResult] = []
    memory_message = "请记住这个信息：我的猫叫小橘，今年3岁，是一只橘猫"

    # 1. 发送应触发记忆写入的消息
    try:
        resp = await client.chat_with_fallback(memory_message)
        if resp.ttft_ms > 0:
            metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
        if resp.tps > 0:
            metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
        metrics.record_response_time("chat_stream", resp.total_time_ms, threshold_ms=config.performance_threshold_ms)

        # 2. 评判原始回复质量
        judge_result = await judge.judge_response(memory_message, resp.content)
        step_response = StepResult(
            name="记忆写入回复评判",
            passed=judge_result.passed,
            score=judge_result.score,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"reason": judge_result.reason},
            error=None if judge_result.passed else judge_result.reason,
        )
        steps.append(step_response)

    except Exception as exc:
        steps.append(StepResult(
            name="记忆写入消息异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    # 3. 等待记忆写入完成
    await asyncio.sleep(2)

    # 4. 搜索记忆
    try:
        search_start = time.monotonic()
        search_results = await client.search_memories(query="小橘")
        search_time_ms = (time.monotonic() - search_start) * 1000
        metrics.record_response_time("memories_search", search_time_ms, threshold_ms=config.performance_threshold_ms)

        # 5. 评判搜索结果
        judge_search = await judge.judge_memory_search("小橘", search_results.get("results", search_results.get("memories", [])))
        step_search = StepResult(
            name="记忆搜索结果评判",
            passed=judge_search.passed,
            score=judge_search.score,
            response_time_ms=search_time_ms,
            details={"reason": judge_search.reason},
            error=None if judge_search.passed else judge_search.reason,
        )
        steps.append(step_search)

    except Exception as exc:
        steps.append(StepResult(
            name="记忆搜索异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_memory_write_and_search",
        description="记忆写入与检索 - 测试记忆存储和搜索功能",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


async def scenario_tool_calling(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """工具调用 - 测试计算器和时间工具调用。"""
    steps: list[StepResult] = []

    # 测试计算器工具
    calc_message = "帮我计算 123 * 456"
    try:
        resp = await client.chat_with_fallback(calc_message)
        if resp.ttft_ms > 0:
            metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
        if resp.tps > 0:
            metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
        metrics.record_response_time("chat_stream.calc", resp.total_time_ms, threshold_ms=config.performance_threshold_ms)

        # 验证工具调用非空
        has_tool_calls = bool(resp.tool_calls)
        step_tool_check = StepResult(
            name="计算器工具调用检查",
            passed=has_tool_calls,
            score=5.0 if has_tool_calls else 1.0,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"tool_calls_count": len(resp.tool_calls)},
            error=None if has_tool_calls else "未检测到工具调用",
        )
        steps.append(step_tool_check)

        # 验证工具结果包含正确答案
        correct_answer = 56088
        found_correct = False
        for tr in resp.tool_results:
            result_str = str(tr.get("result", ""))
            if str(correct_answer) in result_str:
                found_correct = True
                break
        step_result_check = StepResult(
            name="计算器结果正确性检查",
            passed=found_correct,
            score=5.0 if found_correct else 1.0,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"expected": correct_answer, "tool_results": resp.tool_results},
            error=None if found_correct else f"工具结果中未找到正确答案 {correct_answer}",
        )
        steps.append(step_result_check)

        # 评判工具调用正确性
        judge_result = await judge.judge_tool_call(
            calc_message, resp.tool_calls, resp.tool_results, resp.content
        )
        step_judge = StepResult(
            name="计算器工具调用评判",
            passed=judge_result.passed,
            score=judge_result.score,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"reason": judge_result.reason},
            error=None if judge_result.passed else judge_result.reason,
        )
        steps.append(step_judge)

    except Exception as exc:
        steps.append(StepResult(
            name="计算器工具调用异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    # 测试时间工具
    time_message = "现在几点了？"
    try:
        resp = await client.chat_with_fallback(time_message)
        if resp.ttft_ms > 0:
            metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
        if resp.tps > 0:
            metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
        metrics.record_response_time("chat_stream.datetime", resp.total_time_ms, threshold_ms=config.performance_threshold_ms)

        judge_result = await judge.judge_tool_call(
            time_message, resp.tool_calls, resp.tool_results, resp.content
        )
        step_time = StepResult(
            name="时间工具调用评判",
            passed=judge_result.passed,
            score=judge_result.score,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"reason": judge_result.reason},
            error=None if judge_result.passed else judge_result.reason,
        )
        steps.append(step_time)

    except Exception as exc:
        steps.append(StepResult(
            name="时间工具调用异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_tool_calling",
        description="工具调用 - 测试计算器和时间工具调用",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


async def scenario_memory_agent(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """记忆管理对话 - 测试记忆管理代理。"""
    steps: list[StepResult] = []

    # 1. 查看记忆统计
    try:
        resp = await client.memory_agent_chat_with_fallback("查看我的记忆统计")
        if resp.ttft_ms > 0:
            metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
        if resp.tps > 0:
            metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
        metrics.record_response_time("memory_agent_chat", resp.total_time_ms, threshold_ms=config.performance_threshold_ms)

        content_ok = bool(resp.content and resp.content.strip())
        step_check = StepResult(
            name="记忆统计回复非空检查",
            passed=content_ok,
            score=5.0 if content_ok else 1.0,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"content_length": len(resp.content)},
            error=None if content_ok else "记忆统计回复为空",
        )
        steps.append(step_check)

        judge_result = await judge.judge_response("查看我的记忆统计", resp.content)
        step_judge = StepResult(
            name="记忆统计回复评判",
            passed=judge_result.passed,
            score=judge_result.score,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"reason": judge_result.reason},
            error=None if judge_result.passed else judge_result.reason,
        )
        steps.append(step_judge)

    except Exception as exc:
        steps.append(StepResult(
            name="记忆统计对话异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    # 2. 搜索关于猫的记忆
    try:
        resp = await client.memory_agent_chat_with_fallback("搜索关于猫的记忆")
        if resp.ttft_ms > 0:
            metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
        if resp.tps > 0:
            metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
        metrics.record_response_time("memory_agent_chat.search", resp.total_time_ms, threshold_ms=config.performance_threshold_ms)

        judge_result = await judge.judge_response("搜索关于猫的记忆", resp.content)
        step_search = StepResult(
            name="记忆搜索回复评判",
            passed=judge_result.passed,
            score=judge_result.score,
            response_time_ms=resp.total_time_ms,
            ttft_ms=resp.ttft_ms,
            tps=resp.tps,
            details={"reason": judge_result.reason},
            error=None if judge_result.passed else judge_result.reason,
        )
        steps.append(step_search)

    except Exception as exc:
        steps.append(StepResult(
            name="记忆搜索对话异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_memory_agent",
        description="记忆管理对话 - 测试记忆管理代理",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


async def scenario_concurrent_chat(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """并发聊天 - 测试并发请求处理能力。"""
    steps: list[StepResult] = []
    questions = ["你好", "1+1等于几？", "今天天气怎么样？", "讲个笑话", "什么是AI？"]
    concurrent_count = config.concurrent_users

    async def _send_chat(idx: int) -> tuple[bool, float, str, str]:
        """发送单个聊天请求，返回 (成功, 延迟ms, 问题, 回复内容)。"""
        question = questions[idx % len(questions)]
        start = time.monotonic()
        try:
            resp = await client.chat_with_fallback(question)
            elapsed = (time.monotonic() - start) * 1000
            return True, elapsed, question, resp.content
        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            return False, elapsed, question, ""

    # 并发发送请求
    try:
        results = await asyncio.gather(
            *[_send_chat(i) for i in range(concurrent_count)]
        )

        success_count = sum(1 for r in results if r[0])
        latencies = [r[1] for r in results]
        avg_time = sum(latencies) / len(latencies) if latencies else 0.0

        metrics.record_concurrent(
            total=concurrent_count,
            success=success_count,
            avg_time_ms=avg_time,
            latencies_ms=latencies,
        )

        step_concurrent = StepResult(
            name="并发请求成功率",
            passed=success_count == concurrent_count,
            score=5.0 * (success_count / concurrent_count),
            response_time_ms=avg_time,
            details={
                "total": concurrent_count,
                "success": success_count,
                "avg_time_ms": avg_time,
            },
            error=None if success_count == concurrent_count else f"部分请求失败: {concurrent_count - success_count}/{concurrent_count}",
        )
        steps.append(step_concurrent)

        # 评判部分成功回复的质量
        successful_results = [r for r in results if r[0]]
        sample_size = min(2, len(successful_results))
        for i in range(sample_size):
            r = successful_results[i]
            try:
                judge_result = await judge.judge_response(r[2], r[3])
                step_judge = StepResult(
                    name=f"并发回复评判-{i+1}",
                    passed=judge_result.passed,
                    score=judge_result.score,
                    details={"question": r[2], "reason": judge_result.reason},
                    error=None if judge_result.passed else judge_result.reason,
                )
                steps.append(step_judge)
            except Exception as exc:
                steps.append(StepResult(
                    name=f"并发回复评判-{i+1}异常",
                    passed=False,
                    score=0.0,
                    error=str(exc),
                ))

    except Exception as exc:
        steps.append(StepResult(
            name="并发聊天异常",
            passed=False,
            score=0.0,
            error=str(exc),
        ))

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_concurrent_chat",
        description="并发聊天 - 测试并发请求处理能力",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


async def scenario_api_performance(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """API 性能基线 - 测试各 GET 端点的响应时间。"""
    steps: list[StepResult] = []
    endpoints = [
        ("health", client.check_health),
        ("agents", client.get_agents),
        ("memories", lambda: client.list_memories(limit=10)),
        ("tools", client.list_tools),
        ("stats", client.get_stats),
    ]

    # 获取 context/sessions 需要通过 chat_history 或直接请求
    # 使用 search_memories 作为替代，因为 client 没有 get_sessions 方法
    # 但根据需求，我们尝试直接请求 /api/context/sessions
    async def _get_sessions() -> dict:
        resp = await client._client.get("/api/context/sessions")
        resp.raise_for_status()
        return resp.json()

    endpoints.append(("context_sessions", _get_sessions))

    for endpoint_name, endpoint_fn in endpoints:
        times_ms: list[float] = []
        last_error: str | None = None
        success_count = 0

        for attempt in range(5):
            try:
                start = time.monotonic()
                await endpoint_fn()
                elapsed = (time.monotonic() - start) * 1000
                times_ms.append(elapsed)
                success_count += 1
            except Exception as exc:
                last_error = str(exc)

        if times_ms:
            avg_time = sum(times_ms) / len(times_ms)
            metrics.record_response_time(endpoint_name, avg_time, threshold_ms=config.performance_threshold_ms)

            step = StepResult(
                name=f"GET /api/{endpoint_name} 性能",
                passed=avg_time <= config.performance_threshold_ms,
                score=5.0 if avg_time <= config.performance_threshold_ms else max(1.0, 5.0 - (avg_time - config.performance_threshold_ms) / config.performance_threshold_ms * 2),
                response_time_ms=avg_time,
                details={
                    "avg_ms": avg_time,
                    "min_ms": min(times_ms),
                    "max_ms": max(times_ms),
                    "success_count": success_count,
                    "total_attempts": 5,
                },
                error=last_error,
            )
        else:
            step = StepResult(
                name=f"GET /api/{endpoint_name} 性能",
                passed=False,
                score=0.0,
                details={"success_count": 0, "total_attempts": 5},
                error=last_error or "所有尝试均失败",
            )
        steps.append(step)

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_api_performance",
        description="API 性能基线 - 测试各 GET 端点的响应时间",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


async def scenario_long_conversation(
    client: CXHMSClient,
    judge: JudgeAgent,
    metrics: MetricsCollector,
    config: TestConfig,
) -> ScenarioResult:
    """超长对话稳定性 - 测试长时间对话的性能和上下文保持。"""
    steps: list[StepResult] = []
    total_rounds = config.long_conversation_rounds
    conversation: list[dict[str, str]] = []
    memory_data: dict[int, str] = {}  # 记录写入的测试数据

    for i in range(total_rounds):
        round_type = i % 4
        message = ""
        try:
            if round_type == 0:
                # 简单问答
                message = f"第{i+1}轮对话：告诉我一个有趣的事实"
            elif round_type == 1:
                # 记忆操作
                random_value = f"val_{random.randint(1000, 9999)}"
                memory_data[i] = random_value
                message = f"请记住：测试数据{i}的值是{random_value}"
            elif round_type == 2:
                # 工具调用
                a = random.randint(10, 99)
                b = random.randint(10, 99)
                message = f"帮我计算 {a} + {b}"
            elif round_type == 3:
                # 上下文引用
                ref_key = i - 5
                if ref_key in memory_data:
                    message = f"我刚才让你记住的测试数据{ref_key}的值是多少？"
                else:
                    message = f"第{i+1}轮对话：总结一下我们聊过的内容"

            resp = await client.chat_with_fallback(message)
            conversation.append({"role": "user", "content": message})
            conversation.append({"role": "assistant", "content": resp.content})

            if resp.ttft_ms > 0:
                metrics.record_ttft(resp.ttft_ms, threshold_ms=config.ttft_threshold_ms)
            if resp.tps > 0:
                metrics.record_tps(resp.tps, min_threshold=config.tps_min_threshold)
            metrics.record_response_time(
                f"chat_stream.long_round_{i+1}", resp.total_time_ms, threshold_ms=config.performance_threshold_ms
            )

        except Exception as exc:
            steps.append(StepResult(
                name=f"长对话第{i+1}轮异常",
                passed=False,
                score=0.0,
                error=str(exc),
            ))

        # 每10轮打印进度并检查退化
        if (i + 1) % 10 == 0:
            print(f"  长对话进度: {i+1}/{total_rounds}")
            degraded = metrics.check_degradation("response_time", window=10, threshold_pct=0.5)
            if degraded:
                steps.append(StepResult(
                    name=f"第{i+1}轮性能退化检测",
                    passed=False,
                    score=2.0,
                    details={"degradation_detected": True},
                    error="检测到响应时间退化趋势",
                ))

    # 对最后几条消息评判上下文连贯性
    last_messages = conversation[-6:] if len(conversation) >= 6 else conversation
    if last_messages:
        try:
            last_assistant_msg = ""
            for msg in reversed(conversation):
                if msg["role"] == "assistant":
                    last_assistant_msg = msg["content"]
                    break
            coherence_result = await judge.judge_context_coherence(last_messages, last_assistant_msg)
            steps.append(StepResult(
                name="长对话上下文连贯性评判",
                passed=coherence_result.passed,
                score=coherence_result.score,
                details={"reason": coherence_result.reason},
                error=None if coherence_result.passed else coherence_result.reason,
            ))
        except Exception as exc:
            steps.append(StepResult(
                name="长对话上下文连贯性评判异常",
                passed=False,
                score=0.0,
                error=str(exc),
            ))

    all_passed = all(s.passed for s in steps)
    avg_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return ScenarioResult(
        name="scenario_long_conversation",
        description="超长对话稳定性 - 测试长时间对话的性能和上下文保持",
        passed=all_passed and avg_score >= config.judge_score_pass,
        score=avg_score,
        metrics=metrics.get_summary(),
        steps=steps,
        error=None,
    )


ALL_SCENARIOS = [
    scenario_basic_chat,
    scenario_multi_turn,
    scenario_memory_write_and_search,
    scenario_tool_calling,
    scenario_memory_agent,
    scenario_concurrent_chat,
    scenario_api_performance,
    scenario_long_conversation,
]
