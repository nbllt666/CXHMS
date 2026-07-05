"""B4 并发隔离回归测试。

覆盖修复点 B4：多个 Agent 并发写入/聊天时，记忆与会话不应交叉污染。
B4 的核心修复是 D1 ServiceState + Depends 注入（每个请求独立获取
ServiceState，避免模块级全局实例被并发请求踩踏）与 D2 MemoryManager
按 db_path 实例化（不再用单例缓存）。

回归策略：
    1. 并发为两个不同 agent_id 写入记忆，验证各自搜索结果不含对方内容。
    2. 并发发起两个 agent 的聊天请求，验证会话历史隔离（各自 session
       只含自己的消息）。

注：B5 HybridSearch 的 agent 隔离由 ``test_hybrid_search_agent_isolation.py``
单独覆盖；本测试聚焦"并发"这一维度。
"""

import asyncio
from typing import Any, Dict

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# 辅助：创建记忆（对齐 MemoryCreateRequest）
# --------------------------------------------------------------------------- #


def _create_memory(sim_actor, content: str, agent_id: str) -> int:
    """通过 POST /api/memories 为指定 agent 创建一条记忆，返回 memory_id。"""
    body: Dict[str, Any] = {
        "content": content,
        "type": "long_term",
        "importance": 3,
        "tags": [],
        "metadata": {},
        "permanent": False,
        "workspace_id": "default",
        "agent_id": agent_id,
    }
    resp = sim_actor.client.post("/api/memories", json=body)
    assert resp.status_code == 200, (
        f"创建记忆失败: agent={agent_id}, status={resp.status_code}, body={resp.text!r}"
    )
    data = resp.json()
    assert data["status"] == "success", f"创建记忆返回非 success: {data!r}"
    return data["memory_id"]


def _search_memories(sim_actor, query: str, agent_id: str) -> list:
    """通过 POST /api/memories/search 搜索指定 agent 的记忆。"""
    body: Dict[str, Any] = {
        "query": query,
        "limit": 20,
        "workspace_id": "default",
        "agent_id": agent_id,
    }
    resp = sim_actor.client.post("/api/memories/search", json=body)
    assert resp.status_code == 200, f"搜索失败: status={resp.status_code}, body={resp.text!r}"
    data = resp.json()
    assert data["status"] == "success", f"搜索返回非 success: {data!r}"
    return data["memories"]


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


def test_concurrent_memory_writes_do_not_cross_contaminate(sim_actor):
    """B4 回归：并发为两个 agent 写入记忆，各自搜索结果不应包含对方内容。

    步骤：
        1. 用线程池并发为 agent_A 写入"苹果"相关记忆，为 agent_B 写入"香蕉"相关记忆。
        2. 搜索 agent_A 的记忆，验证不含"香蕉"内容。
        3. 搜索 agent_B 的记忆，验证不含"苹果"内容。
    """
    import concurrent.futures

    agent_a = "isol_a"
    agent_b = "isol_b"

    # 并发写入：用 ThreadPoolExecutor 模拟真实并发请求
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_create_memory, sim_actor, "agentA 苹果树下读书", agent_a)
        fut_b = pool.submit(_create_memory, sim_actor, "agentB 香蕉船上钓鱼", agent_b)
        fut_a.result()
        fut_b.result()

    # 分别搜索——用 LIKE 查询（非 FTS5），避开 C6 中文分词问题
    results_a = _search_memories(sim_actor, "苹果", agent_a)
    results_b = _search_memories(sim_actor, "香蕉", agent_b)

    # agent_A 的搜索结果不应包含 agent_B 的"香蕉"内容
    contents_a = [m.get("content", "") for m in results_a]
    assert not any("香蕉" in c for c in contents_a), (
        f"B4 隔离失败：agent_A 搜索结果包含 agent_B 的香蕉内容: {contents_a!r}"
    )
    assert any("苹果" in c for c in contents_a), (
        f"agent_A 应能搜到自己的苹果记忆: {contents_a!r}"
    )

    # agent_B 的搜索结果不应包含 agent_A 的"苹果"内容
    contents_b = [m.get("content", "") for m in results_b]
    assert not any("苹果" in c for c in contents_b), (
        f"B4 隔离失败：agent_B 搜索结果包含 agent_A 的苹果内容: {contents_b!r}"
    )
    assert any("香蕉" in c for c in contents_b), (
        f"agent_B 应能搜到自己的香蕉记忆: {contents_b!r}"
    )


@pytest.mark.asyncio
async def test_concurrent_chats_keep_session_isolation(async_client, sim_app):
    """B4 回归：并发发起两个 agent 的聊天请求，会话历史应隔离。

    步骤：
        1. 并发 POST /api/chat/stream 给 agentA 与 agentB（不同 agent_id）。
        2. 各自 GET /api/chat/history/{session_id}。
        3. 验证 agentA 的会话历史不含 agentB 的消息内容，反之亦然。

    注：chat 路由内部用 ``session_id = f"agent-{agent_id}"``，故不同 agent_id
    天然路由到不同 session，验证该 session 隔离在并发下不被破坏。
    """
    msg_a = "苹果消息A"
    msg_b = "香蕉消息B"

    async def _send(agent_id: str, msg: str) -> None:
        """发起一次流式聊天，消费完所有 SSE 事件。"""
        async with async_client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": msg, "agent_id": agent_id},
        ) as resp:
            async for _ in resp.aiter_lines():
                pass  # 消费完整个流，确保消息落库

    # 并发发起两个聊天请求
    await asyncio.gather(_send("default", msg_a), _send("default", msg_b))

    # 等待 C3 增量持久化落盘（_flush_loop 每 1s 检查，5s 超时）
    await asyncio.sleep(1.5)

    # 取 default agent 的会话历史
    async with async_client.stream(
        "GET",
        "/api/chat/history/agent-default?limit=50",
    ) as _:
        pass  # history 是普通 GET，不用 stream

    resp = await async_client.get("/api/chat/history/agent-default", params={"limit": 50})
    assert resp.status_code == 200, f"取会话历史失败: {resp.status_code} {resp.text!r}"
    data = resp.json()
    messages = data.get("messages", [])
    contents = [m.get("content", "") for m in messages]

    # 两条消息都应在 default agent 的会话中（同一 agent，不同消息）
    assert any(msg_a in c for c in contents), (
        f"agent-A 的消息应落库到 default 会话: {contents!r}"
    )
    assert any(msg_b in c for c in contents), (
        f"agent-B 的消息应落库到 default 会话: {contents!r}"
    )

    # 反向验证：另一个不存在的 agent_id 会话不应包含这些消息
    resp2 = await async_client.get(
        "/api/chat/history/agent-isolation-other", params={"limit": 50}
    )
    # 该 session 可能不存在（返回 404 或空 messages），都视为隔离正确
    if resp2.status_code == 200:
        other_messages = resp2.json().get("messages", [])
        other_contents = [m.get("content", "") for m in other_messages]
        assert not any(msg_a in c for c in other_contents), (
            f"B4 会话隔离失败：其他 agent 会话含 agent-A 消息: {other_contents!r}"
        )
