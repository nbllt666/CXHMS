"""视频解析器（模块11 独立知识库）。

职责：抽离音轨做 ASR 转写，同时按固定间隔抽帧并逐帧调用图片解析器，最终把
「音轨转写 + 带时间戳帧描述」合并为统一文本。

冻结契约（spec「多模态文档解析器」）：
    parse_video(path, filename, mime, config=None, asr=None) -> ParseResult

依赖（Task 3/4/5 并行支点）：
    - `parsers.base.ParseResult`
    - `parsers.image_parser.parse_image`
    - `media.extract_audio` / `media.extract_frames` /
      `media.probe_duration` / `media.cleanup_paths`
    - `asr.ASRClient`

降级语义：
    - ASR 不可用：仅记录 `metadata.audio_error`，继续抽帧，不整体失败；
    - ffmpeg 不可用（抽音轨/抽帧抛 `KnowledgeFFmpegUnavailableError`）：整体失败，
      `parse_error=KNOWLEDGE_FFMPEG_UNAVAILABLE`；
    - 单帧解析失败：记入 `metadata.frame_errors`，不影响其它帧；
    - 音轨与帧描述皆空：`failed` + `KNOWLEDGE_PARSE_FAILED`。
"""

from __future__ import annotations

import os
import tempfile

from .. import media
from ..asr import ASRClient
from ..exceptions import KnowledgeASRUnavailableError, KnowledgeFFmpegUnavailableError
from .base import KNOWLEDGE_MEDIA_TOO_LONG, KNOWLEDGE_PARSE_FAILED, ParseResult
from .image_parser import parse_image

_PARSED = "parsed"
_FAILED = "failed"
_UNSUPPORTED = "unsupported"

_ERROR_PARSE_FAILED = KNOWLEDGE_PARSE_FAILED
_ERROR_ASR_UNAVAILABLE = "KNOWLEDGE_ASR_UNAVAILABLE"
_ERROR_FFMPEG_UNAVAILABLE = "KNOWLEDGE_FFMPEG_UNAVAILABLE"
_ERROR_MEDIA_TOO_LONG = KNOWLEDGE_MEDIA_TOO_LONG

_DEFAULT_SAMPLE_RATE = 16000
_DEFAULT_FRAME_INTERVAL = 10
_DEFAULT_MAX_FRAMES = 12
_DEFAULT_MAX_DURATION = 3600


def _as_positive_int(value: object, default: int) -> int:
    """把配置值安全地转为 ≥1 的整数；非法值回退默认值。"""
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def _build_result(
    text_content: str,
    parse_status: str,
    parse_error: str | None,
    metadata: dict,
    source_refs: list[str],
) -> ParseResult:
    """按冻结字段构造 ParseResult。"""
    return ParseResult(
        text_content=text_content,
        parse_status=parse_status,
        parse_error=parse_error,
        metadata=metadata,
        source_refs=source_refs,
    )


def _transcribe_audio(
    path: str,
    wav_path: str,
    sample_rate: int,
    config: dict,
    asr: ASRClient | None,
) -> tuple[str, dict, str | None]:
    """抽取音轨并转写。

    Returns:
        (transcript, audio_metadata, audio_error)：
            - `audio_error=None` 表示音轨转写成功（文本可能为空）；
            - `audio_error` 为错误码时表示该分支已降级，调用方应继续抽帧。
    """
    try:
        media.extract_audio(path, wav_path, sample_rate)
    except KnowledgeFFmpegUnavailableError:
        raise
    except Exception:
        return "", {}, _ERROR_PARSE_FAILED

    try:
        asr_client = asr if asr is not None else ASRClient(config)
        transcript_raw, asr_metadata = asr_client.transcribe(wav_path)
    except KnowledgeASRUnavailableError:
        return "", {}, _ERROR_ASR_UNAVAILABLE
    except Exception:
        return "", {}, _ERROR_PARSE_FAILED

    return (transcript_raw or "").strip(), dict(asr_metadata or {}), None


def parse_video(
    path: str,
    filename: str,
    mime: str,
    config: dict | None = None,
    asr: ASRClient | None = None,
) -> ParseResult:
    """解析视频文件：音轨转写 + 抽帧描述。

    Args:
        path: 视频文件绝对路径（原文件，不会被修改）。
        filename: 原始文件名（仅用于溯源，可为空）。
        mime: 上传时声明的 MIME 类型，写入 metadata。
        config: 知识库配置字典；缺省时使用冻结默认值。
        asr: 可注入的 ASR 客户端；缺省时按配置构造 `ASRClient`。

    Returns:
        ParseResult：
            - `parsed`：合并文本非空，metadata 含 duration/frames_count/
              frame_errors/transcript_chars/asr_available/mime；
            - `unsupported` + `KNOWLEDGE_MEDIA_TOO_LONG`：时长超过上限；
            - `failed` + 对应错误码：ffmpeg 不可用、音轨与帧皆空或其它解析异常。
    """
    config = dict(config or {})
    max_duration = _as_positive_int(
        config.get("max_media_duration_seconds"), _DEFAULT_MAX_DURATION
    )
    sample_rate = _as_positive_int(
        config.get("ffmpeg_audio_sample_rate"), _DEFAULT_SAMPLE_RATE
    )
    frame_interval = _as_positive_int(
        config.get("video_frame_interval_seconds"), _DEFAULT_FRAME_INTERVAL
    )
    max_frames = _as_positive_int(
        config.get("video_max_frames"), _DEFAULT_MAX_FRAMES
    )

    if not os.path.isfile(path):
        return _build_result(
            "",
            _FAILED,
            _ERROR_PARSE_FAILED,
            {"mime": mime, "reason": "file_not_found", "frames_count": 0},
            [path],
        )

    temp_dir: str | None = None
    try:
        duration = media.probe_duration(path)
        if duration is not None and float(duration) > max_duration:
            return _build_result(
                "",
                _UNSUPPORTED,
                _ERROR_MEDIA_TOO_LONG,
                {"mime": mime, "duration": duration, "frames_count": 0},
                [path],
            )

        temp_dir = tempfile.mkdtemp(prefix="knowledge_video_")

        wav_path = os.path.join(temp_dir, "audio.wav")
        transcript, asr_meta, audio_error = _transcribe_audio(
            path, wav_path, sample_rate, config, asr
        )
        asr_available = audio_error is None

        try:
            extracted_frames = media.extract_frames(
                path,
                temp_dir,
                interval=frame_interval,
                max_frames=max_frames,
            )
        except KnowledgeFFmpegUnavailableError:
            raise
        except Exception as exc:
            return _build_result(
                "",
                _FAILED,
                _ERROR_FFMPEG_UNAVAILABLE,
                {
                    "mime": mime,
                    "reason": str(exc),
                    "frames_count": 0,
                    "frame_errors": [],
                },
                [path],
            )

        frame_paths = [str(frame) for frame in (extracted_frames or [])][:max_frames]
        frame_lines: list[str] = []
        frame_errors: list[dict] = []

        for index, frame_path in enumerate(frame_paths):
            try:
                frame_result = parse_image(
                    frame_path,
                    f"frame_{index}.jpg",
                    "image/jpeg",
                    config,
                )
            except Exception as exc:
                frame_errors.append({"frame": index, "error": str(exc)})
                continue

            frame_text = (getattr(frame_result, "text_content", "") or "").strip()
            frame_status = getattr(frame_result, "parse_status", _FAILED)
            if frame_status == _PARSED and frame_text:
                timestamp = index * frame_interval
                frame_lines.append(f"[帧 {index} @ {timestamp}s] {frame_text}")
            else:
                error = getattr(frame_result, "parse_error", None) or frame_status
                frame_errors.append({"frame": index, "error": str(error)})

        audio_section = f"[视频音轨转写]\n{transcript}" if transcript else ""
        frames_section = "\n".join(frame_lines)
        merged_text = "\n\n".join(
            section for section in (audio_section, frames_section) if section
        ).strip()

        if not merged_text:
            return _build_result(
                "",
                _FAILED,
                _ERROR_PARSE_FAILED,
                {
                    "mime": mime,
                    "reason": "empty_content",
                    "duration": asr_meta.get("duration", duration),
                    "frames_count": len(frame_paths),
                    "frame_errors": frame_errors,
                    "transcript_chars": len(transcript),
                    "asr_available": asr_available,
                    "audio_error": audio_error,
                },
                [path],
            )

        metadata = {
            "duration": asr_meta.get("duration", duration),
            "frames_count": len(frame_paths),
            "frame_errors": frame_errors,
            "transcript_chars": len(transcript),
            "asr_available": asr_available,
            "mime": mime,
            "audio_error": audio_error,
        }
        return _build_result(merged_text, _PARSED, None, metadata, [path])
    except KnowledgeFFmpegUnavailableError:
        return _build_result(
            "",
            _FAILED,
            _ERROR_FFMPEG_UNAVAILABLE,
            {"mime": mime},
            [path],
        )
    except Exception as exc:
        return _build_result(
            "",
            _FAILED,
            _ERROR_PARSE_FAILED,
            {"mime": mime, "reason": str(exc)},
            [path],
        )
    finally:
        if temp_dir is not None:
            try:
                media.cleanup_paths([temp_dir])
            except Exception:  # 清理失败不得覆盖主结果
                pass
