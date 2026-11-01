"""统一解析入口（模块11 Task 3）。

`parse(source_path, filename, mime, config=None) -> ParseResult` 按 MIME/扩展名分派：
    - document → `parse_text_document`
    - image / audio / video → **函数内懒加载**对应解析器
      （`image_parser.parse_image` / `audio_parser.parse_audio` / `video_parser.parse_video`），
      避免并行开发期顶层导入失败；
    - 白名单外或未知类型 → `unsupported` + `KNOWLEDGE_UNSUPPORTED_MIME`；
    - 任意异常 → `failed` + `KNOWLEDGE_PARSE_FAILED`，本函数不抛出。

媒体时长 `max_media_duration_seconds` 校验位于音视频解析器内部，本模块不重复实现。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Set

from backend.core.knowledge.parsers.base import (
    DEFAULT_ALLOWED_AUDIO_MIMES,
    DEFAULT_ALLOWED_DOCUMENT_MIMES,
    DEFAULT_ALLOWED_IMAGE_MIMES,
    DEFAULT_ALLOWED_VIDEO_MIMES,
    KNOWLEDGE_PARSE_FAILED,
    KNOWLEDGE_UNSUPPORTED_MIME,
    ParseError,
    ParseResult,
    classify_mime,
    infer_mime,
    sanitize_filename,
)
from backend.core.knowledge.parsers.text_parser import parse_text_document

logger = logging.getLogger(__name__)

# 媒体大类 → 配置键名
_WHITELIST_CONFIG_KEYS: Dict[str, str] = {
    "document": "allowed_document_mimes",
    "image": "allowed_image_mimes",
    "audio": "allowed_audio_mimes",
    "video": "allowed_video_mimes",
}

# 媒体大类 → 默认白名单（config=None 或缺键时兜底）
_DEFAULT_WHITELISTS: Dict[str, List[str]] = {
    "document": DEFAULT_ALLOWED_DOCUMENT_MIMES,
    "image": DEFAULT_ALLOWED_IMAGE_MIMES,
    "audio": DEFAULT_ALLOWED_AUDIO_MIMES,
    "video": DEFAULT_ALLOWED_VIDEO_MIMES,
}


def _resolve_whitelist(config: Optional[Mapping[str, Any]], kind: str) -> Set[str]:
    """解析指定媒体大类的 MIME 白名单（配置优先，缺失回退默认值）。

    Args:
        config: 知识库配置字典，可为 None。
        kind: 媒体大类（document|image|audio|video）。

    Returns:
        规范化（小写去空白）后的 MIME 集合。
    """
    key = _WHITELIST_CONFIG_KEYS[kind]
    values: Any = None
    if config:
        try:
            values = config.get(key)  # type: ignore[union-attr]
        except AttributeError:
            values = None
    if not values:
        values = _DEFAULT_WHITELISTS[kind]
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _build_result(
    parse_status: str,
    parse_error: Optional[str],
    mime: str,
    source_path: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> ParseResult:
    """构造统一的失败/不支持 ParseResult。

    Args:
        parse_status: failed 或 unsupported。
        parse_error: 错误码或错误摘要。
        mime: 已推断的 MIME。
        source_path: 源文件路径（写入 source_refs）。
        metadata: 额外元数据。

    Returns:
        对应的 ParseResult。
    """
    merged: Dict[str, Any] = {"mime": mime}
    if metadata:
        merged.update(metadata)
    return ParseResult(
        text_content="",
        parse_status=parse_status,
        parse_error=parse_error,
        metadata=merged,
        source_refs=[source_path] if source_path else [],
    )


def parse(
    source_path: str,
    filename: str,
    mime: str,
    config: Optional[Mapping[str, Any]] = None,
) -> ParseResult:
    """统一解析入口：按 MIME/扩展名分派到对应解析器。

    Args:
        source_path: 已落盘源文件路径。
        filename: 原始文件名（用于 MIME 兜底与清洗）。
        mime: 客户端上报的 MIME（application/octet-stream 或空时按扩展名推断）。
        config: 知识库配置（提供 allowed_*_mimes 白名单）；None 时使用默认白名单。

    Returns:
        ParseResult：parsed / failed / unsupported；本函数不抛出异常。
    """
    safe_name = sanitize_filename(filename)
    safe_mime = infer_mime(safe_name, mime)
    kind = classify_mime(safe_mime)

    if kind == "unsupported":
        return _build_result(
            "unsupported",
            f"{KNOWLEDGE_UNSUPPORTED_MIME}: 不支持的 MIME 类型 {safe_mime}",
            safe_mime,
            source_path,
        )

    if safe_mime not in _resolve_whitelist(config, kind):
        return _build_result(
            "unsupported",
            f"{KNOWLEDGE_UNSUPPORTED_MIME}: MIME 类型 {safe_mime} 不在白名单",
            safe_mime,
            source_path,
        )

    if kind == "document":
        try:
            return parse_text_document(source_path, safe_name, safe_mime)
        except ParseError as exc:
            return _build_result(
                "failed",
                exc.parse_error,
                safe_mime,
                source_path,
                {"error": exc.message},
            )
        except Exception as exc:  # noqa: BLE001 - 统一转 failed，不抛出
            logger.warning("文档解析失败: %s - %s", safe_name, exc)
            return _build_result(
                "failed", KNOWLEDGE_PARSE_FAILED, safe_mime, source_path, {"error": str(exc)}
            )

    # 媒体类：函数内懒加载，避免并行开发期顶层导入失败
    try:
        if kind == "image":
            from backend.core.knowledge.parsers.image_parser import parse_image

            return parse_image(source_path, safe_name, safe_mime, config)

        if kind == "audio":
            from backend.core.knowledge.parsers.audio_parser import parse_audio

            return parse_audio(source_path, safe_name, safe_mime, config)

        from backend.core.knowledge.parsers.video_parser import parse_video

        return parse_video(source_path, safe_name, safe_mime, config)
    except ParseError as exc:
        return _build_result(
            "failed",
            exc.parse_error,
            safe_mime,
            source_path,
            {"error": exc.message},
        )
    except ImportError as exc:
        # 对应解析器模块尚未就绪 → failed，禁止 Mock 假成功
        logger.warning("媒体解析器不可用: kind=%s - %s", kind, exc)
        return _build_result(
            "failed",
            KNOWLEDGE_PARSE_FAILED,
            safe_mime,
            source_path,
            {"error": f"{kind} 解析器不可用: {exc}"},
        )
    except Exception as exc:  # noqa: BLE001 - 统一转 failed，不抛出
        logger.warning("媒体解析失败: kind=%s name=%s - %s", kind, safe_name, exc)
        return _build_result(
            "failed", KNOWLEDGE_PARSE_FAILED, safe_mime, source_path, {"error": str(exc)}
        )
