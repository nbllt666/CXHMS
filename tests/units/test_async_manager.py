"""AsyncMemoryManager 单元测试。

覆盖修复点：
    - B1: AsyncMemoryManager 未初始化（``_pool`` 永远为 None）
    - B2: 同步/异步 MemoryManager schema 一致性（``memory_type`` 列名统一 + 旧库迁移）

设计原则：
    - 直接实例化 ``AsyncMemoryManager``，用临时 db_path 隔离，不依赖 sim_app
      （sim_app 的模拟模式显式 ``async_memory_manager = None``，故 B1 的运行时
      证据由本文件直接实例化 + ``initialize()`` 验证）。
    - B2 一致性：用 ``memory_manager`` fixture（同步侧）写入，再用独立
      ``AsyncMemoryManager`` 实例（异步侧）读取同一 db 文件，验证字段口径一致。
    - B2 旧库迁移：手工构造仅有 ``type`` 列的旧库，验证 ``_migrate_memories_schema``
      将 ``type`` RENAME 为 ``memory_type`` 并补齐 3 个新字段。
"""

import os
import sqlite3

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# B1: AsyncMemoryManager initialize() 后 _pool is not None
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b1_initialize_sets_pool(tmp_path):
    """B1: initialize() 后 _pool 不为 None，_initialized 为 True。

    回归断言：修复前 lifespan 未调 ``initialize()``，``_pool`` 永远为 None，
    任何经 ``get_async_memory_manager()`` 的调用抛 AttributeError。
    """
    from backend.core.memory.async_manager import AsyncMemoryManager

    db_path = os.path.join(str(tmp_path), "async_memories.db")
    mgr = AsyncMemoryManager(db_path=db_path)

    # 修复前：未调 initialize() 时 _pool 为 None
    assert mgr._pool is None
    assert mgr._initialized is False

    await mgr.initialize()

    # 修复后：initialize() 建立 _pool
    assert mgr._pool is not None
    assert mgr._initialized is True

    await mgr.close()


@pytest.mark.asyncio
async def test_b1_factory_get_async_memory_manager_initialized(tmp_path):
    """B1: get_async_memory_manager() 工厂返回已初始化实例，不抛 AttributeError。"""
    from backend.core.memory.async_manager import (
        AsyncMemoryManager,
        get_async_memory_manager,
    )

    db_path = os.path.join(str(tmp_path), "factory_memories.db")
    mgr = await get_async_memory_manager(db_path=db_path)

    try:
        assert isinstance(mgr, AsyncMemoryManager)
        assert mgr._pool is not None
        assert mgr._initialized is True
    finally:
        await mgr.close()


@pytest.mark.asyncio
async def test_b1_write_memory_does_not_raise_attribute_error(tmp_path):
    """B1: initialize() 后 write_memory 不抛 AttributeError（_pool 可用）。

    回归断言：修复前未 initialize() 时 ``write_memory`` 因 ``self._pool`` 为 None
    抛 AttributeError；修复后 initialize() 在 lifespan 中被调用，本测试直接
    复现 initialize() 后写入路径的正常行为。
    """
    from backend.core.memory.async_manager import AsyncMemoryManager

    db_path = os.path.join(str(tmp_path), "write_memories.db")
    mgr = AsyncMemoryManager(db_path=db_path)
    await mgr.initialize()

    try:
        memory_id = await mgr.write_memory(
            content="B1 回归：异步写入不应抛 AttributeError",
            memory_type="short_term",
            importance=3,
            agent_id="default",
        )
        assert isinstance(memory_id, int)
        assert memory_id > 0
    finally:
        await mgr.close()


# --------------------------------------------------------------------------- #
# B2: 同步/异步 schema 一致性 + 旧库迁移
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b2_async_reads_sync_written_memory(tmp_path, memory_manager):
    """B2: 同步 MemoryManager 写入后，异步 AsyncMemoryManager 读取字段一致。

    共享同一 db 文件——同步侧用 ``memory_type`` 列写入，异步侧 ``_migrate_memories_schema``
    检测到 schema 已统一后为 no-op，读取时字段名 ``memory_type`` 一致，
    不再出现列名错配。
    """
    from backend.core.memory.async_manager import AsyncMemoryManager

    # 同步侧写入一条记忆（用 memory_manager fixture 的独立 db）
    sync_id = memory_manager.write_memory(
        content="B2 一致性：同步写入",
        memory_type="long_term",
        importance=4,
        agent_id="default",
        workspace_id="default",
    )
    assert sync_id > 0

    # 异步侧打开同一 db 文件
    async_mgr = AsyncMemoryManager(db_path=str(memory_manager.db_path))
    await async_mgr.initialize()

    try:
        # 异步侧能读到同步写入的记忆（同 id）
        mem = await async_mgr.get_memory(sync_id)
        assert mem is not None
        # 字段口径一致：异步侧读 memory_type（而非旧 type 列）
        assert mem.get("memory_type") == "long_term"
        # B2 补齐的 3 个新字段在异步侧也存在
        assert "accessed_at" in mem
        assert "access_count" in mem
        assert "decay_score" in mem
    finally:
        await async_mgr.close()


@pytest.mark.asyncio
async def test_b2_async_migrates_legacy_type_column(tmp_path):
    """B2: 旧库仅有 ``type`` 列时，``_migrate_memories_schema`` RENAME 为 ``memory_type``。

    回归断言：旧库由更早版本创建时 memories 表用 ``type`` 列；异步侧 initialize()
    调 ``_migrate_memories_schema`` 将 ``type`` RENAME 为 ``memory_type``（保留数据），
    并补齐 accessed_at / access_count / decay_score。

    本测试聚焦于 schema 迁移本身（列名变更 + 新字段补齐），不调用 ``get_memory``
    完整路径——``_row_to_memory`` 依赖同步侧完整 schema（tags/decay_type 等），
    而旧库迁移只负责 type→memory_type 与 3 个新字段，不补齐其他列。完整的读写
    一致性由 ``test_b2_async_reads_sync_written_memory`` 覆盖。
    """
    legacy_db = os.path.join(str(tmp_path), "legacy_memories.db")
    # 手工构造旧 schema：仅有 type 列、无 memory_type / accessed_at / access_count / decay_score
    conn = sqlite3.connect(legacy_db)
    conn.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'short_term',
            importance INTEGER DEFAULT 3,
            workspace_id TEXT DEFAULT 'default',
            agent_id TEXT DEFAULT 'default',
            created_at TEXT,
            updated_at TEXT,
            is_deleted INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT INTO memories (content, type, importance, workspace_id, agent_id, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("旧库存量行", "long_term", 3, "default", "default", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    from backend.core.memory.async_manager import AsyncMemoryManager

    mgr = AsyncMemoryManager(db_path=legacy_db)
    await mgr.initialize()

    try:
        # 迁移后 type 列已被 RENAME 为 memory_type
        conn2 = sqlite3.connect(legacy_db)
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(memories)").fetchall()}
        conn2.close()
        assert "memory_type" in cols
        assert "type" not in cols
        # 补齐的 3 个新字段
        assert "accessed_at" in cols
        assert "access_count" in cols
        assert "decay_score" in cols

        # 存量行数据保留（直接 SQL 验证，不经过 _row_to_memory）
        conn3 = sqlite3.connect(legacy_db)
        row = conn3.execute(
            "SELECT content, memory_type FROM memories WHERE id = 1"
        ).fetchone()
        conn3.close()
        assert row is not None
        assert row[0] == "旧库存量行"
        assert row[1] == "long_term"
    finally:
        await mgr.close()


@pytest.mark.asyncio
async def test_b2_sync_async_write_consistency(tmp_path):
    """B2: 同步先建表 + 异步后写入共存于同一 db，互相读取字段一致。

    场景：同步侧先创建 db（含完整 schema 含 decay_type 等列），异步侧再打开
    （``_migrate_memories_schema`` 检测到 memory_type 已存在为 no-op），双方互写互读。

    说明：异步侧 INSERT 仅使用 memory_type 等少数列（其 CREATE TABLE 的子集），
    同步侧 CREATE TABLE 包含完整列集；故同步侧先建表时，异步侧 INSERT 与读取
    均可正常进行。验证列名统一后双方互操作无 SQL 错误。
    """
    from backend.core.memory.async_manager import AsyncMemoryManager
    from backend.core.memory.manager import MemoryManager

    db_path = os.path.join(str(tmp_path), "shared_memories.db")

    # 同步侧先建表 + 写入一条
    sync_mgr = MemoryManager(db_path=db_path)
    sync_id = sync_mgr.write_memory(
        content="同步侧写入",
        memory_type="long_term",
        importance=4,
        agent_id="default",
    )
    assert sync_id > 0

    # 异步侧打开同一 db（迁移为 no-op，因同步侧已创建 memory_type 列）
    async_mgr = AsyncMemoryManager(db_path=db_path)
    await async_mgr.initialize()

    try:
        # 异步侧再写一条
        async_id = await async_mgr.write_memory(
            content="异步侧写入",
            memory_type="short_term",
            importance=3,
            agent_id="default",
        )
        assert async_id > 0

        # 异步侧读取同步侧写入的（字段口径一致：memory_type）
        sync_mem_async_side = await async_mgr.get_memory(sync_id)
        assert sync_mem_async_side is not None
        assert sync_mem_async_side.get("memory_type") == "long_term"

        # 同步侧读取异步侧写入的
        async_mem_sync_side = sync_mgr.get_memory(async_id)
        assert async_mem_sync_side is not None
        assert async_mem_sync_side.get("memory_type") == "short_term"
    finally:
        await async_mgr.close()
        sync_mgr.shutdown()
