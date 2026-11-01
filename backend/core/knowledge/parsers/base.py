"""知识库解析器基座（模块11 Task 3）。

冻结 `ParseResult` 数据模型与内部异常 `ParseError`，并提供：
    - `sanitize_filename`：文件名清洗（仅保留 basename，去除路径穿越与控制字符）
    - `infer_mime`：MIME 兜底推断（application/octet-stream 或空值按扩展名映射）
    - `classify_mime`：MIME 分类（document / image / audio / video / unsupported）

默认 MIME 白名单与 `public/config_template/knowledge_config.json`
（`config/default.yaml::knowledge` 同键）保持一致，供 router 在 `config=None`
或白名单缺失时兜底（rules-3 §三 auto_fill）。

本模块只依赖标准库，不导入 image/audio/video 解析器，避免并行开发期导入失败。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# 错误码（与 public/schema/knowledge.json::definitions.error_codes 对齐）
# --------------------------------------------------------------------------- #
KNOWLEDGE_PARSE_FAILED = "KNOWLEDGE_PARSE_FAILED"
KNOWLEDGE_UNSUPPORTED_MIME = "KNOWLEDGE_UNSUPPORTED_MIME"
KNOWLEDGE_MEDIA_TOO_LONG = "KNOWLEDGE_MEDIA_TOO_LONG"

# 文本类文档大小上限默认值（MB），与 knowledge_config.json 默认值一致
DEFAULT_MAX_DOCUMENT_SIZE_MB = 20

# --------------------------------------------------------------------------- #
# 默认 MIME 白名单（与 public/config_template/knowledge_config.json 一致）
# --------------------------------------------------------------------------- #
DEFAULT_ALLOWED_DOCUMENT_MIMES: List[str] = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/markdown",
]

DEFAULT_ALLOWED_IMAGE_MIMES: List[str] = [
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
]

DEFAULT_ALLOWED_AUDIO_MIMES: List[str] = [
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/flac",
    "audio/ogg",
    "audio/aac",
    "audio/opus",
]

DEFAULT_ALLOWED_VIDEO_MIMES: List[str] = [
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "video/x-msvideo",
    "video/x-flv",
]

# 扩展名 → MIME 映射（用于上传 Content-Type=application/octet-stream 的兜底）
_EXTENSION_MIME_MAP: Dict[str, str] = {
    # 文档类
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    # 图片类
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    # 音频类
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".opus": "audio/opus",
    # 视频类
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".flv": "video/x-flv",
}

# 无法清洗出有效文件名时的兜底值
_FALLBACK_FILENAME = "unnamed"


@dataclass
class ParseResult:
    """解析结果（冻结契约，逐字段对齐 spec「冻结的解析数据模型与函数签名」）。

    Attributes:
        text_content: 解析得到的纯文本；失败/不支持时为空字符串或占位说明。
        parse_status: pending|parsing|parsed|failed|unsupported。
        parse_error: 失败/不支持时的错误码或错误摘要，可为 None。
        metadata: 解析元数据（chars/mime/size_bytes/error 等）。
        source_refs: 来源引用列表（如源文件路径）。
    """

    text_content: str
    parse_status: str
    parse_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_refs: List[str] = field(default_factory=list)


class ParseError(Exception):
    """解析器内部异常；由 router 统一转为 `failed` 的 ParseResult。

    Attributes:
        message: 异常描述。
        parse_error: 应写入 ParseResult.parse_error 的错误码。
    """

    def __init__(self, message: str, parse_error: str = KNOWLEDGE_PARSE_FAILED):
        super().__init__(message)
        self.message = message
        self.parse_error = parse_error


def sanitize_filename(name: str) -> str:
    """清洗文件名，仅保留安全的 basename。

    去除 `../` / `..\\` 路径穿越片段、路径前缀与控制字符；空结果回退为 `unnamed`。

    Args:
        name: 原始文件名（可能含路径穿越、绝对路径或非法字符）。

    Returns:
        清洗后的安全文件名。
    """
    if not name:
        return _FALLBACK_FILENAME

    raw = str(name)
    # 去除显式路径穿越片段（兼容 Windows / POSIX 两种写法）
    raw = raw.replace("..\\", "").replace("../", "")
    # 统一分隔符后仅保留 basename（挡住绝对路径与多级目录）
    raw = raw.replace("\\", "/")
    base = raw.rsplit("/", 1)[-1]
    # 去除控制字符（\x00 ~ \x1f、\x7f 等不可打印字符）
    base = "".join(ch for ch in base if ch.isprintable())
    base = base.strip()

    if not base or base in (".", ".."):
        return _FALLBACK_FILENAME
    return base


def _normalize_mime(mime: Optional[str]) -> str:
    """规范化 MIME：小写、去空白、去参数（如 `text/plain; charset=utf-8`）。"""
    return (mime or "").strip().lower().split(";", 1)[0].strip()


def infer_mime(filename: str, mime: str) -> str:
    """推断有效 MIME；当入参为 application/octet-stream 或空时按扩展名兜底。

    Args:
        filename: 文件名（用于扩展名映射）。
        mime: 客户端上报的 MIME。

    Returns:
        推断后的 MIME；无法推断时返回 `application/octet-stream`。
    """
    normalized = _normalize_mime(mime)
    if normalized and normalized != "application/octet-stream":
        return normalized
    ext = os.path.splitext(sanitize_filename(filename))[1].lower()
    return _EXTENSION_MIME_MAP.get(ext, "application/octet-stream")


def classify_mime(mime: str) -> str:
    """按 MIME 归类为 `document|image|audio|video|unsupported`。

    Args:
        mime: 已推断的 MIME。

    Returns:
        媒体大类字符串；不属于已知大类时返回 `unsupported`。
    """
    normalized = _normalize_mime(mime)
    if normalized in DEFAULT_ALLOWED_DOCUMENT_MIMES:
        return "document"
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("audio/"):
        return "audio"
    if normalized.startswith("video/"):
        return "video"
    return "unsupported"
