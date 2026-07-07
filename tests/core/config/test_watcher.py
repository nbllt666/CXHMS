"""backend.core.config.watcher 的单元测试。

覆盖 ConfigWatcher 在以下场景下的行为：
    1. start/stop 不抛异常，状态正确切换
    2. 修改文件后防抖触发 callback
    3. 连续多次修改文件，防抖后只触发一次 callback
    4. stop 后修改文件，callback 不被调用
    5. callback 抛异常时 watcher 不崩溃

测试策略：
    - 使用 tmp_path 隔离文件系统，不依赖真实 config/default.yaml
    - watchdog 文件事件在不同 OS 上有延迟，修改文件后 sleep 0.5s 等待事件传播
    - 防抖时间为 5 秒，等待 6.5 秒确保计时器触发
    - 测试较慢（约 6-10 秒/用例），标记 slow 并设置 30 秒超时
    - watchdog 未安装时整个模块跳过（pytest.importorskip）
"""

import time
from pathlib import Path
from typing import List

import pytest

# watchdog 未安装时跳过整个模块
pytest.importorskip("watchdog")

from backend.core.config.watcher import ConfigWatcher


# --------------------------------------------------------------------------- #
# 辅助函数与 fixture
# --------------------------------------------------------------------------- #


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """创建临时配置文件。

    在 watcher 启动前创建文件，避免 on_created 事件干扰测试。
    返回文件路径（绝对路径）。
    """
    p = tmp_path / "config.yaml"
    p.write_text("key: initial\n", encoding="utf-8")
    return p


def _modify_file(path: Path) -> None:
    """修改文件内容以触发 on_modified 事件。

    追加不同内容确保文件系统检测到变化。
    修改后等待 0.5s 让事件传播（watchdog 在不同 OS 上有延迟）。
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"# modified at {time.time()}\n")
    # 等待事件传播
    time.sleep(0.5)


# --------------------------------------------------------------------------- #
# 测试用例 1：start/stop 不抛异常
# --------------------------------------------------------------------------- #


@pytest.mark.slow
@pytest.mark.timeout(30)
def test_watcher_start_stop(config_file: Path):
    """start() 然后 stop() 不抛异常，_started 状态正确切换。"""
    calls: List[int] = []
    watcher = ConfigWatcher(str(config_file), lambda: calls.append(1))
    try:
        watcher.start()
        assert watcher._started is True
    finally:
        watcher.stop()
    assert watcher._started is False


# --------------------------------------------------------------------------- #
# 测试用例 2：修改文件后防抖触发 callback
# --------------------------------------------------------------------------- #


@pytest.mark.slow
@pytest.mark.timeout(30)
def test_watcher_callback_triggered(config_file: Path):
    """修改文件后等待防抖（5s），callback 应被调用至少 1 次。"""
    calls: List[int] = []
    watcher = ConfigWatcher(str(config_file), lambda: calls.append(1))
    try:
        watcher.start()
        # 等待 observer 启动就绪
        time.sleep(0.5)
        # 修改文件
        _modify_file(config_file)
        # 等待事件传播 + 防抖（5s）+ 缓冲
        time.sleep(6.5)
        assert len(calls) >= 1, f"callback 应被调用至少 1 次，实际 {len(calls)} 次"
    finally:
        watcher.stop()


# --------------------------------------------------------------------------- #
# 测试用例 3：连续多次修改，防抖后只触发 1 次
# --------------------------------------------------------------------------- #


@pytest.mark.slow
@pytest.mark.timeout(30)
def test_watcher_debounce(config_file: Path):
    """连续 3 次修改（间隔 1 秒），防抖后 callback 只被调用 1 次。"""
    calls: List[int] = []
    watcher = ConfigWatcher(str(config_file), lambda: calls.append(1))
    try:
        watcher.start()
        # 等待 observer 启动就绪
        time.sleep(0.5)
        # 连续 3 次修改，间隔 1 秒
        for i in range(3):
            _modify_file(config_file)
            time.sleep(1.0)
        # 等待防抖结束（最后一次事件后 5s）+ 缓冲
        time.sleep(6.5)
        assert len(calls) == 1, f"防抖后应只触发 1 次，实际 {len(calls)} 次"
    finally:
        watcher.stop()


# --------------------------------------------------------------------------- #
# 测试用例 4：stop 后修改文件不触发 callback
# --------------------------------------------------------------------------- #


@pytest.mark.slow
@pytest.mark.timeout(30)
def test_watcher_no_callback_after_stop(config_file: Path):
    """stop 后修改文件，callback 不被调用。"""
    calls: List[int] = []
    watcher = ConfigWatcher(str(config_file), lambda: calls.append(1))
    watcher.start()
    time.sleep(0.5)
    watcher.stop()
    # stop 后修改文件
    _modify_file(config_file)
    # 等待足够长时间（超过防抖）确认不触发
    time.sleep(6.5)
    assert len(calls) == 0, f"stop 后不应触发 callback，实际 {len(calls)} 次"


# --------------------------------------------------------------------------- #
# 测试用例 5：callback 抛异常时 watcher 不崩溃
# --------------------------------------------------------------------------- #


@pytest.mark.slow
@pytest.mark.timeout(30)
def test_watcher_callback_exception_doesnt_crash(config_file: Path):
    """callback 抛异常，watcher 不崩溃，仍保持启动状态。"""
    call_count = [0]

    def raising_callback() -> None:
        call_count[0] += 1
        raise RuntimeError("intentional test error")

    watcher = ConfigWatcher(str(config_file), raising_callback)
    try:
        watcher.start()
        time.sleep(0.5)
        _modify_file(config_file)
        # 等待防抖 + 缓冲
        time.sleep(6.5)
        # callback 被调用过（异常被 _fire_callback 捕获）
        assert call_count[0] >= 1, "callback 应被调用"
        # watcher 仍处于启动状态（未崩溃）
        assert watcher._started is True, "watcher 不应因 callback 异常而崩溃"
    finally:
        watcher.stop()
