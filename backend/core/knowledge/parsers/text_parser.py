"""文本类文档解析器（模块11 Task 3）。

支持 PDF / DOCX / DOC / TXT / MD：复用 `backend.core.document.parser.parse_document`
得到纯文本，并按冻结契约返回 `ParseResult`。

约束：
    - 读取前按 `max_document_size_mb`（默认 20MB）校验大小，超限抛 `ParseError`
      （由 router 转为 `failed`）；
    - `.doc` 旧版格式、PDF/Word 无可提取文本等占位返回 → `parse_status="unsupported"`；
    - 其余解析异常一律转为 `failed` + `KNOWLEDGE_PARSE_FAILED`，不向调用方抛出。
"""

from __future__ import annotations

import logging
import os

from backend.core.document.parser import parse_document
from backend.core.knowledge.parsers.base import (
    DEFAULT_MAX_DOCUMENT_SIZE_MB,
    KNOWLEDGE_PARSE_FAILED,
    KNOWLEDGE_UNSUPPORTED_MIME,
    ParseError,
    ParseResult,
    infer_mime,
    sanitize_filename,
)

logger = logging.getLogger(__name__)

# parse_document 返回的“无可提取内容”占位前缀（命中即判 unsupported）
_UNSUPPORTED_TEXT_PREFIXES = (
    "[不支持解析旧版 .doc 格式",
    "[PDF 无可提取文本]",
    "[Word 文档无可提取文本]",
)


def parse_text_document(path: str, filename: str, mime: str) -> ParseResult:
    """解析文本类文档为 `ParseResult`。

    Args:
        path: 源文件路径（由调用方保证已落盘）。
        filename: 原始文件名（用于 MIME 兜底与清洗）。
        mime: 客户端上报的 MIME。

    Returns:
        ParseResult：正常为 `parsed`；占位文本为 `unsupported`；解析异常为 `failed`。

    Raises:
        ParseError: 文件超过 `max_document_size_mb`（默认 20MB）时抛出。
    """
    safe_name = sanitize_filename(filename)
    safe_mime = infer_mime(safe_name, mime)
    max_bytes = DEFAULT_MAX_DOCUMENT_SIZE_MB * 1024 * 1024

    try:
        size_bytes = os.path.getsize(path)
        if size_bytes > max_bytes:
            raise ParseError(
                f"文档 {safe_name} 大小 {size_bytes} 字节超过上限 {max_bytes} 字节"
                f"（{DEFAULT_MAX_DOCUMENT_SIZE_MB}MB）"
            )

        with open(path, "rb") as handle:
            raw_bytes = handle.read()

        # utf-8 容错解码由 parse_document 内部的 _parse_text 负责
        text_content = parse_document(safe_name, safe_mime, raw_bytes) or ""

        stripped = text_content.strip()
        for prefix in _UNSUPPORTED_TEXT_PREFIXES:
            if stripped.startswith(prefix):
                return ParseResult(
                    text_content="",
                    parse_status="unsupported",
                    parse_error=f"{KNOWLEDGE_UNSUPPORTED_MIME}: {stripped}",
                    metadata={"mime": safe_mime, "size_bytes": size_bytes},
                    source_refs=[path],
                )

        return ParseResult(
            text_content=text_content,
            parse_status="parsed",
            metadata={
                "chars": len(text_content),
                "mime": safe_mime,
                "size_bytes": size_bytes,
            },
            source_refs=[path],
        )
    except ParseError:
        # 大小超限交由 router 转 failed
        raise
    except Exception as exc:  # noqa: BLE001 - 解析失败必须可观测且不抛出
        logger.warning("文本类文档解析失败: %s - %s", safe_name, exc)
        return ParseResult(
            text_content="",
            parse_status="failed",
            parse_error=KNOWLEDGE_PARSE_FAILED,
            metadata={"mime": safe_mime, "error": str(exc)},
            source_refs=[path] if path else [],
        )
