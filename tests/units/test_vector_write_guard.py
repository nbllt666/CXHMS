"""向量写入链路守卫单元测试（P2 修复）。

覆盖点：
    1. 空向量不写入：``_sync_vector_for_memory`` 在 embedding 为空时返回 False，
       且从不调用 ``add_memory_vector``（修复前会把 None 当作向量写入，产生无向量对象）。
    2. 空向量不删除旧数据：``_update_vector_for_memory`` 在 embedding 为空时返回 False，
       且既不调用 ``delete_by_memory_id`` 也不调用 ``add_memory_vector``（保留旧向量）。
    3. 写入幂等：``add_memory_vector`` 每次写入前先删除同 memory_id 的既存对象再插入，
       满足「每次 add 都先删后插」，同一 memory_id 不产生重复对象。
    4. 空 embedding 防御：``add_memory_vector(embedding=None)`` 直接返回 False，
       ``insert`` 从未被调用。
    5. ``delete_by_memory_id`` 删干净：循环删除所有匹配 memory_id 的对象，
       返回值语义为「删过至少 1 个 → True；一个都没有 → False」。

设计原则：
    - 全部使用 ``unittest.mock`` 伪造，**绝不向真实 Weaviate 写入任何对象**。
    - 裸实例用 ``object.__new__`` 构造，不触发 SQLite / Weaviate 真实初始化。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# 测试辅助构造
# --------------------------------------------------------------------------- #


def _bare_manager(embedding_return, add_return=True):
    """构造裸 MemoryManager（object.__new__，不触发 DB / 向量库初始化）。

    Args:
        embedding_return: ``_embedding_model.get_embedding`` 的返回值。
        add_return: ``_vector_store.add_memory_vector`` 的返回值。

    Returns:
        (MemoryManager, 向量库 MagicMock, 嵌入模型 MagicMock)
    """
    from backend.core.memory.manager import MemoryManager

    mm = object.__new__(MemoryManager)
    vector_store = MagicMock()
    vector_store.add_memory_vector = AsyncMock(return_value=add_return)
    vector_store.delete_by_memory_id = AsyncMock(return_value=True)
    embedding_model = MagicMock()
    embedding_model.get_embedding = AsyncMock(return_value=embedding_return)
    mm._vector_store = vector_store
    mm._embedding_model = embedding_model
    return mm, vector_store, embedding_model


def _fake_object(uuid: str) -> MagicMock:
    """构造带 ``uuid`` 属性的伪 Weaviate 对象。"""
    obj = MagicMock()
    obj.uuid = uuid
    return obj


def _make_fake_store(collection: MagicMock):
    """构造裸 WeaviateVectorStore（``_client`` 用 MagicMock 伪造，不连真实服务）。

    ``collections.exists`` 返回 True 使 ``_ensure_collection_for_agent`` 走「已存在」分支，
    ``collections.get`` 始终返回同一个伪 collection，保证 add / delete 打在同一对象上。

    Args:
        collection: 伪 collection（含 query.fetch_objects / data.insert / data.delete_by_id）。

    Returns:
        (WeaviateVectorStore, 伪 client)
    """
    from backend.core.memory.weaviate_store import WeaviateVectorStore

    store = object.__new__(WeaviateVectorStore)
    store.schema_class = "CXHMSMemory"
    client = MagicMock()
    client.collections.exists.return_value = True
    client.collections.get.return_value = collection
    store._client = client
    return store, client


# --------------------------------------------------------------------------- #
# 1 & 2: 调用方空向量校验
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("empty_embedding", [None, []])
def test_sync_vector_skips_write_when_embedding_empty(empty_embedding):
    """空向量不写入：embedding 为 None / 空序列时 ``_sync_vector_for_memory`` 返回 False 且不写库。"""
    mm, vector_store, _ = _bare_manager(embedding_return=empty_embedding)

    result = mm._sync_vector_for_memory(1, "待写入内容", {"agent_id": "default"})

    assert result is False, "空向量必须跳过写入并返回 False"
    vector_store.add_memory_vector.assert_not_called()
    vector_store.delete_by_memory_id.assert_not_called()


@pytest.mark.parametrize("empty_embedding", [None, []])
def test_update_vector_keeps_old_vector_when_embedding_empty(empty_embedding):
    """空向量不删除旧数据：``_update_vector_for_memory`` 空 embedding 时返回 False，不删也不写。"""
    mm, vector_store, _ = _bare_manager(embedding_return=empty_embedding)

    result = mm._update_vector_for_memory(1, "更新后内容", {"agent_id": "default"})

    assert result is False, "空向量必须跳过更新并返回 False"
    vector_store.delete_by_memory_id.assert_not_called()
    vector_store.add_memory_vector.assert_not_called()


def test_sync_vector_writes_and_reports_success_when_embedding_present():
    """对照组：embedding 非空时正常写入，返回值透传存储层 True。"""
    mm, vector_store, _ = _bare_manager(embedding_return=[0.1, 0.2, 0.3])

    result = mm._sync_vector_for_memory(1, "正常内容", {"agent_id": "default"})

    assert result is True
    vector_store.add_memory_vector.assert_awaited_once()


# --------------------------------------------------------------------------- #
# 3: add_memory_vector 写入幂等（先删后插）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_add_memory_vector_is_idempotent():
    """幂等：连续两次 add 同一 memory_id，每次均为「先删同 ID 既存对象 → 再插入」。"""
    calls = []

    existing = MagicMock()
    existing.objects = [_fake_object("uuid-old")]
    empty = MagicMock()
    empty.objects = []

    collection = MagicMock()
    # 每次 delete 消耗 2 次 fetch：先返回 1 个既有对象，再返回空（退出循环）
    collection.query.fetch_objects.side_effect = [existing, empty, existing, empty]
    collection.data.insert.side_effect = lambda **kwargs: calls.append("insert")
    collection.data.delete_by_id.side_effect = lambda uuid: calls.append("delete")

    store, _ = _make_fake_store(collection)

    r1 = await store.add_memory_vector(memory_id=1, content="x", embedding=[0.1] * 4)
    r2 = await store.add_memory_vector(memory_id=1, content="x", embedding=[0.1] * 4)

    assert r1 is True and r2 is True
    assert collection.data.insert.call_count == 2, "两次 add 应各插入一次"
    assert collection.data.delete_by_id.call_count == 2, "两次 add 应各删除既有对象一次"
    # 顺序断言：每轮均为 delete -> insert，证明是「先删后插」而非直接 insert
    assert calls == ["delete", "insert", "delete", "insert"]


# --------------------------------------------------------------------------- #
# 4: add_memory_vector 空向量防御
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_add_memory_vector_rejects_empty_embedding():
    """空 embedding 防御：``add_memory_vector(embedding=None)`` 返回 False 且 insert 从未被调用。"""
    collection = MagicMock()
    store, _ = _make_fake_store(collection)

    result = await store.add_memory_vector(memory_id=1, content="x", embedding=None)

    assert result is False
    collection.data.insert.assert_not_called()
    collection.data.delete_by_id.assert_not_called()


# --------------------------------------------------------------------------- #
# 5: delete_by_memory_id 删干净 + 返回值语义
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_delete_by_memory_id_deletes_all_duplicates():
    """删干净：第一轮返回 2 个重复对象、第二轮返回 0 个 → 删除 2 次并返回 True。"""
    first = MagicMock()
    first.objects = [_fake_object("uuid-1"), _fake_object("uuid-2")]
    second = MagicMock()
    second.objects = []

    collection = MagicMock()
    collection.query.fetch_objects.side_effect = [first, second]

    store, _ = _make_fake_store(collection)

    result = await store.delete_by_memory_id(1, agent_id="default")

    assert result is True
    assert collection.data.delete_by_id.call_count == 2
    deleted_uuids = [c.args[0] for c in collection.data.delete_by_id.call_args_list]
    assert deleted_uuids == ["uuid-1", "uuid-2"]


@pytest.mark.asyncio
async def test_delete_by_memory_id_returns_false_when_nothing_found():
    """返回值语义：无匹配对象时返回 False，且不调用 delete_by_id。"""
    empty = MagicMock()
    empty.objects = []

    collection = MagicMock()
    collection.query.fetch_objects.side_effect = [empty]

    store, _ = _make_fake_store(collection)

    result = await store.delete_by_memory_id(999, agent_id="default")

    assert result is False
    collection.data.delete_by_id.assert_not_called()