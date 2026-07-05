"""C4 流式取消回归测试。

覆盖修复点 C4：客户端断开/取消时，后端 ``chat_stream`` 路由的 ``generate_stream``
inner function 必须在 finally 块中主动 ``await stream_gen.aclose()``，把取消信号
传播到上游 vLLM 流（避免泄露未关闭的生成器与残余 token 计费）。

回归策略：
    用 ``TrackingGen`` 包装 ``generate_chat_stream`` 返回的 async generator，
    monkeypatch 到 ``backend.api.routers.chat.generate_chat_stream``，再以
    ``async_client.stream`` 发起流式请求。读到首个 SSE 事件后关闭流模拟客户端
    断开，最后断言 ``TrackingGen.aclose_called`` 为 True。

    同时提供正常完成路径的回归——即使流正常结束，finally 块也应调用 aclose
    （验证 C4 的 finally 路径始终存在，而非仅在异常路径）。
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# TrackingGen：包装 async generator，记录 aclose() 调用
# --------------------------------------------------------------------------- #


class TrackingGen:
    """包装 async generator，记录 ``aclose`` 是否被调用。

    C4 回归核心：``chat_stream`` 路由在 finally 块中调用
    ``await stream_gen.aclose()``，本类捕获该调用以供断言。
    """

    def __init__(self, inner: AsyncGenerator[Dict[str, Any], None], flag: Dict[str, bool]):
        self._inner = inner
        self._flag = flag

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._inner.__anext__()

    async def aclose(self):
        self._flag["value"] = True
        try:
            await self._inner.aclose()
        except Exception:
            # 关闭底层失败不应影响测试断言（已记录调用事实）
            pass


# --------------------------------------------------------------------------- #
# 工厂：用 TrackingGen 包装 generate_chat_stream
# --------------------------------------------------------------------------- #


def _make_tracking_wrapper(original_fn, flag: Dict[str, bool]):
    """返回一个与 ``generate_chat_stream`` 同签名的 wrapper，包装返回值为 TrackingGen。

    注意：``generate_chat_stream`` 是 async generator function（用 ``yield``），
    调用它直接返回 ``AsyncGenerator`` 对象（无需 await）。故 wrapper 必须是
    普通函数，返回 TrackingGen 实例——若用 ``async def ... return`` 则变成
    coroutine，后端 ``async for event in stream_gen`` 会因缺 ``__aiter__`` 失败。
    """

    def _wrapped(*args, **kwargs) -> "TrackingGen":
        inner = original_fn(*args, **kwargs)
        return TrackingGen(inner, flag)

    return _wrapped


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_cancel_calls_aclose_on_client_disconnect(
    async_client, monkeypatch
):
    """C4 回归：客户端断开流式连接后，后端必须 aclose 上游聊天流生成器。

    步骤：
        1. monkeypatch ``backend.api.routers.chat.generate_chat_stream`` 为
           TrackingGen 包装版本。
        2. ``async_client.stream`` 发起 POST /api/chat/stream。
        3. 读到首个 SSE 事件（session 事件）后立即关闭流，模拟客户端断开。
        4. 等待 finally 块执行，断言 ``aclose_called`` 为 True。
    """
    import backend.api.routers.chat as chat_mod

    flag = {"value": False}
    original_fn = chat_mod.generate_chat_stream
    monkeypatch.setattr(
        chat_mod,
        "generate_chat_stream",
        _make_tracking_wrapper(original_fn, flag),
    )

    # 发起流式请求，读到首个事件后关闭，模拟客户端中途断开
    async with async_client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "测试取消", "agent_id": "default"},
    ) as response:
        # 等到第一个 SSE event 到达，证明 generate_stream 已进入循环
        async for raw_line in response.aiter_lines():
            if raw_line and raw_line.startswith("data: "):
                # 首个 SSE 事件通常是 {"type":"session",...}
                _ = json.loads(raw_line[len("data: "):])
                break
        # 退出 with 块 → httpx 关闭底层流 → 后端 generate_stream 收到取消
        # 触发 finally 块 → await stream_gen.aclose()

    # 给后端 finally 块一点时间执行（TestClient 的 ASGITransport 同步传播，
    # 但 aclose 内部可能有 await 链，留 200ms 余量）
    await asyncio.sleep(0.2)

    assert flag["value"] is True, (
        "C4 回归失败：客户端断开后后端未调用 stream_gen.aclose()。"
        " 检查 chat_stream 路由 generate_stream 的 finally 块是否调用 aclose。"
    )


@pytest.mark.asyncio
async def test_stream_normal_completion_also_calls_aclose(async_client, monkeypatch):
    """C4 回归补充：即使流正常结束，finally 块也应调用 aclose。

    验证 aclose 调用不依赖异常路径，而是 finally 块的常规清理动作。
    """
    import backend.api.routers.chat as chat_mod

    flag = {"value": False}
    original_fn = chat_mod.generate_chat_stream
    monkeypatch.setattr(
        chat_mod,
        "generate_chat_stream",
        _make_tracking_wrapper(original_fn, flag),
    )

    # 完整消费整个流（不提前断开）
    async with async_client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "你好", "agent_id": "default"},
    ) as response:
        event_count = 0
        async for raw_line in response.aiter_lines():
            if raw_line and raw_line.startswith("data: "):
                event_count += 1
        # 至少应有 session + thinking + content 事件
        assert event_count > 0, "流式响应应至少产生一个 SSE 事件"

    await asyncio.sleep(0.2)

    assert flag["value"] is True, (
        "C4 回归失败：流正常结束后后端未调用 stream_gen.aclose()。"
        " finally 块应在所有路径都执行 aclose，而非仅异常路径。"
    )
