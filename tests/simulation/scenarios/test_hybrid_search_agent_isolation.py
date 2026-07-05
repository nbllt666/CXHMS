"""B5 HybridSearch agent 隔离回归测试。

覆盖修复点 B5：``HybridSearch._keyword_search`` 必须透传 ``workspace_id`` 与
``agent_id`` 到 ``sqlite_manager.search_memories``，否则关键词搜索会跨 agent 泄漏。

B5 修复位置：``backend/core/memory/hybrid_search.py`` 的 ``_keyword_search`` 方法，
    显式传递 ``workspace_id=options.workspace_id or "default"`` 与
    ``agent_id=options.agent_id``。

回归策略：
    1. agent_A 写入"苹果"相关记忆，agent_B 写入"香蕉"相关记忆。
    2. 通过 ``POST /api/memories/rag?agent_id=agent_A`` 触发 hybrid_search。
    3. 验证 agent_A 的搜索结果不含 agent_B 的"香蕉"内容，反之亦然。
    4. 同时验证 ``_keyword_search`` 与 ``search_memories`` 的 agent_id 透传路径。

注：agent_A/agent_B 用非 default 的 agent_id，使 ``_get_table_name`` 路由到
各自专属表（``memories_isol_a`` / ``memories_isol_b``），这是隔离的物理基础。
default agent 共用 memories 表，靠 workspace_id 过滤，故本测试用非 default agent
才能验证 B5 的 agent_id 透传。
"""

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #


def _create_memory(sim_actor, content: str, agent_id: str) -> int:
    """通过 POST /api/memories 为指定 agent 创建一条记忆。"""
    body = {
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


def _rag_search(sim_actor, query: str, agent_id: str, limit: int = 20) -> list:
    """通过 POST /api/memories/rag 触发 hybrid_search。

    rag_search 端点签名 ``rag_search(query: str, ..., agent_id: str = "default")``,
    query/agent_id 均为 query parameter（非 body）。
    """
    resp = sim_actor.client.post(
        "/api/memories/rag",
        params={"query": query, "workspace_id": "default", "limit": limit, "agent_id": agent_id},
    )
    assert resp.status_code == 200, (
        f"RAG 搜索失败: agent={agent_id}, status={resp.status_code}, body={resp.text!r}"
    )
    data = resp.json()
    assert data["status"] == "success", f"RAG 搜索返回非 success: {data!r}"
    return data["results"]


def _keyword_search(sim_actor, query: str, agent_id: str, limit: int = 20) -> list:
    """通过 POST /api/memories/search 走 keyword_search 路径（非向量）。"""
    body = {
        "query": query,
        "limit": limit,
        "workspace_id": "default",
        "agent_id": agent_id,
    }
    resp = sim_actor.client.post("/api/memories/search", json=body)
    assert resp.status_code == 200, (
        f"关键词搜索失败: agent={agent_id}, status={resp.status_code}, body={resp.text!r}"
    )
    data = resp.json()
    assert data["status"] == "success", f"关键词搜索返回非 success: {data!r}"
    return data["memories"]


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


def test_hybrid_search_agent_a_excludes_agent_b_memories(sim_actor):
    """B5 回归：agent_A 的 hybrid_search 结果不应包含 agent_B 的记忆。

    步骤：
        1. agent_A 写入"苹果"记忆，agent_B 写入"香蕉"记忆。
        2. agent_A 调用 RAG 搜索（hybrid_search）。
        3. 验证 agent_A 的结果不含"香蕉"内容。
    """
    agent_a = "hs_isol_a"
    agent_b = "hs_isol_b"

    _create_memory(sim_actor, "苹果树上结了红苹果", agent_a)
    _create_memory(sim_actor, "香蕉船上装满黄香蕉", agent_b)

    # agent_A 的 RAG 搜索
    results_a = _rag_search(sim_actor, query="苹果", agent_id=agent_a)
    contents_a = [r.get("content", "") for r in results_a]

    # 关键断言：agent_A 的结果不含 agent_B 的"香蕉"内容
    assert not any("香蕉" in c for c in contents_a), (
        f"B5 隔离失败：agent_A 的 hybrid_search 结果泄漏了 agent_B 的香蕉内容: {contents_a!r}"
    )

    # 反向验证：agent_B 的搜索结果不含 agent_A 的"苹果"内容
    results_b = _rag_search(sim_actor, query="香蕉", agent_id=agent_b)
    contents_b = [r.get("content", "") for r in results_b]
    assert not any("苹果" in c for c in contents_b), (
        f"B5 隔离失败：agent_B 的 hybrid_search 结果泄漏了 agent_A 的苹果内容: {contents_b!r}"
    )


def test_keyword_search_agent_isolation(sim_actor):
    """B5 回归补充：``search_memories`` 的 agent_id 透传路径。

    ``_keyword_search`` 底层调用 ``sqlite_manager.search_memories``，B5 修复确保
    透传 agent_id。本测试直接走 /api/memories/search 端点验证该路径。
    """
    agent_a = "kw_isol_a"
    agent_b = "kw_isol_b"

    _create_memory(sim_actor, "苹果果汁甜苹果", agent_a)
    _create_memory(sim_actor, "香蕉奶昔香香蕉", agent_b)

    # agent_A 的关键词搜索
    results_a = _keyword_search(sim_actor, query="苹果", agent_id=agent_a)
    contents_a = [m.get("content", "") for m in results_a]

    assert not any("香蕉" in c for c in contents_a), (
        f"B5 隔离失败：agent_A 的关键词搜索结果泄漏了 agent_B 的香蕉内容: {contents_a!r}"
    )
    assert any("苹果" in c for c in contents_a), (
        f"agent_A 应能搜到自己的苹果记忆: {contents_a!r}"
    )

    # agent_B 的关键词搜索
    results_b = _keyword_search(sim_actor, query="香蕉", agent_id=agent_b)
    contents_b = [m.get("content", "") for m in results_b]
    assert not any("苹果" in c for c in contents_b), (
        f"B5 隔离失败：agent_B 的关键词搜索结果泄漏了 agent_A 的苹果内容: {contents_b!r}"
    )
    assert any("香蕉" in c for c in contents_b), (
        f"agent_B 应能搜到自己的香蕉记忆: {contents_b!r}"
    )


def test_default_agent_does_not_leak_to_other_agents(sim_actor):
    """B5 边界回归：default agent 的记忆不应泄漏到其他 agent 的搜索结果。

    default agent 共用 memories 表，非 default agent 用专属表。B5 修复确保
    hybrid_search 的 agent_id 透传不会让 default 表的记忆泄漏到其他 agent。
    """
    agent_other = "other_isol"

    # default agent 写入记忆
    _create_memory(sim_actor, "默认agent的苹果记忆", "default")
    # other agent 写入不同内容
    _create_memory(sim_actor, "其他agent的香蕉记忆", agent_other)

    # other agent 搜索"苹果"，不应命中 default agent 的记忆
    results_other = _rag_search(sim_actor, query="苹果", agent_id=agent_other)
    contents_other = [r.get("content", "") for r in results_other]
    assert not any("默认agent" in c for c in contents_other), (
        f"B5 边界失败：default agent 的记忆泄漏到 agent '{agent_other}': {contents_other!r}"
    )

    # 反向：default agent 搜索"香蕉"，不应命中 other agent 的记忆
    results_default = _rag_search(sim_actor, query="香蕉", agent_id="default")
    contents_default = [r.get("content", "") for r in results_default]
    assert not any("其他agent" in c for c in contents_default), (
        f"B5 边界失败：agent '{agent_other}' 的记忆泄漏到 default agent: {contents_default!r}"
    )
