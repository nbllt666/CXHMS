"""配置文件监听器

监听 config/default.yaml 修改事件，5 秒防抖后触发 reinit。

设计要点：
    - 基于 watchdog Observer 监听配置文件所在目录
    - 5 秒防抖：连续修改只触发一次回调
    - 异常容错：watchdog 未安装或启动失败时记录 warning 不抛出，
      不影响主服务（手动 reinit 仍可用）
    - 线程安全：防抖计时器用 threading.Lock 保护
    - daemon 线程：防抖计时器设为 daemon，进程退出时自动结束
"""

import threading
from pathlib import Path
from typing import Callable, Optional

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


class ConfigWatcher:
    """配置文件监听器（基于 watchdog）。

    监听 config/default.yaml 的修改事件，5 秒防抖后触发回调。
    异常时记录 warning 不抛出，不影响主服务。

    Attributes:
        DEBOUNCE_SECONDS: 防抖时间（秒），默认 5.0。
    """

    DEBOUNCE_SECONDS = 5.0

    def __init__(self, config_path: str, callback: Callable[[], None]):
        """初始化配置监听器。

        Args:
            config_path: 监听的配置文件路径（如 "config/default.yaml"）。
                内部会转为绝对路径，避免工作目录变化影响比较。
            callback: 文件修改且防抖后触发的回调（无参数，由调用方
                自行处理 reinit 逻辑）。回调异常不会导致 watcher 崩溃。
        """
        self._config_path = Path(config_path).absolute()
        self._callback = callback
        self._observer = None
        self._debounce_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        """启动监听器。

        幂等：已启动时直接返回。
        异常时记录 warning 不抛出：
            - watchdog 未安装 → warning，手动 reinit 仍可用
            - 其他异常 → warning，不影响主服务
        """
        if self._started:
            return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self, watcher: "ConfigWatcher"):
                    self._watcher = watcher

                def on_modified(self, event):
                    # 只关心配置文件本身（不是目录）
                    if event.is_directory:
                        return
                    # watchdog 在 Windows 上可能返回不同路径分隔符，用 Path 比较
                    try:
                        src_path = Path(event.src_path).absolute()
                    except Exception:
                        return
                    if src_path == self._watcher._config_path:
                        self._watcher._on_file_changed()

            self._observer = Observer()
            # 监听 config 目录（而非单个文件，watchdog 对文件监听在 Windows 上不稳定）
            watch_dir = self._config_path.parent
            self._observer.schedule(_Handler(self), str(watch_dir), recursive=False)
            self._observer.start()
            self._started = True
            logger.info(f"ConfigWatcher 已启动，监听 {self._config_path}")
        except ImportError:
            logger.warning(
                "watchdog 库未安装，ConfigWatcher 未启动（手动 reinit 仍可用）"
            )
        except Exception as e:
            logger.warning(f"ConfigWatcher 启动失败 [{type(e).__name__}]: {e}")

    def stop(self) -> None:
        """停止监听器。

        幂等：未启动时直接返回。
        取消待执行的防抖计时器，避免 stop 后再触发回调。
        异常时记录 warning 不抛出。
        """
        if not self._started:
            return
        try:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=2.0)
                self._observer = None
            # 取消待执行的防抖计时器
            with self._lock:
                if self._debounce_timer:
                    self._debounce_timer.cancel()
                    self._debounce_timer = None
            self._started = False
            logger.info("ConfigWatcher 已停止")
        except Exception as e:
            logger.warning(f"ConfigWatcher 停止失败: {e}")

    def _on_file_changed(self) -> None:
        """文件修改事件处理（防抖）。

        每次收到修改事件时取消之前的计时器并启动新的计时器，
        确保连续修改只在最后一次修改后 DEBOUNCE_SECONDS 秒触发一次回调。
        """
        with self._lock:
            # 取消之前的计时器
            if self._debounce_timer:
                self._debounce_timer.cancel()
            # 启动新的计时器
            self._debounce_timer = threading.Timer(
                self.DEBOUNCE_SECONDS, self._fire_callback
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _fire_callback(self) -> None:
        """防抖结束后触发回调。

        回调异常不会导致 watcher 崩溃，仅记录 warning。
        """
        try:
            logger.info(
                f"ConfigWatcher 检测到配置变化，触发 reinit"
                f"（{self.DEBOUNCE_SECONDS}s 防抖后）"
            )
            self._callback()
        except Exception as e:
            logger.warning(
                f"ConfigWatcher 回调执行失败 [{type(e).__name__}]: {e}"
            )
