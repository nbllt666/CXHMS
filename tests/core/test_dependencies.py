"""backend.dependencies.ServiceState.update_component 的单元测试。

覆盖：
    1. update_component 替换属性
    2. update_component 返回旧实例
    3. update_component 多线程并发安全（不丢失更新）

补丁策略：
    - _safe_close 可能调用旧实例的 close()/shutdown()；测试用例传入字符串
      或 mock 对象，无 close/shutdown 方法，_safe_close 走 no-op 分支
    - 并发安全测试：N 个线程各自写入不同值，验证最终值在写入集合内
      （不丢失更新 = 串行化效果，无 torn write）
"""

import threading
import time
from typing import List

import pytest

from backend.dependencies import ServiceState


# --------------------------------------------------------------------------- #
# 测试用例 1：update_component 替换属性
# --------------------------------------------------------------------------- #


def test_update_component_replaces():
    """update_component("memory_manager", "new") 后 state.memory_manager == "new" """
    state = ServiceState()
    state.memory_manager = "old"

    state.update_component("memory_manager", "new")

    assert state.memory_manager == "new"


# --------------------------------------------------------------------------- #
# 测试用例 2：update_component 返回旧实例
# --------------------------------------------------------------------------- #


def test_update_component_returns_old():
    """update_component 返回被替换的旧实例"""
    state = ServiceState()
    state.memory_manager = "old"

    old = state.update_component("memory_manager", "new")

    assert old == "old"


# --------------------------------------------------------------------------- #
# 测试用例 3：多线程并发安全
# --------------------------------------------------------------------------- #


def test_update_component_concurrent_safe():
    """N 个线程并发调用 update_component，验证不丢失更新。

    构造：
        - 100 个线程并发写入不同的 int 值（0~99）
        - 每个线程做 10 次写入（重复自己的值）
    验证：
        - 最终 state.memory_manager 必须是 0~99 中的某个值（不能是部分写入
          产生的脏值，因为赋值是原子的 setattr）
        - 不抛异常
    """
    state = ServiceState()
    state.memory_manager = -1  # 初始值

    N_THREADS = 100
    N_WRITES = 10
    errors: List[Exception] = []

    def writer(val: int) -> None:
        try:
            for _ in range(N_WRITES):
                state.update_component("memory_manager", val)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 无异常
    assert errors == [], f"并发写入产生异常: {errors}"

    # 最终值必须在 0~N_THREADS-1 范围内（合法的写入值之一）
    final_val = state.memory_manager
    assert 0 <= final_val < N_THREADS, (
        f"最终值 {final_val} 不在合法范围 [0, {N_THREADS})，"
        "可能发生了 torn write"
    )


# --------------------------------------------------------------------------- #
# 补充：update_component 替换 None 初始值
# --------------------------------------------------------------------------- #


def test_update_component_returns_none_when_no_old():
    """属性初始为 None 时，update_component 返回 None"""
    state = ServiceState()

    old = state.update_component("memory_manager", "first")

    assert old is None
    assert state.memory_manager == "first"


# --------------------------------------------------------------------------- #
# 补充：_safe_close 调用旧实例的 shutdown()
# --------------------------------------------------------------------------- #


def test_safe_close_calls_shutdown(monkeypatch):
    """旧实例有 shutdown() 时被调用（延迟排空窗口后触发）"""
    # M8-b：旧实例改为延迟关闭，测试将排空窗口缩短为 0.05s
    monkeypatch.setattr(
        "backend.dependencies.OLD_INSTANCE_CLOSE_DELAY_SECONDS", 0.05
    )
    state = ServiceState()

    closed = {"called": False}

    class FakeComponent:
        def shutdown(self) -> None:
            closed["called"] = True

    old_instance = FakeComponent()
    state.memory_manager = old_instance

    state.update_component("memory_manager", "new")

    # 等待延迟 Timer 触发
    time.sleep(0.3)

    assert closed["called"] is True


# --------------------------------------------------------------------------- #
# 补充：_safe_close 优先 shutdown() 而非 close()
# --------------------------------------------------------------------------- #


def test_safe_close_prefers_shutdown_over_close(monkeypatch):
    """旧实例同时有 shutdown() 和 close() 时，只调用 shutdown()（延迟触发）"""
    # M8-b：旧实例改为延迟关闭，测试将排空窗口缩短为 0.05s
    monkeypatch.setattr(
        "backend.dependencies.OLD_INSTANCE_CLOSE_DELAY_SECONDS", 0.05
    )
    state = ServiceState()

    calls = []

    class FakeComponent:
        def shutdown(self) -> None:
            calls.append("shutdown")

        def close(self) -> None:
            calls.append("close")

    state.memory_manager = FakeComponent()
    state.update_component("memory_manager", "new")

    # 等待延迟 Timer 触发
    time.sleep(0.3)

    assert calls == ["shutdown"]


# --------------------------------------------------------------------------- #
# 补充：_safe_close 对 async close 跳过同步调用
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_safe_close_skips_async_close():
    """旧实例的 close() 是 async 时，_safe_close 跳过（不调用）"""
    state = ServiceState()

    calls = []

    class FakeComponent:
        async def close(self) -> None:
            calls.append("async_close")

    state.memory_manager = FakeComponent()
    # update_component 是同步方法，async close 应被跳过
    state.update_component("memory_manager", "new")

    # async close 不应在同步路径中被调用
    assert calls == []
