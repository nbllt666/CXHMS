"""音频解析器（模块11 独立知识库）。

职责：把任意受支持音频格式经 ffmpeg 归一化为 16kHz 单声道 WAV，再交给 ASR
转写为文本，最终封装为冻结的 `ParseResult` 数据模型。

冻结契约（spec「多模态文档解析器」）：
    parse_audio(path, filename, mime, config=None, asr=None) -> ParseResult

依赖（Task 3/5 并行支点）：
    - `parsers.base.ParseResult`
    - `media.extract_audio` / `media.probe_duration` / `media.cleanup_paths`
    - `asr.ASRClient`

失败可观测性：任何异常都转成 `parse_status=failed` + 错误码，不向外抛未捕获异常；
临时 WAV 落在独立临时目录，`finally` 中整体清理，原文件始终保留。
"""

from __future__ import annotations

import os
import tempfile

from .. import media
from ..asr import ASRClient
from ..exceptions import KnowledgeASRUnavailableError, KnowledgeFFmpegUnavailableError
from .base import KNOWLEDGE_MEDIA_TOO_LONG, KNOWLEDGE_PARSE_FAILED, ParseResult

_PARSED = "parsed"
_FAILED = "failed"
_UNSUPPORTED = "unsupported"

_ERROR_PARSE_FAILED = KNOWLEDGE_PARSE_FAILED
_ERROR_ASR_UNAVAILABLE = "KNOWLEDGE_ASR_UNAVAILABLE"
_ERROR_FFMPEG_UNAVAILABLE = "KNOWLEDGE_FFMPEG_UNAVAILABLE"
_ERROR_MEDIA_TOO_LONG = KNOWLEDGE_MEDIA_TOO_LONG

_DEFAULT_SAMPLE_RATE = 16000
_DEFAULT_MAX_DURATION = 3600
_DEFAULT_ASR_LANGUAGE = "zh"
_DEFAULT_ASR_PROVIDER = "faster_whisper"


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
    """按冻结字段构造 ParseResult，避免依赖 base 模块内部实现细节。"""
    return ParseResult(
        text_content=text_content,
        parse_status=parse_status,
        parse_error=parse_error,
        metadata=metadata,
        source_refs=source_refs,
    )


def parse_audio(
    path: str,
    filename: str,
    mime: str,
    config: dict | None = None,
    asr: ASRClient | None = None,
) -> ParseResult:
    """解析音频文件并返回转写结果。

    Args:
        path: 音频文件绝对路径（原文件，不会被修改）。
        filename: 原始文件名（仅用于溯源，可为空）。
        mime: 上传时声明的 MIME 类型，写入 metadata。
        config: 知识库配置字典；缺省时使用冻结默认值。
        asr: 可注入的 ASR 客户端；缺省时按配置构造 `ASRClient`。

    Returns:
        ParseResult：
            - `parsed`：转写文本非空，metadata 含 duration/language/
              transcript_chars/provider/segments/mime；
            - `unsupported` + `KNOWLEDGE_MEDIA_TOO_LONG`：时长超过上限；
            - `failed` + 对应错误码：ASR 不可用、ffmpeg 不可用或其它解析异常。
    """
    config = dict(config or {})
    max_duration = _as_positive_int(
        config.get("max_media_duration_seconds"), _DEFAULT_MAX_DURATION
    )
    sample_rate = _as_positive_int(
        config.get("ffmpeg_audio_sample_rate"), _DEFAULT_SAMPLE_RATE
    )

    if not os.path.isfile(path):
        return _build_result(
            "",
            _FAILED,
            _ERROR_PARSE_FAILED,
            {"mime": mime, "reason": "file_not_found"},
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
                {"mime": mime, "duration": duration},
                [path],
            )

        temp_dir = tempfile.mkdtemp(prefix="knowledge_audio_")
        wav_path = os.path.join(temp_dir, "audio.wav")
        media.extract_audio(path, wav_path, sample_rate)

        asr_client = asr if asr is not None else ASRClient(config)
        transcript_raw, asr_metadata = asr_client.transcribe(wav_path)
        asr_meta = dict(asr_metadata or {})
        transcript = (transcript_raw or "").strip()

        if not transcript:
            return _build_result(
                "",
                _FAILED,
                _ERROR_PARSE_FAILED,
                {"mime": mime, "reason": "empty_transcript"},
                [path],
            )

        metadata = {
            "duration": asr_meta.get("duration", duration),
            "language": asr_meta.get("language", config.get("asr_language", _DEFAULT_ASR_LANGUAGE)),
            "transcript_chars": len(transcript),
            "provider": asr_meta.get("provider", config.get("asr_provider", _DEFAULT_ASR_PROVIDER)),
            "segments": asr_meta.get("segments", 0),
            "mime": mime,
        }
        return _build_result(transcript, _PARSED, None, metadata, [path])
    except KnowledgeASRUnavailableError:
        return _build_result(
            "",
            _FAILED,
            _ERROR_ASR_UNAVAILABLE,
            {"mime": mime},
            [path],
        )
    except KnowledgeFFmpegUnavailableError:
        return _build_result(
            "",
            _FAILED,
            _ERROR_FFMPEG_UNAVAILABLE,
            {"mime": mime},
            [path],
        )
    except Exception as exc:  # 兜底：解析失败必须可观测，不得抛出未捕获异常
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
