"""知识库媒体工具（模块11）。

冻结签名见 spec「冻结的 ASR / 媒体签名」：
    ffmpeg_available(config: dict) -> bool
    extract_audio(src: str, dst: str, sample_rate: int = 16000) -> str
    extract_frames(src: str, out_dir: str, interval: int = 10, max_frames: int = 12) -> list[str]
    probe_duration(src: str) -> float | None
    cleanup_paths(paths: list[str]) -> None

约束：
1. ffmpeg 发现顺序：``config["ffmpeg_path"]`` → ``shutil.which("ffmpeg")`` →
   ``imageio_ffmpeg.get_ffmpeg_exe()``（仅当 ``ffmpeg_fallback_to_imageio=True``），结果缓存。
2. ``ffmpeg_available`` 任何失败返回 ``False``，不抛异常。
3. 抽取失败时 ffmpeg 缺失抛 ``KnowledgeFFmpegUnavailableError``，其余抛
   ``KnowledgeParseError``。
4. 所有路径在入口处统一转为绝对路径；临时文件/目录由调用方创建与清理
   （``cleanup_paths`` 仅提供幂等清理能力）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from typing import Any, Dict, List, Optional

from backend.core.knowledge.exceptions import (
    KnowledgeFFmpegUnavailableError,
    KnowledgeParseError,
)

# 抽取类命令超时（秒），可用环境变量覆盖；冻结签名无 config 参数，故此处以模块常量承载。
FFMPEG_TIMEOUT_SECONDS = int(os.environ.get("CXHMS_FFMPEG_TIMEOUT_SECONDS", "120"))
# `ffmpeg -i` 探测类命令超时（秒），可用环境变量覆盖。
FFMPEG_PROBE_TIMEOUT_SECONDS = int(os.environ.get("CXHMS_FFMPEG_PROBE_TIMEOUT_SECONDS", "30"))

_DURATION_PATTERN = re.compile(
    r"Duration:\s*(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?"
)

# 缓存键为 (显式 ffmpeg_path, 是否允许 imageio 回退)，值为绝对路径或 None。
_FFMPEG_CACHE: Dict[tuple, Optional[str]] = {}
_FFMPEG_CACHE_LOCK = threading.Lock()


def reset_ffmpeg_cache() -> None:
    """清空 ffmpeg 发现缓存（供测试或运行期重新探测使用）。"""
    with _FFMPEG_CACHE_LOCK:
        _FFMPEG_CACHE.clear()


def _import_imageio_ffmpeg() -> Any:
    """懒加载 imageio_ffmpeg（未安装时抛 ImportError）。"""
    import imageio_ffmpeg

    return imageio_ffmpeg


def _probe_ffmpeg(
    explicit_path: Optional[str], fallback_to_imageio: bool
) -> Optional[str]:
    """按发现顺序返回 ffmpeg 可执行文件的绝对路径，找不到返回 None。"""
    if explicit_path:
        candidate = os.path.abspath(explicit_path)
        if os.path.isfile(candidate):
            return candidate

    which_path = shutil.which("ffmpeg")
    if which_path:
        return os.path.abspath(which_path)

    if fallback_to_imageio:
        try:
            module = _import_imageio_ffmpeg()
            exe = module.get_ffmpeg_exe()
        except Exception:
            return None
        if exe:
            exe_abs = os.path.abspath(str(exe))
            if os.path.isfile(exe_abs):
                return exe_abs

    return None


def _resolve_ffmpeg(config: Optional[dict] = None) -> Optional[str]:
    """解析并缓存 ffmpeg 可执行文件路径。

    Args:
        config: 知识库配置；仅读取 ``ffmpeg_path`` 与 ``ffmpeg_fallback_to_imageio``。

    Returns:
        绝对路径；不可用时返回 None。
    """
    cfg = config if isinstance(config, dict) else {}
    explicit = cfg.get("ffmpeg_path") or ""
    explicit_path = str(explicit).strip() or None
    fallback = bool(cfg.get("ffmpeg_fallback_to_imageio", True))
    cache_key = (explicit_path, fallback)

    with _FFMPEG_CACHE_LOCK:
        if cache_key in _FFMPEG_CACHE:
            return _FFMPEG_CACHE[cache_key]

    resolved = _probe_ffmpeg(explicit_path, fallback)

    with _FFMPEG_CACHE_LOCK:
        _FFMPEG_CACHE[cache_key] = resolved
    return resolved


def _last_known_ffmpeg() -> Optional[str]:
    """返回缓存中最近一次成功解析的 ffmpeg 路径。

    冻结签名中 ``extract_audio`` / ``extract_frames`` / ``probe_duration`` 不含 config
    参数，调用前通常已由 ``ffmpeg_available(config)`` 解析过显式 ``ffmpeg_path``；
    此处复用该成功结果，避免无 config 路径时退化为系统 PATH 探测。
    """
    with _FFMPEG_CACHE_LOCK:
        for value in _FFMPEG_CACHE.values():
            if value:
                return value
    return None


def ffmpeg_available(config: dict) -> bool:
    """判断 ffmpeg 是否可用（缓存结果，任何异常返回 False）。"""
    try:
        return _resolve_ffmpeg(config) is not None
    except Exception:
        return False


def _run_ffmpeg(
    cmd: List[str], timeout: int, action: str
) -> "subprocess.CompletedProcess[str]":
    """执行 ffmpeg 命令，超时/启动失败统一转为 ``KnowledgeParseError``。"""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise KnowledgeParseError(
            f"ffmpeg {action} timed out after {timeout}s",
            {"action": action, "timeout_seconds": timeout, "command": cmd},
        ) from exc
    except OSError as exc:
        raise KnowledgeParseError(
            f"ffmpeg {action} failed to start: {exc}",
            {"action": action, "command": cmd},
        ) from exc


def _require_ffmpeg(action: str, source_path: str) -> str:
    """解析 ffmpeg，缺失时抛 ``KnowledgeFFmpegUnavailableError``。"""
    exe = _resolve_ffmpeg(None) or _last_known_ffmpeg()
    if not exe:
        raise KnowledgeFFmpegUnavailableError(
            f"ffmpeg executable not found; cannot {action}",
            {"action": action, "source": source_path},
        )
    return exe


def extract_audio(src: str, dst: str, sample_rate: int = 16000) -> str:
    """将源媒体音轨归一化为单声道 WAV。

    Args:
        src: 源媒体文件路径。
        dst: 目标 WAV 路径（父目录不存在时自动创建）。
        sample_rate: 采样率，默认 16000。

    Returns:
        目标 WAV 的绝对路径。

    Raises:
        KnowledgeFFmpegUnavailableError: ffmpeg 不可用。
        KnowledgeParseError: 源文件缺失或 ffmpeg 执行失败/超时。
    """
    src_abs = os.path.abspath(src)
    dst_abs = os.path.abspath(dst)

    if not os.path.isfile(src_abs):
        raise KnowledgeParseError(
            f"source media file not found: {src_abs}", {"source": src_abs}
        )

    exe = _require_ffmpeg("extract audio", src_abs)

    rate = int(sample_rate) if sample_rate else 16000
    if rate <= 0:
        rate = 16000

    dst_dir = os.path.dirname(dst_abs)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)

    cmd = [
        exe,
        "-y",
        "-i",
        src_abs,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(rate),
        "-f",
        "wav",
        dst_abs,
    ]
    completed = _run_ffmpeg(cmd, FFMPEG_TIMEOUT_SECONDS, "extract audio")

    if completed.returncode != 0 or not os.path.isfile(dst_abs):
        raise KnowledgeParseError(
            "ffmpeg failed to extract audio",
            {
                "source": src_abs,
                "destination": dst_abs,
                "returncode": completed.returncode,
                "stderr": (completed.stderr or "")[-2000:],
            },
        )

    return dst_abs


def extract_frames(
    src: str, out_dir: str, interval: int = 10, max_frames: int = 12
) -> List[str]:
    """按固定时间间隔抽取视频关键帧为 JPG。

    帧率表达式为 ``fps=1/interval``，输出 ``frame_%03d.jpg``，最多 ``max_frames`` 张。
    参数默认值由冻结签名提供，不读取业务配置。

    Args:
        src: 源视频路径。
        out_dir: 抽帧输出目录（不存在时自动创建）。
        interval: 抽帧间隔秒数（≥1，非法值回退为 1）。
        max_frames: 最大帧数（≥1，非法值回退为 1）。

    Returns:
        抽取到的帧绝对路径列表，按文件名升序。

    Raises:
        KnowledgeFFmpegUnavailableError: ffmpeg 不可用。
        KnowledgeParseError: 源文件缺失或 ffmpeg 执行失败/超时。
    """
    src_abs = os.path.abspath(src)
    out_abs = os.path.abspath(out_dir)

    if not os.path.isfile(src_abs):
        raise KnowledgeParseError(
            f"source video file not found: {src_abs}", {"source": src_abs}
        )

    exe = _require_ffmpeg("extract frames", src_abs)

    try:
        safe_interval = int(interval)
    except (TypeError, ValueError):
        safe_interval = 10
    if safe_interval <= 0:
        safe_interval = 1

    try:
        safe_max_frames = int(max_frames)
    except (TypeError, ValueError):
        safe_max_frames = 12
    if safe_max_frames <= 0:
        safe_max_frames = 1

    os.makedirs(out_abs, exist_ok=True)
    output_pattern = os.path.join(out_abs, "frame_%03d.jpg")

    cmd = [
        exe,
        "-y",
        "-i",
        src_abs,
        "-vf",
        f"fps=1/{safe_interval}",
        "-frames:v",
        str(safe_max_frames),
        output_pattern,
    ]
    completed = _run_ffmpeg(cmd, FFMPEG_TIMEOUT_SECONDS, "extract frames")

    if completed.returncode != 0:
        raise KnowledgeParseError(
            "ffmpeg failed to extract frames",
            {
                "source": src_abs,
                "out_dir": out_abs,
                "returncode": completed.returncode,
                "stderr": (completed.stderr or "")[-2000:],
            },
        )

    frame_names = sorted(
        name
        for name in os.listdir(out_abs)
        if name.startswith("frame_") and name.lower().endswith((".jpg", ".jpeg"))
    )
    frames = [os.path.abspath(os.path.join(out_abs, name)) for name in frame_names]
    return frames[:safe_max_frames]


def probe_duration(src: str) -> Optional[float]:
    """解析媒体时长（秒）。

    使用 ``ffmpeg -i`` 的 stderr 中 ``Duration: HH:MM:SS.ss``；任何失败返回 None，不抛异常。

    Args:
        src: 源媒体路径。

    Returns:
        时长秒数；无法解析时返回 None。
    """
    try:
        src_abs = os.path.abspath(src)
        if not os.path.isfile(src_abs):
            return None
        exe = _resolve_ffmpeg(None) or _last_known_ffmpeg()
        if not exe:
            return None
        completed = subprocess.run(
            [exe, "-i", src_abs],
            capture_output=True,
            text=True,
            timeout=FFMPEG_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
        output = f"{completed.stderr or ''}\n{completed.stdout or ''}"
        match = _DURATION_PATTERN.search(output)
        if not match:
            return None
        hours, minutes, seconds, fraction = match.groups()
        total = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        if fraction:
            total += float(f"0.{fraction}")
        return float(total)
    except Exception:
        return None


def cleanup_paths(paths: List[str]) -> None:
    """幂等删除文件或目录，任何异常均被忽略。

    Args:
        paths: 待删除路径列表；不存在的路径直接跳过。
    """
    for raw_path in paths or []:
        if not raw_path:
            continue
        try:
            target = os.path.abspath(raw_path)
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.lexists(target):
                try:
                    os.remove(target)
                except OSError:
                    continue
        except Exception:
            continue
