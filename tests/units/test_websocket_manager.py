"""WebSocketManager 单元测试。

覆盖修复点：
    - B7: ``broadcast`` 迭代前 snapshot ``list(self.connections.items())``，
      防止迭代期间 ``disconnect`` 并发删键触发
      ``RuntimeError: dictionary changed size during iteration``

设计原则：
    - 不依赖真实 WebSocket 连接，用 ``unittest.mock.AsyncMock`` 构造 fake connection
    - 构造并发场景：``broadcast`` 在 ``await connection.send`` 让出控制权期间，
      并发调用 ``disconnect`` 删除字典键
    - 验证 ``broadcast`` 不抛 ``RuntimeError``，正常完成
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# 工具：构造 fake WebSocketConnection
# --------------------------------------------------------------------------- #


def _make_fake_connection(client_id: str, send_delay: float = 0.01):
    """构造一个 fake WebSocketConnection。

    ``send`` 为 AsyncMock，含 ``send_delay`` 延迟（让出事件循环控制权，
    使 disconnect 有机会并发执行）。``subscriptions`` 为空 set。
    """
    from backend.core.websocket.manager import WebSocketConnection

    websocket = AsyncMock()
    websocket.send_json = AsyncMock()

    connection = WebSocketConnection(websocket=websocket, client_id=client_id)
    # 注入延迟到 send：用 side_effect 包装
    original_send = connection.send

    async def delayed_send(data):
        if send_delay > 0:
            await asyncio.sleep(send_delay)
        await original_send(data)

    connection.send = delayed_send
    return connection


# --------------------------------------------------------------------------- #
# B7: broadcast snapshot 防止并发修改
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b7_broadcast_does_not_raise_on_concurrent_disconnect():
    """B7: broadcast 期间并发 disconnect 不触发 RuntimeError: dictionary changed size。

    回归断言：修复前 ``for client_id, connection in self.connections.items()``
    直接迭代字典，``await connection.send`` 让出控制权后 ``disconnect`` 并发删键，
    触发 ``RuntimeError: dictionary changed size during iteration``；
    修复前 ``list(self.connections.items())`` snapshot，迭代对象与字典删除解耦。
    """
    from backend.core.websocket.manager import WebSocketManager

    manager = WebSocketManager()
    # 注入 5 个 fake connection（send 含 0.02s 延迟，让出事件循环）
    client_ids = [f"client-{i}" for i in range(5)]
    for cid in client_ids:
        manager.connections[cid] = _make_fake_connection(cid, send_delay=0.02)

    # 并发：broadcast + 2 个 disconnect（在 broadcast 迭代期间删除字典键）
    async def do_broadcast():
        await manager.broadcast({"type": "test", "content": "B7 并发测试"})

    async def do_disconnect(cid):
        # 稍等 broadcast 开始迭代后再 disconnect
        await asyncio.sleep(0.005)
        await manager.disconnect(cid)

    # 不应抛 RuntimeError
    await asyncio.gather(
        do_broadcast(),
        do_disconnect(client_ids[0]),
        do_disconnect(client_ids[1]),
    )

    # broadcast 后被 disconnect 的键应已删除
    assert client_ids[0] not in manager.connections
    assert client_ids[1] not in manager.connections
    # 其余连接保留
    assert client_ids[2] in manager.connections
    assert client_ids[3] in manager.connections
    assert client_ids[4] in manager.connections


@pytest.mark.asyncio
async def test_b7_broadcast_uses_list_snapshot():
    """B7: ``broadcast`` 源码用 ``list(self.connections.items())`` snapshot。

    回归断言：静态验证 broadcast 方法迭代前对 ``self.connections.items()`` 取 ``list()``
    快照，与字典删除解耦。
    """
    from backend.core.websocket.manager import WebSocketManager

    source = inspect.getsource(WebSocketManager.broadcast)
    # 应包含 list(self.connections.items()) 调用
    assert "list(self.connections.items())" in source, (
        "broadcast 未使用 list(self.connections.items()) snapshot 保护并发修改"
    )


@pytest.mark.asyncio
async def test_b7_broadcast_handles_send_failure_gracefully():
    """B7: broadcast 中 send 失败的连接被加入 disconnected 列表后清理，不抛异常。

    补充断言：send 抛异常时 broadcast 的 except 捕获，后续 disconnect 清理，
    不影响其他连接的广播。
    """
    from backend.core.websocket.manager import WebSocketManager

    manager = WebSocketManager()
    # 一个正常 + 一个会失败的连接
    ok_conn = _make_fake_connection("ok-client", send_delay=0)
    fail_conn = _make_fake_connection("fail-client", send_delay=0)

    # 让 fail_conn 的 send 抛异常
    async def fail_send(data):
        raise ConnectionError("模拟连接失败")

    fail_conn.send = fail_send

    manager.connections["ok-client"] = ok_conn
    manager.connections["fail-client"] = fail_conn

    # broadcast 应正常完成（不抛异常）
    await manager.broadcast({"type": "test"})

    # fail-client 因 send 失败被 disconnect 清理
    assert "fail-client" not in manager.connections
    # ok-client 保留
    assert "ok-client" in manager.connections


@pytest.mark.asyncio
async def test_b7_broadcast_exclude_option():
    """B7: broadcast 的 exclude 参数正确排除指定 client_id。

    补充断言：exclude 参数语义正常，不向被排除的连接发送消息。
    """
    from backend.core.websocket.manager import WebSocketManager

    manager = WebSocketManager()
    conn_a = _make_fake_connection("client-a", send_delay=0)
    conn_b = _make_fake_connection("client-b", send_delay=0)

    # 用 spy 计数 send 调用
    send_count = {"a": 0, "b": 0}

    async def spy_send_a(data):
        send_count["a"] += 1

    async def spy_send_b(data):
        send_count["b"] += 1

    conn_a.send = spy_send_a
    conn_b.send = spy_send_b

    manager.connections["client-a"] = conn_a
    manager.connections["client-b"] = conn_b

    await manager.broadcast({"type": "test"}, exclude="client-a")

    # client-a 被排除，未收到消息
    assert send_count["a"] == 0
    # client-b 收到消息
    assert send_count["b"] == 1


@pytest.mark.asyncio
async def test_b7_broadcast_to_empty_connections():
    """B7: broadcast 在空连接字典上不抛异常。

    补充断言：边界场景——无连接时 broadcast 正常返回。
    """
    from backend.core.websocket.manager import WebSocketManager

    manager = WebSocketManager()
    # 不应抛异常
    await manager.broadcast({"type": "test"})
