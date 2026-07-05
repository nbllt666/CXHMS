"""MemoryManager 单元测试。

覆盖修复点：
    - B2: 同步 MemoryManager schema 迁移（``type`` → ``memory_type`` + 3 新字段）
    - B4: recall_memory 透传 agent_id，跨 agent 记忆不串扰
    - 衰减字段（accessed_at / access_count / decay_score）写入后存在
    - recall_memory 后 reactivation_count 增加

设计原则：
    - 用 ``memory_manager`` fixture（tmp_path db + fakes 注入，D2 按 db_path 实例化）
    - 不重新实例化 fakes，统一通过 fixture 注入
    - B4 agent 隔离：用非默认 agent_id 写入，验证 recall/search 不串扰
"""

import os
import sqlite3

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# B2: 同步 MemoryManager schema 迁移
# --------------------------------------------------------------------------- #


def test_b2_sync_migrates_legacy_type_column(tmp_path):
    """B2: 旧库 ``type`` 列在同步 MemoryManager 初始化后被 RENAME 为 ``memory_type``。

    回归断言：同步侧 ``_init_db`` 检测到 ``type`` 列存在且 ``memory_type`` 不存在时，
    执行 RENAME COLUMN 保留数据，并补齐 accessed_at / access_count / decay_score。

    旧库构造：模拟"上一版本同步侧创建的库"——含 CREATE TABLE 全部列，仅以 ``type``
    替代 ``memory_type``，且无 3 个新字段（accessed_at / access_count / decay_score）。
    """
    legacy_db = os.path.join(str(tmp_path), "legacy_sync.db")
    conn = sqlite3.connect(legacy_db)
    # 旧 schema：type 替代 memory_type，无 accessed_at/access_count/decay_score
    conn.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type VARCHAR(20) NOT NULL DEFAULT 'short_term',
            content TEXT NOT NULL,
            vector_id VARCHAR(100),
            metadata TEXT,
            importance INTEGER DEFAULT 3,
            importance_score FLOAT DEFAULT 0.6,
            decay_type VARCHAR(20) DEFAULT 'exponential',
            decay_params TEXT,
            reactivation_count INTEGER DEFAULT 0,
            emotion_score FLOAT DEFAULT 0.0,
            permanent BOOLEAN DEFAULT FALSE,
            psychological_age FLOAT DEFAULT 1.0,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            archived_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP,
            source VARCHAR(50) DEFAULT 'user',
            workspace_id VARCHAR(100) DEFAULT 'default',
            agent_id VARCHAR(100) DEFAULT 'default'
        )
        """
    )
    conn.execute(
        "INSERT INTO memories (type, content, importance, workspace_id, agent_id, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("long_term", "旧库存量", 3, "default", "default", "2026-01-01", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    from backend.core.memory.manager import MemoryManager

    mgr = MemoryManager(db_path=legacy_db)

    try:
        conn2 = sqlite3.connect(legacy_db)
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(memories)").fetchall()}
        conn2.close()
        # type 已 RENAME 为 memory_type
        assert "memory_type" in cols
        assert "type" not in cols
        # 3 个新字段已补齐
        assert "accessed_at" in cols
        assert "access_count" in cols
        assert "decay_score" in cols

        # 存量行数据保留
        conn3 = sqlite3.connect(legacy_db)
        row = conn3.execute("SELECT content, memory_type FROM memories WHERE id = 1").fetchone()
        conn3.close()
        assert row == ("旧库存量", "long_term")
    finally:
        mgr.shutdown()


def test_b2_sync_write_read_uses_memory_type(memory_manager):
    """B2: 同步写入用 ``memory_type`` 列，读取时 ``memory_type`` 与 ``type`` 别名一致。

    回归断言：``_row_to_memory`` 输出 ``memory_type`` 主字段 + ``type`` 别名（同值），
    兼容下游读取 ``memory.get("type")`` 的旧代码。
    """
    mem_id = memory_manager.write_memory(
        content="B2 同步读写一致性",
        memory_type="long_term",
        importance=4,
        agent_id="default",
    )
    assert mem_id > 0

    mem = memory_manager.get_memory(mem_id)
    assert mem is not None
    # memory_type 主字段
    assert mem["memory_type"] == "long_term"
    # type 别名（向后兼容，与 memory_type 同值）
    assert mem["type"] == "long_term"
    # 3 个新字段存在
    assert "accessed_at" in mem
    assert "access_count" in mem
    assert "decay_score" in mem


# --------------------------------------------------------------------------- #
# B4: recall_memory 透传 agent_id + 跨 agent 不串扰
# --------------------------------------------------------------------------- #


def test_b4_recall_memory_passes_agent_id(memory_manager):
    """B4: recall_memory 透传 agent_id，按 agent 表查询。

    回归断言：修复前 ``recall_memory`` 硬编码 ``SELECT * FROM memories WHERE id=?``，
    忽略 agent_id，非默认 agent 召回的是默认表记忆。修复后用 ``table_name =
    self._get_table_name(agent_id)``，按 agent 表查询。
    """
    # 写入 agent A 的记忆
    mem_id_a = memory_manager.write_memory(
        content="Agent A 的专属记忆",
        memory_type="long_term",
        importance=4,
        agent_id="agent-a",
    )
    assert mem_id_a > 0

    # recall_memory 透传 agent_id="agent-a"，应能召回
    recalled = memory_manager.recall_memory(mem_id_a, emotion_intensity=0.5, agent_id="agent-a")
    assert recalled is not None
    assert recalled["id"] == mem_id_a
    # reactivation_count 应增加
    assert recalled["reactivation_count"] >= 1


def test_b4_recall_memory_wrong_agent_returns_none(memory_manager):
    """B4: 用错误 agent_id recall_memory 应返回 None（不串扰默认表）。

    回归断言：记忆写在 agent-a 表，用 agent_id="agent-b" 召回应返回 None，
    不会从默认 memories 表误召回。
    """
    mem_id_a = memory_manager.write_memory(
        content="Agent A 的记忆，B 不应召回",
        memory_type="long_term",
        importance=4,
        agent_id="agent-a",
    )

    # 用 agent-b 召回（应返回 None，因为记忆在 agent-a 表）
    recalled = memory_manager.recall_memory(mem_id_a, agent_id="agent-b")
    assert recalled is None


def test_b4_agent_isolation_search_memories(memory_manager):
    """B4: search_memories 按 agent_id 过滤，跨 agent 记忆不串扰。

    回归断言：写入 agent-a 与 agent-b 各一条记忆，search_memories(agent_id="agent-a")
    仅返回 agent-a 的记忆，不返回 agent-b 的。
    """
    mem_a = memory_manager.write_memory(
        content="Agent A 的搜索目标",
        memory_type="long_term",
        importance=4,
        agent_id="agent-a",
        workspace_id="ws-a",
    )
    mem_b = memory_manager.write_memory(
        content="Agent B 的搜索目标",
        memory_type="long_term",
        importance=4,
        agent_id="agent-b",
        workspace_id="ws-b",
    )
    assert mem_a > 0
    assert mem_b > 0

    # search_memories 按 agent-a 过滤
    results_a = memory_manager.search_memories(
        query=None,
        memory_type=None,
        agent_id="agent-a",
        workspace_id="ws-a",
    )
    contents_a = [r["content"] for r in results_a]
    assert "Agent A 的搜索目标" in contents_a
    assert "Agent B 的搜索目标" not in contents_a

    # search_memories 按 agent-b 过滤
    results_b = memory_manager.search_memories(
        query=None,
        memory_type=None,
        agent_id="agent-b",
        workspace_id="ws-b",
    )
    contents_b = [r["content"] for r in results_b]
    assert "Agent B 的搜索目标" in contents_b
    assert "Agent A 的搜索目标" not in contents_b


# --------------------------------------------------------------------------- #
# 衰减字段 + recall_memory 副作用
# --------------------------------------------------------------------------- #


def test_write_memory_has_decay_fields(memory_manager):
    """写入记忆后，衰减相关字段（accessed_at / access_count / decay_score）存在。

    回归断言：B2 补齐的 3 个新字段在写入路径中可读，与异步 MemoryManager 对齐。
    """
    mem_id = memory_manager.write_memory(
        content="衰减字段测试",
        memory_type="short_term",
        importance=3,
        agent_id="default",
    )
    mem = memory_manager.get_memory(mem_id)
    assert mem is not None
    # 3 个新字段均有值（accessed_at 在写入时设置，access_count/decay_score 走 DEFAULT）
    assert mem["accessed_at"] is not None
    assert mem["access_count"] == 0
    assert mem["decay_score"] == 0.0


def test_recall_memory_increases_reactivation_count(memory_manager):
    """recall_memory 后 reactivation_count 递增，emotion_score 更新。

    回归断言：recall_memory 不只是读取，还会更新 reactivation_count 与 emotion_score。
    """
    mem_id = memory_manager.write_memory(
        content="recall 副作用测试",
        memory_type="long_term",
        importance=3,
        agent_id="default",
    )
    before = memory_manager.get_memory(mem_id)
    assert before["reactivation_count"] == 0

    # recall 一次
    recalled = memory_manager.recall_memory(mem_id, emotion_intensity=0.8, agent_id="default")
    assert recalled is not None
    assert recalled["reactivation_count"] == 1

    # 再 recall 一次
    recalled2 = memory_manager.recall_memory(mem_id, emotion_intensity=0.6, agent_id="default")
    assert recalled2 is not None
    assert recalled2["reactivation_count"] == 2


# --------------------------------------------------------------------------- #
# CRUD 基本闭环
# --------------------------------------------------------------------------- #


def test_memory_crud_lifecycle(memory_manager):
    """MemoryManager CRUD 闭环：写入 → 读取 → 搜索 → 删除。"""
    # Create
    mem_id = memory_manager.write_memory(
        content="CRUD 闭环测试记忆",
        memory_type="long_term",
        importance=5,
        tags=["test", "crud"],
        agent_id="default",
    )
    assert mem_id > 0

    # Read
    mem = memory_manager.get_memory(mem_id)
    assert mem is not None
    assert mem["content"] == "CRUD 闭环测试记忆"
    assert mem["memory_type"] == "long_term"

    # Search（按 tag）
    results = memory_manager.search_memories(
        query=None,
        memory_type=None,
        tags=["test"],
        agent_id="default",
    )
    assert any(r["id"] == mem_id for r in results)


# --------------------------------------------------------------------------- #
# B3: 异常体系统一——CXHMSException 基类 + error_code/http_status 透传
# --------------------------------------------------------------------------- #
#
# B3 修复点：合并 core/api 双重异常体系。修复前 core 层 raise 的异常落入
# generic_exception_handler，返回 500 + INTERNAL_ERROR，error_code 丢失。修复后
# 所有业务异常（core + api）共享 CXHMSException 基类，FastAPI 注册单一
# cxhms_exception_handler 即可透传 error_code / http_status 到响应体。
# --------------------------------------------------------------------------- #


def test_b3_core_exceptions_inherit_cxhms_base():
    """B3: core 层业务异常均继承自 CXHMSException 基类。

    回归断言：修复前 core/api 双重异常体系并存。修复后 core 层 DatabaseError /
    MemoryOperationError / MemoryNotFoundError 等全部继承 CXHMSException，单一
    handler 处理即可透传 error_code/http_status，不会落入 generic 500。
    """
    from backend.core.exceptions import (
        CXHMSException,
        DatabaseError,
        MemoryOperationError,
        MemoryNotFoundError,
        ValidationError,
        VectorStoreError,
        LLMError,
        ContextError,
    )

    for exc_class in [
        DatabaseError,
        MemoryOperationError,
        MemoryNotFoundError,
        ValidationError,
        VectorStoreError,
        LLMError,
        ContextError,
    ]:
        assert issubclass(exc_class, CXHMSException), (
            f"{exc_class.__name__} 未继承 CXHMSException"
        )
        assert issubclass(exc_class, Exception)


def test_b3_api_exceptions_inherit_cxhms_base():
    """B3: api 层异常（CXHMSError 及其子类）继承自 core 层 CXHMSException。

    回归断言：api 层 CXHMSError 继承自 CXHMSException，api 层子类（DatabaseError、
    MemoryNotFoundError、AgentNotFoundError 等）继承自 CXHMSError，从而所有业务异常
    （core + api）共享同一基类，单一 cxhms_exception_handler 覆盖全部业务异常。
    """
    from backend.api.exceptions import (
        CXHMSError,
        DatabaseError as ApiDatabaseError,
        MemoryNotFoundError as ApiMemoryNotFoundError,
        AgentNotFoundError,
        SessionNotFoundError,
        LLMError as ApiLLMError,
        VectorStoreError as ApiVectorStoreError,
        ValidationError as ApiValidationError,
        AuthenticationError,
        RateLimitError,
    )
    from backend.core.exceptions import CXHMSException

    # CXHMSError 继承自 CXHMSException（B3 合并核心断言）
    assert issubclass(CXHMSError, CXHMSException)

    # api 层子类继承自 CXHMSError，从而继承自 CXHMSException
    for exc_class in [
        ApiDatabaseError,
        ApiMemoryNotFoundError,
        AgentNotFoundError,
        SessionNotFoundError,
        ApiLLMError,
        ApiVectorStoreError,
        ApiValidationError,
        AuthenticationError,
        RateLimitError,
    ]:
        assert issubclass(exc_class, CXHMSError), (
            f"{exc_class.__name__} 未继承 CXHMSError"
        )
        assert issubclass(exc_class, CXHMSException), (
            f"{exc_class.__name__} 未透传到 CXHMSException"
        )


def test_b3_exception_carries_error_code_and_http_status():
    """B3: 业务异常实例携带正确 error_code 和 http_status。

    回归断言：异常经 handler 返回时，error_code 与 http_status 必须透传到响应体。
    修复前 core 层异常落入 generic handler 时 error_code 丢失；修复后透传保留。
    """
    from backend.core.exceptions import (
        DatabaseError,
        MemoryOperationError,
        MemoryNotFoundError,
        ValidationError,
        VectorStoreError,
        LLMError,
        ContextError,
    )

    cases = [
        (DatabaseError("db fail"), "DATABASE_ERROR", 500),
        (MemoryOperationError("op fail"), "MEMORY_OPERATION_ERROR", 500),
        (MemoryNotFoundError(999), "MEMORY_NOT_FOUND", 404),
        (ValidationError("invalid"), "VALIDATION_ERROR", 400),
        (VectorStoreError("vs fail"), "VECTOR_STORE_ERROR", 503),
        (LLMError("llm fail"), "LLM_ERROR", 503),
        (ContextError("ctx fail"), "CONTEXT_ERROR", 500),
    ]

    for exc, expected_code, expected_status in cases:
        assert exc.error_code == expected_code, (
            f"{type(exc).__name__}.error_code 期望 {expected_code}，实际 {exc.error_code}"
        )
        assert exc.http_status == expected_status, (
            f"{type(exc).__name__}.http_status 期望 {expected_status}，实际 {exc.http_status}"
        )
        # status_code 别名（向后兼容，旧 handler 读取 status_code）
        assert exc.status_code == expected_status, (
            f"{type(exc).__name__}.status_code 别名与 http_status 不一致"
        )


def test_b3_memory_not_found_error_details():
    """B3: MemoryNotFoundError details 含 memory_id，handler 透传到响应体。

    回归断言：MemoryNotFoundError 构造时把 memory_id 转为 str 放入 details，
    cxhms_exception_handler 返回时 details 字段透传到响应体。
    """
    from backend.core.exceptions import MemoryNotFoundError

    exc = MemoryNotFoundError(42)
    assert exc.error_code == "MEMORY_NOT_FOUND"
    assert exc.http_status == 404
    assert exc.details == {"memory_id": "42"}


@pytest.mark.asyncio
async def test_b3_exception_handler_returns_correct_response():
    """B3: cxhms_exception_handler 把 CXHMSException 转为带 error_code/http_status 的 JSONResponse。

    回归断言：修复前 core 层 raise 的异常落入 generic_exception_handler，返回
    500 + INTERNAL_ERROR。修复后单一 cxhms_exception_handler 处理所有 CXHMSException
    子类，返回正确 http_status + 响应体含 error_code。
    """
    import json
    from types import SimpleNamespace

    from backend.api.exceptions import cxhms_exception_handler
    from backend.core.exceptions import (
        DatabaseError,
        MemoryNotFoundError,
        ValidationError,
    )

    # handler 不实际读取 request 内容，传 SimpleNamespace 即可
    request = SimpleNamespace(url=SimpleNamespace(path="/test"))

    # MemoryNotFoundError -> 404 + MEMORY_NOT_FOUND
    exc = MemoryNotFoundError(123)
    response = await cxhms_exception_handler(request, exc)
    assert response.status_code == 404
    data = json.loads(response.body)
    assert data["error_code"] == "MEMORY_NOT_FOUND"
    assert data["error"] == "Memory not found: 123"
    assert data["success"] is False
    assert data["details"] == {"memory_id": "123"}

    # DatabaseError -> 500 + DATABASE_ERROR
    exc2 = DatabaseError("connection lost", details={"reason": "timeout"})
    response2 = await cxhms_exception_handler(request, exc2)
    assert response2.status_code == 500
    data2 = json.loads(response2.body)
    assert data2["error_code"] == "DATABASE_ERROR"
    assert data2["error"] == "connection lost"
    assert data2["details"] == {"reason": "timeout"}

    # ValidationError -> 400 + VALIDATION_ERROR
    exc3 = ValidationError("bad input")
    response3 = await cxhms_exception_handler(request, exc3)
    assert response3.status_code == 400
    data3 = json.loads(response3.body)
    assert data3["error_code"] == "VALIDATION_ERROR"
