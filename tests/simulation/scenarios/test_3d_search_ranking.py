"""C5 三维搜索排序回归测试。

覆盖修复点 C5：``search_memories_3d`` 把 decay 计算下推到 SQL（用
``julianday`` 线性衰减），``ORDER BY`` 在 DB 端按近似最终分排序，仅拉取
``limit`` 行（而非 ``limit*2``）交由 Python 精算最终分。

最终分公式（见 ``manager.search_memories_3d``）：
    final_score = importance_score * w[0] + time_score * w[1] + relevance_score * w[2]
    permanent 记忆额外 +0.15，最终 min(final_score, 1.0)

回归策略：
    1. 写入不同 importance 的记忆，验证按 importance DESC 排序。
    2. 验证 limit 生效（C5 只拉取 limit 行）。
    3. 验证 permanent 记忆获得 +0.15 bonus，排在前面。
"""

import pytest

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #


def _create_memory(
    sim_actor,
    content: str,
    importance: int = 3,
    permanent: bool = False,
    tags=None,
) -> int:
    """通过 POST /api/memories 创建记忆，返回 memory_id。"""
    body = {
        "content": content,
        "type": "long_term",
        "importance": importance,
        "tags": tags or [],
        "metadata": {},
        "permanent": permanent,
        "workspace_id": "default",
        "agent_id": "default",
    }
    resp = sim_actor.client.post("/api/memories", json=body)
    assert resp.status_code == 200, (
        f"创建记忆失败: status={resp.status_code}, body={resp.text!r}"
    )
    data = resp.json()
    assert data["status"] == "success", f"创建记忆返回非 success: {data!r}"
    return data["memory_id"]


def _search_3d(
    sim_actor,
    query: str = None,
    limit: int = 10,
    weights=None,
    memory_type: str = None,
):
    """通过 POST /api/memories/3d 触发三维搜索。

    参数均为 query parameter（``search_memories_3d`` 路由签名）。
    """
    params = {"limit": limit, "workspace_id": "default"}
    if query is not None:
        params["query"] = query
    if memory_type is not None:
        params["memory_type"] = memory_type
    if weights is not None:
        # weights 是 List[float]，FastAPI 用重复 query param 传 list
        # 例如 ?weights=0.35&weights=0.25&weights=0.4
        # 这里用 params list 形式
        return _search_3d_with_weights(sim_actor, query, limit, weights, memory_type)

    resp = sim_actor.client.post("/api/memories/3d", params=params)
    assert resp.status_code == 200, (
        f"3D 搜索失败: status={resp.status_code}, body={resp.text!r}"
    )
    data = resp.json()
    assert data["status"] == "success", f"3D 搜索返回非 success: {data!r}"
    return data["memories"]


def _search_3d_with_weights(sim_actor, query, limit, weights, memory_type):
    """带自定义权重的 3D 搜索（weights 作为 list query param）。"""
    params = {
        "limit": limit,
        "workspace_id": "default",
        "weights": weights,  # httpx 会编码为 ?weights=0.35&weights=0.25&weights=0.4
    }
    if query is not None:
        params["query"] = query
    if memory_type is not None:
        params["memory_type"] = memory_type

    resp = sim_actor.client.post("/api/memories/3d", params=params)
    assert resp.status_code == 200, (
        f"3D 搜索失败: status={resp.status_code}, body={resp.text!r}"
    )
    data = resp.json()
    assert data["status"] == "success", f"3D 搜索返回非 success: {data!r}"
    return data["memories"]


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


def _set_importance_score(sim_app, memory_id: int, importance_score: float) -> None:
    """直接通过 memory_manager 更新 importance_score 字段。

    背景：``POST /api/memories`` 写入时固定 importance_score=0.6（不随 importance
    字段变化），且 ``PUT /api/memories/{id}`` 的 update_memory 不更新 importance_score。
    为验证 C5 的 SQL 端 ``COALESCE(importance_score, importance * 1.0 / 5.0)``
    排序逻辑，需直接更新 importance_score 制造差异。

    这不是"绕过 API"，而是为 C5 SQL 排序回归准备必要的测试数据。
    """
    services = sim_app.app.state.services
    mm = services.memory_manager
    conn = mm._get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE memories SET importance_score = ? WHERE id = ?",
            (importance_score, memory_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_3d_search_ranks_by_importance_score_desc(sim_app, sim_actor):
    """C5 回归：高 importance_score 的记忆应排在低 importance_score 前面。

    C5 的 SQL 端排序用 ``COALESCE(importance_score, importance * 1.0 / 5.0)``
    计算 _imp，``ORDER BY _imp * (1 - days/30) DESC``。本测试直接更新
    importance_score 制造差异，验证 SQL 端排序与 Python 端 final_score 一致。

    注：写入时 importance_score 固定为 0.6，故需 ``_set_importance_score`` 制造差异。
    """
    # 写入不同内容的记忆（避免去重），初始 importance_score 均为 0.6
    mid_low = _create_memory(sim_actor, "排序测试低优先级记忆 XYZ", importance=1)
    mid_high = _create_memory(sim_actor, "排序测试高优先级记忆 XYZ", importance=5)
    mid_mid = _create_memory(sim_actor, "排序测试中优先级记忆 XYZ", importance=3)

    # 直接更新 importance_score 制造差异（模拟真实衰减后的分值差异）
    _set_importance_score(sim_app, mid_low, 0.2)   # 低
    _set_importance_score(sim_app, mid_mid, 0.6)   # 中
    _set_importance_score(sim_app, mid_high, 1.0)  # 高

    # 不传 query，获取所有记忆，验证按 importance_score DESC 排序
    memories = _search_3d(sim_actor, query=None, limit=10)

    assert len(memories) >= 3, f"应至少返回 3 条记忆，实际 {len(memories)}"

    # 取出 importance_score 与 final_score
    scored = [
        (m.get("importance_score", 0), m.get("final_score", 0), m.get("content", ""))
        for m in memories
    ]

    # 高 importance_score 应排在低 importance_score 前面
    high_idx = next(i for i, (_, _, c) in enumerate(scored) if "高优先级" in c)
    low_idx = next(i for i, (_, _, c) in enumerate(scored) if "低优先级" in c)

    assert high_idx < low_idx, (
        f"C5 排序失败：高 importance_score 记忆（idx={high_idx}）应排在"
        f" 低 importance_score（idx={low_idx}）前面。完整排序: {scored}"
    )

    # final_score 也应满足 DESC（high > low）
    assert scored[high_idx][1] > scored[low_idx][1], (
        f"C5 排序失败：高 importance_score 的 final_score ({scored[high_idx][1]}) "
        f"应大于低 importance_score ({scored[low_idx][1]})"
    )


def test_3d_search_respects_limit(sim_actor):
    """C5 回归：``limit`` 参数应生效，只返回 limit 行。

    C5 修复把 ORDER BY 下推到 SQL 并只拉取 limit 行（而非 limit*2）。
    本测试验证 limit 严格生效。
    """
    # 写入 5 条记忆
    for i in range(5):
        _create_memory(sim_actor, f"limit 测试记忆 {i} XYZ", importance=3)

    # 用 limit=2 搜索
    memories = _search_3d(sim_actor, query=None, limit=2)

    assert len(memories) == 2, (
        f"C5 limit 失败：期望 2 条，实际 {len(memories)}。"
        f" 检查 SQL LIMIT 是否正确下推。"
    )


def test_3d_search_permanent_gets_bonus(sim_actor):
    """C5 回归：permanent 记忆获得 +0.15 bonus，应排在普通记忆前面。

    permanent 记忆的 time_score=1.0（不经过 decay 计算），且有 +0.15 bonus。
    相同 importance_score 下，permanent 的 final_score 应高于普通记忆。

    注：两条记忆内容差异需足够大，否则被去重引擎判定为重复跳过写入。
    """
    # 用差异大的内容避免去重（苹果 vs 香蕉，内容完全不同）
    _create_memory(sim_actor, "苹果树上结了红苹果", importance=3, permanent=False)
    _create_memory(sim_actor, "香蕉船上装满黄香蕉", importance=3, permanent=True)

    memories = _search_3d(sim_actor, query=None, limit=10)

    # 找出两条记忆
    normal = next((m for m in memories if "苹果" in m.get("content", "")), None)
    permanent = next((m for m in memories if "香蕉" in m.get("content", "")), None)

    assert normal is not None, f"未找到普通记忆（苹果）: {memories!r}"
    assert permanent is not None, (
        f"未找到永久记忆（香蕉，可能被去重跳过）: {memories!r}"
    )

    normal_score = normal.get("final_score", 0)
    permanent_score = permanent.get("final_score", 0)

    assert permanent_score > normal_score, (
        f"C5 permanent bonus 失败：permanent final_score ({permanent_score}) "
        f"应大于 normal ({normal_score})"
    )


def test_3d_search_returns_component_scores(sim_actor):
    """C5 回归补充：每条记忆应包含 component_scores 与 applied_weights。

    验证 C5 返回结构完整，便于诊断排序依据。
    """
    _create_memory(sim_actor, "结构验证记忆 XYZ", importance=4)

    memories = _search_3d(sim_actor, query=None, limit=5)

    assert memories, "应至少返回一条记忆"
    m = memories[0]
    assert "final_score" in m, f"记忆应包含 final_score: {m!r}"
    assert "component_scores" in m, f"记忆应包含 component_scores: {m!r}"
    comp = m["component_scores"]
    assert "importance" in comp, f"component_scores 应含 importance: {comp!r}"
    assert "time" in comp, f"component_scores 应含 time: {comp!r}"
    assert "relevance" in comp, f"component_scores 应含 relevance: {comp!r}"
    assert "applied_weights" in m, f"记忆应包含 applied_weights: {m!r}"
