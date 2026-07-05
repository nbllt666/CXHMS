"""ContextManager 单元测试。

覆盖修复点：
    - C3: 增量持久化（``_persist`` 只标记 dirty，后台 ``_flush_loop`` 周期性落盘）

设计原则：
    - 用 ``tmp_path`` 隔离 ``_context_dir``，不污染 ``data/context/``
    - 实例化后用 monkeypatch 替换 ``_context_dir`` 并清空 ``_store``，避免加载
      真实 ``data/context/`` 残留
    - 测试 dirty 标记、flush 行为、shutdown 最终落盘
    - 性能断言：单条 ``add_message_async`` < 5ms（仅内存更新，无磁盘 I/O）
"""

import json
import os
import time

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def context_manager(tmp_path):
    """提供隔离的 ContextManager 实例（_context_dir 指向 tmp_path）。

    实例化后替换 ``_context_dir`` 为 tmp_path 下的子目录，清空 ``_store`` 与
    dirty 标记，避免加载真实 ``data/context/`` 残留。
    """
    from backend.core.context.manager import ContextManager

    mgr = ContextManager()

    # 替换 _context_dir 到 tmp_path，清空已加载的 _store 与 dirty 标记
    ctx_dir = os.path.join(str(tmp_path), "context")
    os.makedirs(ctx_dir, exist_ok=True)
    mgr._context_dir = ctx_dir
    with mgr._lock:
        mgr._store.clear()
        mgr._dirty.clear()
        mgr._dirty_msg_count.clear()

    yield mgr

    # teardown：停止后台 flush 线程
    try:
        mgr.shutdown()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# C3: 增量持久化——_persist 只标记 dirty，不立即写盘
# --------------------------------------------------------------------------- #


def test_c3_add_message_marks_dirty_not_write_disk(context_manager, tmp_path):
    """C3: add_message 后 _dirty 包含 session_id，但磁盘文件未立即更新。

    回归断言：修复前 ``_persist`` 对每条消息全量重写 session JSON；
    修复后 ``_persist`` 仅 ``_mark_dirty``，落盘由后台 ``_flush_loop`` 周期性完成。
    """
    sid = context_manager.create_session(title="C3 dirty 测试")
    msg_id = context_manager.add_message(sid, "user", "第一条消息")

    assert msg_id  # 消息已追加到内存
    # _dirty 集合包含该 session_id
    assert sid in context_manager._dirty
    # _dirty_msg_count 记录该 session 的待 flush 消息数
    assert context_manager._dirty_msg_count.get(sid, 0) >= 1


def test_c3_flush_writes_dirty_sessions_to_disk(context_manager, tmp_path):
    """C3: flush() 后脏 session 落盘，_dirty 清空，磁盘文件含最新消息。

    回归断言：``flush`` 锁内取快照、锁外写盘；写盘后 ``_dirty`` 清空，
    ``_dirty_msg_count`` 清空，session JSON 文件含最新消息。
    """
    sid = context_manager.create_session(title="C3 flush 测试")
    context_manager.add_message(sid, "user", "待 flush 的消息")
    context_manager.add_message(sid, "assistant", "回复")

    # flush 前磁盘文件可能不存在或不含最新消息
    context_manager.flush()

    # flush 后 _dirty 清空
    assert sid not in context_manager._dirty
    assert sid not in context_manager._dirty_msg_count

    # 磁盘文件存在且含 2 条消息
    session_file = os.path.join(context_manager._context_dir, f"{sid}.json")
    assert os.path.exists(session_file)
    with open(session_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "待 flush 的消息"
    assert data["messages"][1]["content"] == "回复"


def test_c3_add_message_async_does_not_block_on_disk_io(context_manager):
    """C3: add_message_async 单条耗时 < 5ms（仅内存更新，无磁盘 I/O、无 to_thread）。

    回归断言：修复前 ``add_message_async`` 每条消息 ``asyncio.to_thread`` 调度写盘，
    长对话下每条消息持久化耗时随历史增长；修复后仅内存 set/dict 更新 + ``_mark_dirty``。
    """
    import asyncio

    sid = context_manager.create_session(title="C3 性能测试")

    async def _run():
        # 预先写入 100 条消息建立长对话基线
        for i in range(100):
            await context_manager.add_message_async(sid, "user", f"预热消息 {i}")

        # 测量第 101 条消息的耗时
        start = time.perf_counter()
        await context_manager.add_message_async(sid, "user", "性能测试消息")
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms

    elapsed_ms = asyncio.run(_run())
    # 单条 add_message_async 应 < 5ms（仅内存更新）
    assert elapsed_ms < 5.0, f"add_message_async 耗时 {elapsed_ms:.2f}ms > 5ms"


def test_c3_shutdown_flushes_pending_dirty(context_manager, tmp_path):
    """C3: shutdown 触发最终 flush，所有脏 session 落盘。

    回归断言：``shutdown`` 停止后台 ``_flush_loop`` 线程并强制 flush 所有脏 session，
    确保退出前数据落盘（避免丢失最近一个 flush 周期内的消息）。
    """
    sid = context_manager.create_session(title="C3 shutdown 测试")
    context_manager.add_message(sid, "user", "shutdown 前的消息")

    # 此时 _dirty 包含 sid（未 flush）
    assert sid in context_manager._dirty

    # shutdown 触发最终 flush
    context_manager.shutdown()

    # 磁盘文件存在且含消息
    session_file = os.path.join(context_manager._context_dir, f"{sid}.json")
    assert os.path.exists(session_file)
    with open(session_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "shutdown 前的消息"


def test_c3_persist_is_mark_dirty_not_full_write(context_manager, monkeypatch):
    """C3: ``_persist`` 仅调用 ``_mark_dirty``，不调用 ``_atomic_write``。

    回归断言：修复前 ``_persist`` 调 ``_atomic_write`` 全量重写；修复后调
    ``_mark_dirty``。用 monkeypatch 监控 ``_atomic_write`` 调用次数。
    """
    atomic_write_calls = []
    original_atomic_write = context_manager._atomic_write

    def spy_atomic_write(session_id, data):
        atomic_write_calls.append(session_id)
        return original_atomic_write(session_id, data)

    monkeypatch.setattr(context_manager, "_atomic_write", spy_atomic_write)

    sid = context_manager.create_session(title="C3 _persist 测试")
    # create_session 内部调 _persist（即 _mark_dirty），不应触发 _atomic_write
    context_manager.add_message(sid, "user", "消息 1")
    context_manager.add_message(sid, "user", "消息 2")

    # _persist 路径不触发 _atomic_write（仅标记 dirty）
    assert len(atomic_write_calls) == 0

    # 显式 flush 才触发 _atomic_write
    context_manager.flush()
    assert len(atomic_write_calls) >= 1
    assert sid in atomic_write_calls


# --------------------------------------------------------------------------- #
# 长对话持久化开销
# --------------------------------------------------------------------------- #


def test_c3_long_conversation_persist_under_threshold(context_manager):
    """C3: 长对话（>100 轮）每条消息持久化 < 5ms（C3 验收口径）。

    回归断言：spec C3 验收标准——"长对话（>100 轮）每条消息持久化 < 5ms"。
    """
    import asyncio

    sid = context_manager.create_session(title="长对话测试")

    async def _run():
        elapsed = []
        for i in range(150):
            start = time.perf_counter()
            await context_manager.add_message_async(sid, "user", f"消息 {i}")
            elapsed.append((time.perf_counter() - start) * 1000)
        return elapsed

    elapsed = asyncio.run(_run())
    # 所有消息持久化耗时均 < 5ms
    max_ms = max(elapsed)
    avg_ms = sum(elapsed) / len(elapsed)
    assert max_ms < 5.0, f"最大耗时 {max_ms:.2f}ms > 5ms"
    assert avg_ms < 2.0, f"平均耗时 {avg_ms:.2f}ms > 2ms"
