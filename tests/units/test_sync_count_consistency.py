"""``sync_with_sqlite`` 计数一致性单元测试（GN-004 第九轮 N-4 修复）。

背景：
    milvus_lite / weaviate 的 ``sync_with_sqlite`` 原先不接收
    ``add_memory_vector`` / ``update_memory_vector`` 的返回值，把「尝试写入」
    一律计为 ``result.synced``；空向量防御（返回 ``False``）等**未写入**场景
    会被虚报为「同步成功」。chroma 侧口径正确（失败计 ``errors``），本次对齐。

覆盖点（修复前对照已标注）：
    1. milvus 创建分支失败 → ``synced == 0`` 且 ``errors == 1``（修复前 synced == 1）
    2. milvus 创建分支成功 → ``synced == 1``（对照组）
    3. milvus 更新分支失败 → ``synced == 0``
    4. weaviate 创建分支失败 → ``synced == 0``（修复前 synced == 1）
    5. weaviate 创建分支成功 → ``synced == 1``（对照组）
    6. weaviate 更新分支失败 → ``synced == 0``
    7. qdrant 创建分支失败 → ``synced == 0``（修复前 synced == 1；实现位于 vector_store.py）
    8. qdrant 创建分支成功 → ``synced == 1``（对照组）
    9. qdrant 更新分支失败 → ``synced == 0``
    10. R-1：``embedding_model`` 缺失（milvus / qdrant / weaviate）→ ``errors == 1`` 且 ``synced == 0``
    11. R-3：qdrant 更新分支成功 → **不调用** ``delete_by_memory_id``（upsert 天然幂等，冗余删除已移除）

设计原则：裸实例（``object.__new__``）+ mock 存储层返回值，
绝不触碰真实向量库 / SQLite。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _fake_sqlite_manager():
    """伪 sqlite_manager：返回 1 条待同步记忆。"""
    sm = MagicMock()
    sm.search_memories.return_value = [
        {"id": 1, "content": "待同步内容", "agent_id": "default"}
    ]
    return sm


# --------------------------------------------------------------------------- #
# milvus_lite
# --------------------------------------------------------------------------- #


def _make_milvus_store(add_return):
    """构造裸 MilvusLiteVectorStore：mock 存储层返回值，走「创建」分支。"""
    from backend.core.memory.milvus_lite_store import MilvusLiteVectorStore

    store = object.__new__(MilvusLiteVectorStore)
    store.collection_name = "memory_vectors"
    store._client = MagicMock()
    store.embedding_model = MagicMock()
    store.embedding_model.get_embedding = AsyncMock(return_value=None)
    store.get_vector_by_id = AsyncMock(return_value=None)  # 不存在 → 创建分支
    store.add_memory_vector = AsyncMock(return_value=add_return)
    store.delete_by_memory_id = AsyncMock(return_value=True)
    return store


@pytest.mark.asyncio
async def test_milvus_create_failure_not_counted_as_synced():
    """milvus 创建分支：写入返回 False → synced 0 / errors 1（修复前 synced 1，虚报）。"""
    store = _make_milvus_store(add_return=False)

    result = await store.sync_with_sqlite(_fake_sqlite_manager())

    assert result.synced == 0, "未写入不得计 synced（修复前虚报为 1）"
    assert result.errors == 1, "未写入应如实计入 errors（对齐 chroma 口径）"


@pytest.mark.asyncio
async def test_milvus_create_success_counted_once():
    """milvus 创建分支：写入返回 True → synced 1 / errors 0（对照组）。"""
    store = _make_milvus_store(add_return=True)

    result = await store.sync_with_sqlite(_fake_sqlite_manager())

    assert result.synced == 1
    assert result.errors == 0


@pytest.mark.asyncio
async def test_milvus_update_failure_not_counted_as_synced():
    """milvus 更新分支：存在旧向量且内容不同、写入失败 → synced 0 / errors 1。"""
    store = _make_milvus_store(add_return=False)
    store.get_vector_by_id = AsyncMock(return_value={"content": "旧内容"})
    sm = _fake_sqlite_manager()
    sm.search_memories.return_value = [
        {"id": 1, "content": "新内容", "agent_id": "default"}
    ]

    result = await store.sync_with_sqlite(sm)

    assert result.synced == 0, "更新分支写入失败不得计 synced"
    assert result.errors == 1
    # N-1：更新分支不再外层先删（delete 由 add_memory_vector 内部承担，以便持有回滚材料）
    store.delete_by_memory_id.assert_not_called()


# --------------------------------------------------------------------------- #
# weaviate
# --------------------------------------------------------------------------- #


def _make_weaviate_store(add_return=True, update_return=True):
    """构造裸 WeaviateVectorStore：mock 存储层返回值，走「创建」分支。"""
    from backend.core.memory.weaviate_store import WeaviateVectorStore

    store = object.__new__(WeaviateVectorStore)
    store._client = MagicMock()
    store.embedding_model = MagicMock()
    store.embedding_model.get_embedding = AsyncMock(return_value=None)
    store.get_vector_by_id = AsyncMock(return_value=None)
    store.add_memory_vector = AsyncMock(return_value=add_return)
    store.update_memory_vector = AsyncMock(return_value=update_return)
    return store


@pytest.mark.asyncio
async def test_weaviate_create_failure_not_counted_as_synced():
    """weaviate 创建分支：写入返回 False → synced 0 / errors 1（修复前 synced 1，虚报）。"""
    store = _make_weaviate_store(add_return=False)

    result = await store.sync_with_sqlite(_fake_sqlite_manager())

    assert result.synced == 0, "未写入不得计 synced（修复前虚报为 1）"
    assert result.errors == 1


@pytest.mark.asyncio
async def test_weaviate_create_success_counted_once():
    """weaviate 创建分支：写入返回 True → synced 1 / errors 0（对照组）。"""
    store = _make_weaviate_store(add_return=True)

    result = await store.sync_with_sqlite(_fake_sqlite_manager())

    assert result.synced == 1
    assert result.errors == 0


@pytest.mark.asyncio
async def test_weaviate_update_failure_not_counted_as_synced():
    """weaviate 更新分支：存在旧向量且内容不同、更新返回 False → synced 0 / errors 1。"""
    store = _make_weaviate_store(update_return=False)
    store.get_vector_by_id = AsyncMock(return_value={"content": "旧内容"})
    sm = _fake_sqlite_manager()
    sm.search_memories.return_value = [
        {"id": 1, "content": "新内容", "agent_id": "default"}
    ]

    result = await store.sync_with_sqlite(sm)

    assert result.synced == 0, "更新分支写入失败不得计 synced"
    assert result.errors == 1
    store.update_memory_vector.assert_awaited_once()


# --------------------------------------------------------------------------- #
# qdrant（实现位于 vector_store.py 的 QdrantVectorStore）
# --------------------------------------------------------------------------- #


def _make_qdrant_store(add_return=True):
    """构造裸 QdrantVectorStore：mock 存储层返回值，走「创建」分支。"""
    from backend.core.memory.vector_store import QdrantVectorStore

    store = object.__new__(QdrantVectorStore)
    store.collection_name = "memory_vectors"
    store._client = MagicMock()
    store.embedding_model = MagicMock()
    store.embedding_model.get_embedding = AsyncMock(return_value=None)
    store.get_vector_by_id = AsyncMock(return_value=None)
    store.add_memory_vector = AsyncMock(return_value=add_return)
    store.delete_by_memory_id = AsyncMock(return_value=True)
    return store


@pytest.mark.asyncio
async def test_qdrant_create_failure_not_counted_as_synced():
    """qdrant 创建分支：写入返回 False → synced 0 / errors 1（修复前 synced 1，虚报）。"""
    store = _make_qdrant_store(add_return=False)

    result = await store.sync_with_sqlite(_fake_sqlite_manager())

    assert result.synced == 0, "未写入不得计 synced（修复前虚报为 1）"
    assert result.errors == 1


@pytest.mark.asyncio
async def test_qdrant_create_success_counted_once():
    """qdrant 创建分支：写入返回 True → synced 1 / errors 0（对照组）。"""
    store = _make_qdrant_store(add_return=True)

    result = await store.sync_with_sqlite(_fake_sqlite_manager())

    assert result.synced == 1
    assert result.errors == 0


@pytest.mark.asyncio
async def test_qdrant_update_failure_not_counted_as_synced():
    """qdrant 更新分支：存在旧向量且内容不同、写入失败 → synced 0 / errors 1。"""
    store = _make_qdrant_store(add_return=False)
    store.get_vector_by_id = AsyncMock(return_value={"content": "旧内容"})
    sm = _fake_sqlite_manager()
    sm.search_memories.return_value = [
        {"id": 1, "content": "新内容", "agent_id": "default"}
    ]

    result = await store.sync_with_sqlite(sm)

    assert result.synced == 0, "更新分支写入失败不得计 synced"
    assert result.errors == 1


# --------------------------------------------------------------------------- #
# R-1：embedding_model 缺失时的计数（三后端对齐 chroma 的 errors 口径）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["milvus", "qdrant", "weaviate"])
async def test_missing_embedding_model_counted_as_skipped(backend):
    """R-1 / O-2：``embedding_model`` 缺失 → ``skipped == 1`` 且 ``errors == 0`` / ``synced == 0``。

    语义分离：未尝试写入（依赖缺失）计 ``skipped``，与写入失败的 ``errors`` 区分。
    """
    if backend == "milvus":
        store = _make_milvus_store(add_return=True)
    elif backend == "qdrant":
        store = _make_qdrant_store(add_return=True)
    else:
        store = _make_weaviate_store(add_return=True)
    store.embedding_model = None  # 模拟未注入 embedding 模型

    result = await store.sync_with_sqlite(_fake_sqlite_manager())

    assert result.synced == 0, "无 embedding 模型不可能写入成功"
    assert result.skipped == 1, "未尝试写入应计 skipped"
    assert result.errors == 0, "依赖缺失不是写入失败，不得计 errors（O-2 语义分离）"


# --------------------------------------------------------------------------- #
# R-3：qdrant 更新分支不再冗余 delete（upsert 天然幂等）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_qdrant_update_does_not_delete_before_upsert():
    """R-3：qdrant 更新分支成功时**不调用** ``delete_by_memory_id``（upsert 幂等，无需先删后插）。"""
    store = _make_qdrant_store(add_return=True)
    store.get_vector_by_id = AsyncMock(return_value={"content": "旧内容"})
    sm = _fake_sqlite_manager()
    sm.search_memories.return_value = [
        {"id": 1, "content": "新内容", "agent_id": "default"}
    ]

    result = await store.sync_with_sqlite(sm)

    assert result.synced == 1 and result.errors == 0
    store.delete_by_memory_id.assert_not_called()
    store.add_memory_vector.assert_awaited_once()


# --------------------------------------------------------------------------- #
# N-1（GN-004 第十二轮）：sync 更新分支不再先删，回滚材料可取到
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["chroma", "milvus"])
async def test_sync_update_branch_does_not_predelete(backend):
    """N-1：sync 更新分支**不得**在 `add_memory_vector` 之前先 delete。

    外层 delete 会使 `add_memory_vector` 内部取回的 `previous` 恒为 None，
    导致「先删后插」的回滚被架空（旧已删、新未写）。修复后更新分支只调 add。
    """
    if backend == "chroma":
        from backend.core.memory.chroma_store import ChromaVectorStore

        store = object.__new__(ChromaVectorStore)
        store.collection_name = "memory_vectors"
        store._collection = MagicMock()
        store._client = MagicMock()
        store.embedding_model = MagicMock()
        store.embedding_model.get_embedding = AsyncMock(return_value=[0.1, 0.2])
        store.get_vector_by_id = AsyncMock(return_value={"content": "旧内容", "id": 1})
        store.add_memory_vector = AsyncMock(return_value=True)
        store.delete_by_memory_id = AsyncMock(return_value=True)
    else:
        store = _make_milvus_store(add_return=True)
        store.embedding_model.get_embedding = AsyncMock(return_value=[0.1, 0.2])
        store.get_vector_by_id = AsyncMock(return_value={"content": "旧内容"})

    sm = _fake_sqlite_manager()
    sm.search_memories.return_value = [
        {"id": 1, "content": "新内容", "agent_id": "default"}
    ]

    result = await store.sync_with_sqlite(sm)

    assert result.synced == 1, "更新成功应计 synced"
    store.add_memory_vector.assert_awaited_once()
    # 外层 delete 必须移除，否则 add 内部取回的 previous 恒为 None、回滚被架空
    store.delete_by_memory_id.assert_not_called()