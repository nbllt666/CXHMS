"""HybridSearch 单元测试。

覆盖修复点：
    - B5: HybridSearch 跨 agent 泄漏修复（``_keyword_search`` 透传 ``workspace_id``/``agent_id``）

设计原则：
    - 用 ``memory_manager`` fixture（已注入 fake_vector_store + fake_embedding）作为
      HybridSearch 的 ``sqlite_manager`` 参数（memory_manager 有 ``search_memories`` 方法）
    - 用 ``fake_vector_store`` + ``fake_embedding`` 直接构造 HybridSearch
    - 验证 keyword / vector / hybrid 三种搜索路径均透传 agent_id，跨 agent 不泄漏
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def hybrid_search(memory_manager, fake_vector_store, fake_embedding):
    """提供 HybridSearch 实例（用 memory_manager 作为 sqlite_manager）。

    memory_manager 已注入 fake_embedding + fake_vector_store，故 HybridSearch 的
    vector_search 与 keyword_search 均可用。memory_manager 提供 search_memories
    方法（被 HybridSearch 当作 sqlite_manager 调用）。
    """
    from backend.core.memory.hybrid_search import HybridSearch

    return HybridSearch(
        vector_store=fake_vector_store,
        sqlite_manager=memory_manager,
        embedding_model=fake_embedding,
    )


# --------------------------------------------------------------------------- #
# B5: _keyword_search 透传 agent_id
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b5_keyword_search_passes_agent_id(hybrid_search, memory_manager):
    """B5: HybridSearch._keyword_search 透传 agent_id，结果仅含当前 agent 记忆。

    回归断言：修复前 ``_keyword_search`` 调 ``sqlite_manager.search_memories`` 未透传
    ``workspace_id``/``agent_id``，关键词搜索返回全部 agent 记忆；
    修复后透传 ``workspace_id=options.workspace_id or "default"`` 与 ``agent_id=options.agent_id``。
    """
    from backend.core.memory.hybrid_search import HybridSearchOptions

    # 写入 agent A 与 agent B 的记忆（content 都含 "苹果"，便于关键词匹配）
    memory_manager.write_memory(
        content="Agent A 的苹果记忆",
        memory_type="long_term",
        importance=4,
        agent_id="agent-a",
        workspace_id="ws",
    )
    memory_manager.write_memory(
        content="Agent B 的苹果记忆",
        memory_type="long_term",
        importance=4,
        agent_id="agent-b",
        workspace_id="ws",
    )

    # HybridSearch 仅用关键词搜索 agent-a
    options = HybridSearchOptions(
        query="苹果",
        use_vector=False,
        use_keyword=True,
        agent_id="agent-a",
        workspace_id="ws",
        min_score=0.0,
    )
    results = await hybrid_search.search(options)

    contents = [r.content for r in results]
    assert "Agent A 的苹果记忆" in contents
    assert "Agent B 的苹果记忆" not in contents, "B5 回归：HybridSearch 关键词搜索跨 agent 泄漏"


@pytest.mark.asyncio
async def test_b5_keyword_search_agent_b_isolated(hybrid_search, memory_manager):
    """B5: 切换 agent_id 到 agent-b，结果仅含 agent-b 记忆（双向隔离验证）。"""
    from backend.core.memory.hybrid_search import HybridSearchOptions

    memory_manager.write_memory(
        content="Agent A 的香蕉记忆",
        memory_type="long_term",
        importance=4,
        agent_id="agent-a",
        workspace_id="ws",
    )
    memory_manager.write_memory(
        content="Agent B 的香蕉记忆",
        memory_type="long_term",
        importance=4,
        agent_id="agent-b",
        workspace_id="ws",
    )

    options = HybridSearchOptions(
        query="香蕉",
        use_vector=False,
        use_keyword=True,
        agent_id="agent-b",
        workspace_id="ws",
        min_score=0.0,
    )
    results = await hybrid_search.search(options)

    contents = [r.content for r in results]
    assert "Agent B 的香蕉记忆" in contents
    assert "Agent A 的香蕉记忆" not in contents


# --------------------------------------------------------------------------- #
# B5: _vector_search 透传 agent_id
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b5_vector_search_passes_agent_id(hybrid_search, memory_manager):
    """B5: HybridSearch._vector_search 透传 agent_id，向量结果仅含当前 agent 记忆。

    回归断言：``_vector_search`` 调 ``vector_store.search_similar`` 时条件性传递
    ``agent_id``（仅当 search_similar 签名支持时）。fake_vector_store 的 search_similar
    按 metadata.agent_id 过滤，故 agent-a 搜索不返回 agent-b 的向量。
    """
    from backend.core.memory.hybrid_search import HybridSearchOptions

    # 写入两个 agent 的相似内容（向量相近，但 agent 不同）
    memory_manager.write_memory(
        content="向量搜索测试记忆苹果",
        memory_type="long_term",
        importance=4,
        agent_id="agent-a",
        workspace_id="ws",
    )
    memory_manager.write_memory(
        content="向量搜索测试记忆苹果",
        memory_type="long_term",
        importance=4,
        agent_id="agent-b",
        workspace_id="ws",
    )

    # 仅用向量搜索 agent-a
    options = HybridSearchOptions(
        query="向量搜索测试记忆苹果",
        use_vector=True,
        use_keyword=False,
        agent_id="agent-a",
        workspace_id="ws",
        min_score=0.0,
        limit=10,
    )
    results = await hybrid_search.search(options)

    # 所有结果应属于 agent-a（fake_vector_store 按 metadata.agent_id 过滤）
    for r in results:
        metadata = r.metadata or {}
        rec_agent = metadata.get("agent_id")
        assert rec_agent == "agent-a", (
            f"B5 回归：向量搜索跨 agent 泄漏，结果含 agent={rec_agent}"
        )


# --------------------------------------------------------------------------- #
# B5: hybrid search（vector + keyword）整体 agent 隔离
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b5_hybrid_search_agent_isolation(hybrid_search, memory_manager):
    """B5: HybridSearch 整体（vector + keyword 合并）按 agent_id 隔离。

    回归断言：合并后的结果不应包含其他 agent 的记忆，无论来自 vector 还是 keyword 路径。
    """
    from backend.core.memory.hybrid_search import HybridSearchOptions

    memory_manager.write_memory(
        content="混合搜索 Agent A 的橙子记忆",
        memory_type="long_term",
        importance=5,
        agent_id="agent-a",
        workspace_id="ws",
    )
    memory_manager.write_memory(
        content="混合搜索 Agent B 的橙子记忆",
        memory_type="long_term",
        importance=5,
        agent_id="agent-b",
        workspace_id="ws",
    )

    options = HybridSearchOptions(
        query="橙子",
        use_vector=True,
        use_keyword=True,
        agent_id="agent-a",
        workspace_id="ws",
        min_score=0.0,
        limit=10,
    )
    results = await hybrid_search.search(options)

    contents = [r.content for r in results]
    assert "混合搜索 Agent A 的橙子记忆" in contents
    assert "混合搜索 Agent B 的橙子记忆" not in contents, (
        "B5 回归：HybridSearch 混合搜索跨 agent 泄漏"
    )


@pytest.mark.asyncio
async def test_b5_keyword_search_source_tag(hybrid_search, memory_manager):
    """B5: 关键词搜索结果的 source 字段为 'keyword'，验证搜索路径确实经过 _keyword_search。

    补充断言：确保结果来自 keyword 路径（而非 vector 路径），验证透传逻辑生效。
    """
    from backend.core.memory.hybrid_search import HybridSearchOptions

    memory_manager.write_memory(
        content="source 标签测试记忆西瓜",
        memory_type="long_term",
        importance=3,
        agent_id="agent-a",
        workspace_id="ws",
    )

    options = HybridSearchOptions(
        query="西瓜",
        use_vector=False,
        use_keyword=True,
        agent_id="agent-a",
        workspace_id="ws",
        min_score=0.0,
    )
    results = await hybrid_search.search(options)
    assert len(results) > 0
    assert all(r.source in ("keyword", "hybrid") for r in results)
