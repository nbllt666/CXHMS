"""SubTask 8.3 - 记忆写入与搜索场景。

覆盖死区：通过 POST /api/memories 显式写入记忆后，POST /api/memories/search
应能按关键词命中；memory_type 过滤与返回结构。验证写入-检索业务闭环而非仅状态码。

注：聊天路由 /api/chat 不会主动调用 memory_mgr.write_memory 持久化用户消息
（仅读取记忆做上下文增强），因此本场景通过显式 POST /api/memories 触发写入。
search 端点底层为 SQLite LIKE 关键词匹配（非向量检索），向量检索语义见
test_semantic_search.py。
"""


def _create_memory(sim_actor, content, memory_type="long_term", tags=None, importance=3):
    """辅助：通过 POST /api/memories 创建一条记忆，返回 memory_id。

    对齐 MemoryCreateRequest 字段（content/type/importance/tags/metadata/
    permanent/workspace_id/agent_id）。
    """
    body = {
        "content": content,
        "type": memory_type,
        "importance": importance,
        "tags": tags or [],
        "metadata": {},
        "permanent": False,
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


def test_search_returns_empty_for_unknown_query(sim_actor):
    """搜索一个不存在的关键词，应返回空列表（total=0）。"""
    results = sim_actor.search_memory("完全不存在的词汇XYZ123456789")
    assert results == [], f"不存在的查询应返回空列表，实际: {results!r}"


def test_search_endpoint_responds(sim_actor):
    """搜索端点可访问且返回结构正确（status/memories/total）。"""
    resp = sim_actor.client.post(
        "/api/memories/search",
        json={"query": "任意查询", "limit": 5},
    )
    assert resp.status_code == 200, f"搜索端点不可访问: status={resp.status_code}"
    data = resp.json()
    assert data["status"] == "success", f"搜索应返回 success: {data!r}"
    assert "memories" in data, f"响应应包含 memories 字段: {data!r}"
    assert isinstance(data["memories"], list), f"memories 应为 list: {data!r}"
    assert "total" in data, f"响应应包含 total 字段: {data!r}"


def test_create_memory_then_search(sim_actor):
    """创建一条记忆后，按内容关键词应能搜索命中。"""
    _create_memory(sim_actor, "我喜欢吃苹果和香蕉", memory_type="long_term")
    results = sim_actor.search_memory("苹果")
    assert any("苹果" in m.get("content", "") for m in results), (
        f"搜索'苹果'应命中刚创建的记忆，实际: {results!r}"
    )
    # 反向验证：搜索另一个不存在的关键词不应命中该记忆
    unrelated = sim_actor.search_memory("橙子柚子柠檬")
    assert not any("苹果" in m.get("content", "") for m in unrelated), (
        f"搜索'橙子柚子柠檬'不应命中苹果记忆，实际: {unrelated!r}"
    )


def test_search_with_memory_type_filter(sim_actor):
    """创建不同 type 的记忆，按 memory_type 过滤应只返回对应类型。"""
    _create_memory(sim_actor, "长期记忆内容-测试场景一", memory_type="long_term")
    _create_memory(sim_actor, "短期记忆内容-测试场景二", memory_type="short_term")

    # 仅搜 long_term
    long_results = sim_actor.search_memory("测试场景", memory_type="long_term")
    assert long_results, "long_term 搜索应至少返回一条记忆"
    assert all(m.get("type") == "long_term" for m in long_results), (
        f"memory_type=long_term 过滤失效，含其他类型: {long_results!r}"
    )
    assert any("长期记忆内容" in m.get("content", "") for m in long_results), (
        f"应命中 long_term 记忆: {long_results!r}"
    )

    # 仅搜 short_term
    short_results = sim_actor.search_memory("测试场景", memory_type="short_term")
    assert short_results, "short_term 搜索应至少返回一条记忆"
    assert all(m.get("type") == "short_term" for m in short_results), (
        f"memory_type=short_term 过滤失效，含其他类型: {short_results!r}"
    )
    assert any("短期记忆内容" in m.get("content", "") for m in short_results), (
        f"应命中 short_term 记忆: {short_results!r}"
    )


def test_search_result_structure(sim_actor):
    """搜索返回的记忆包含必要字段 id/content/type。"""
    _create_memory(sim_actor, "结构验证用记忆内容")
    results = sim_actor.search_memory("结构验证")
    assert results, "应至少返回一条记忆"
    m = results[0]
    assert "id" in m, f"记忆应包含 id 字段: {m!r}"
    assert "content" in m, f"记忆应包含 content 字段: {m!r}"
    assert "type" in m, f"记忆应包含 type 字段: {m!r}"
    assert m["content"], f"content 不应为空: {m!r}"
    assert isinstance(m["id"], int), f"id 应为整数: {m!r}"
