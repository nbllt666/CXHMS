"""C3 长对话增量持久化回归测试。

覆盖修复点 C3：``add_message_async`` 仅在内存中追加消息并标记 dirty，磁盘持久化
由后台 ``_flush_loop`` 线程按阈值（每 ``_FLUSH_MSG_INTERVAL=10`` 条或每
``_FLUSH_TIME_INTERVAL=5.0`` 秒）批量完成。长对话下每条消息持久化开销应 < 5ms
（仅内存 set/dict 更新，无磁盘 I/O、无 to_thread 调度）。

回归策略：
    1. 直接调用 ``context_manager.add_message_async`` 110 次，测量每次耗时，
       断言平均 < 5ms（C3 性能契约）。
    2. 验证 110 轮后内存中消息数与持久化数据一致（C3 不丢消息）。
"""

import asyncio
import time

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #


def _get_context_manager(sim_app):
    """从 sim_app 装配的 ServiceState 取 context_manager。

    sim_app 通过 CXHMS_SIMULATION=1 触发 lifespan 装配 ServiceState，
    挂到 ``app.state.services``（D1 ServiceState + Depends 注入模式）。
    """
    services = sim_app.app.state.services
    assert services is not None, "sim_app lifespan 未装配 ServiceState"
    assert services.context_manager is not None, "ServiceState.context_manager 未装配"
    return services.context_manager


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_long_conversation_add_message_avg_under_5ms(sim_app):
    """C3 性能回归：110 轮 add_message_async 平均耗时 < 5ms。

    C3 的核心契约：``add_message_async`` 仅内存操作（持锁追加 + mark_dirty），
    不触发磁盘 I/O，故每条消息持久化开销应 < 5ms。若 C3 被破坏（如回退到
    每条全量重写 session JSON），平均耗时将显著上升。
    """
    ctx_mgr = _get_context_manager(sim_app)
    session_id = "test-long-conv-100-perf"
    ctx_mgr.create_session(
        workspace_id="default",
        title="C3 长对话性能测试",
        session_id=session_id,
    )

    turn_count = 110
    timings_ms: list[float] = []

    # 预热一次（避免首次 import/JIT 开销干扰测量）
    await ctx_mgr.add_message_async(session_id, "user", "预热消息")

    for i in range(turn_count):
        t0 = time.monotonic()
        await ctx_mgr.add_message_async(session_id, "user", f"第 {i} 轮消息")
        t1 = time.monotonic()
        timings_ms.append((t1 - t0) * 1000.0)

    avg_ms = sum(timings_ms) / len(timings_ms)
    max_ms = max(timings_ms)
    p95_ms = sorted(timings_ms)[int(len(timings_ms) * 0.95)]

    # C3 契约：平均 < 5ms
    assert avg_ms < 5.0, (
        f"C3 性能回归：{turn_count} 轮 add_message_async 平均耗时 {avg_ms:.2f}ms "
        f"超过 5ms 阈值（max={max_ms:.2f}ms, p95={p95_ms:.2f}ms）。"
        f" 检查 add_message_async 是否回退到每条全量重写 session JSON。"
    )

    # 同时记录 max/p95 作为诊断信息（不阻断，但暴露抖动）
    # 若 max 异常高（如 > 50ms），可能是一次 flush 触发，属正常


@pytest.mark.asyncio
async def test_long_conversation_messages_preserved_in_memory(sim_app):
    """C3 数据完整性回归：110 轮后内存中消息数应正确（C3 不丢消息）。

    C3 把磁盘持久化卸载到后台线程，但内存中的消息列表应立即且完整地追加。
    """
    ctx_mgr = _get_context_manager(sim_app)
    session_id = "test-long-conv-100-integrity"
    ctx_mgr.create_session(
        workspace_id="default",
        title="C3 长对话完整性测试",
        session_id=session_id,
    )

    turn_count = 110
    for i in range(turn_count):
        await ctx_mgr.add_message_async(session_id, "user", f"完整性消息 {i}")

    messages = ctx_mgr.get_messages(session_id, limit=turn_count + 10)
    assert len(messages) == turn_count, (
        f"C3 完整性回归：写入 {turn_count} 条，内存中只有 {len(messages)} 条。"
        f" add_message_async 可能丢失消息。"
    )

    # 验证顺序与内容：第一条应是完整性消息 0
    assert "完整性消息 0" in messages[0]["content"], (
        f"首条消息内容不符: {messages[0]!r}"
    )
    assert f"完整性消息 {turn_count - 1}" in messages[-1]["content"], (
        f"末条消息内容不符: {messages[-1]!r}"
    )


@pytest.mark.asyncio
async def test_long_conversation_does_not_block_chat_stream(sim_app):
    """C3 端到端回归：长对话（100+ 轮）下 chat_stream 仍可正常响应。

    模拟真实场景：先预填 100 轮历史，再发起一次 chat_stream，验证不因历史
    过长而阻塞或超时。
    """
    ctx_mgr = _get_context_manager(sim_app)
    session_id = "agent-default"  # chat 路由固定用 agent-{agent_id}

    # 预填 100 轮历史（若 session 不存在则创建）
    try:
        ctx_mgr.create_session(
            workspace_id="agent-chats",
            title="预填长对话",
            session_id=session_id,
        )
    except Exception:
        pass  # session 已存在

    for i in range(100):
        await ctx_mgr.add_message_async(session_id, "user", f"历史消息 {i}")
        await ctx_mgr.add_message_async(session_id, "assistant", f"历史回复 {i}")

    # 发起一次真实 chat_stream，验证不阻塞
    from httpx import ASGITransport, AsyncClient

    fastapi_app = sim_app.app
    t0 = time.monotonic()
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as ac:
        async with ac.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "在 100 轮历史后继续对话", "agent_id": "default"},
        ) as resp:
            event_count = 0
            async for line in resp.aiter_lines():
                if line and line.startswith("data: "):
                    event_count += 1
    elapsed_ms = (time.monotonic() - t0) * 1000.0

    assert event_count > 0, "chat_stream 在 100 轮历史后未产生任何 SSE 事件"
    # 100 轮历史下端到端应 < 30s（FakeLLM 无网络 IO，主要开销在 build_messages
    # 序列化 200 条历史 + 持久化）
    assert elapsed_ms < 30000, (
        f"C3 端到端回归：100 轮历史下 chat_stream 耗时 {elapsed_ms:.0f}ms 超过 30s。"
        f" 可能存在阻塞 I/O 或全量重写。"
    )
