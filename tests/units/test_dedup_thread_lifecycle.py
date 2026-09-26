"""后台去重线程与连接池关闭竞态修复的单元测试。

对应变更文档 ``20260926_模块1_修复后台去重线程与连接池关闭竞态.md``。
背景：``write_memory`` 会 fire-and-forget spawn ``DedupCheck`` 守护线程，该线程随后会经
``_get_connection()`` 使用「本线程自己的」sqlite 连接；而 ``shutdown()`` 会
``close_all_connections()`` 关闭并清空连接池。二者并发 → sqlite3 C 层 use-after-free
（表现为 pytest 偶发 STATUS_ACCESS_VIOLATION 原生崩溃，见 ``debug-pytest-teardown-segv.md``）。

本文件用**确定性断言**覆盖修复要点（不依赖复现那次概率性崩溃）：
    1. ``shutdown()`` 在关闭连接池**之前**等待在途去重线程
    2. ``_stop_event`` 已置位时 worker 不再发起数据库访问（早退）
    3. worker 结束后从登记表自我注销
"""

import sqlite3
import threading
import time
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_awaitable(value):
    """构造一个返回 value 的协程（供 _run_async_sync 消费）。"""

    async def _coro():
        return value

    return _coro()


def test_close_all_connections_skips_unfinished_worker_connections(memory_manager):
    """超时未结束的 worker：其连接必须被跳过关闭（避免并发 close → C 层 use-after-free）。"""
    mm = memory_manager
    release = threading.Event()
    worker_ready = threading.Event()
    captured = {}

    def _stuck_worker():
        # 让本线程在连接池中建立自己的连接（模拟 worker 正在使用 sqlite）
        conn = mm._get_connection()
        captured["ident"] = threading.get_ident()
        captured["conn"] = conn
        worker_ready.set()
        release.wait(10.0)

    worker = threading.Thread(target=_stuck_worker, daemon=True, name="DedupCheck")
    with mm._lock:
        mm._dedup_threads.add(worker)
    worker.start()
    assert worker_ready.wait(3.0), "worker 未能在超时内建立连接"

    try:
        still_alive = mm._join_dedup_threads(timeout=0.3)
        assert worker in still_alive, "卡住的 worker 应被报告为未结束"

        skip_ids = {t.ident for t in still_alive if t.ident is not None}
        mm.close_all_connections(skip_thread_ids=skip_ids)

        # 关键断言：worker 的连接仍在池中（未被关闭）；主线程自己的连接已被关闭
        with mm._lock:
            remaining = set(mm._connection_pool.keys())
        assert captured["ident"] in remaining, (
            "未结束 worker 的连接不应被关闭（否则并发 close 会导致原生崩溃）"
        )
        # 关闭连接后再次使用该连接应当仍可用（未被 close）
        captured["conn"].execute("SELECT 1").fetchone()
    finally:
        release.set()
        worker.join(timeout=2.0)


def test_shutdown_waits_for_inflight_dedup_worker(memory_manager):
    """shutdown() 必须先等在途去重线程结束，再关闭连接池（顺序断言）。"""
    mm = memory_manager
    worker_end = {}
    order = {}

    def _slow_worker():
        time.sleep(0.3)
        worker_end["ts"] = time.monotonic()

    worker = threading.Thread(target=_slow_worker, daemon=True, name="DedupCheck")
    with mm._lock:
        mm._dedup_threads.add(worker)
    worker.start()

    original_close = mm.close_all_connections

    def _recording_close(skip_thread_ids=None):
        order["close_ts"] = time.monotonic()
        order["skip_ids"] = skip_thread_ids
        return original_close(skip_thread_ids=skip_thread_ids)

    mm.close_all_connections = _recording_close
    mm.shutdown()

    assert "close_ts" in order, "close_all_connections 未被调用"
    assert "ts" in worker_end, "worker 未执行完成"
    assert order["close_ts"] >= worker_end["ts"], (
        f"shutdown 未等待在途去重线程：close at {order['close_ts']}, "
        f"worker end at {worker_end['ts']}"
    )
    assert worker not in mm._dedup_threads, "worker 结束后应已从登记表注销"


def test_dedup_worker_skips_when_shutting_down(memory_manager):
    """_stop_event 已置位（正在关闭）时，worker 不得再发起数据库访问。"""
    mm = memory_manager
    spy = MagicMock(side_effect=lambda **kwargs: _make_awaitable(None))
    mm.deduplication_engine = MagicMock()
    mm.deduplication_engine.find_duplicate_memory = spy

    mm._stop_event.set()
    mm._start_async_dedup_check(1, "关闭中不应去重", workspace_id="default", agent_id="default")

    # 等待可能被 spawn 的线程结束（早退分支应极快返回）
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        with mm._lock:
            alive = [t for t in mm._dedup_threads if t.is_alive()]
        if not alive:
            break
        time.sleep(0.02)

    assert spy.call_count == 0, "关闭流程已开始时 worker 不应访问数据库"
    with mm._lock:
        remaining = set(mm._dedup_threads)
    assert remaining == set(), (
        f"早退分支也必须自我注销（否则登记表泄漏），实际残留 {remaining}"
    )


def test_join_dedup_threads_continues_after_timeout(memory_manager):
    """worker 卡住时，等待必须有界：超时后仍继续关闭流程（不无限等待）。"""
    mm = memory_manager
    release = threading.Event()

    def _stuck_worker():
        release.wait(10.0)

    worker = threading.Thread(target=_stuck_worker, daemon=True, name="DedupCheck")
    with mm._lock:
        mm._dedup_threads.add(worker)
    worker.start()

    try:
        start = time.monotonic()
        mm._join_dedup_threads(timeout=0.3)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"等待应有界，实际耗时 {elapsed:.2f}s"
        with mm._lock:
            assert worker in mm._dedup_threads, "卡住的 worker 应仍在登记表中（供告警）"
    finally:
        # 收尾：释放卡住的线程，避免影响其他用例
        release.set()
        worker.join(timeout=2.0)


def test_dedup_worker_self_deregisters(memory_manager):
    """正常路径：worker 完成后应从登记表移除（登记表不泄漏）。"""
    mm = memory_manager
    mm.deduplication_engine = MagicMock()
    mm.deduplication_engine.find_duplicate_memory = MagicMock(
        side_effect=lambda **kwargs: _make_awaitable(None)
    )

    mm._start_async_dedup_check(2, "正常去重检查内容", workspace_id="default", agent_id="default")

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with mm._lock:
            alive = [t for t in mm._dedup_threads if t.is_alive()]
        if not alive:
            break
        time.sleep(0.02)

    with mm._lock:
        remaining = set(mm._dedup_threads)
    assert remaining == set(), f"worker 结束后登记表应清空，实际残留 {remaining}"


def test_close_all_connections_default_clears_pool(memory_manager):
    """默认路径（``skip_thread_ids=None``）：连接池被关闭并清空。

    回归守护：为修竞态新增的「跳过」语义**不得改变默认行为**——
    不传参时仍应关闭全部连接并从池中移除（否则会掩盖连接泄漏）。
    """
    mm = memory_manager
    conn = mm._get_connection()
    with mm._lock:
        assert threading.get_ident() in mm._connection_pool, (
            "前置条件：本线程应在池中持有连接"
        )

    mm.close_all_connections()  # 默认路径：不传 skip_thread_ids

    with mm._lock:
        remaining = set(mm._connection_pool.keys())
    assert remaining == set(), f"默认路径应清空连接池，实际残留 {remaining}"
    # 该连接确实已被关闭（不是"只从池中摘除、连接仍打开"）
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1").fetchone()
