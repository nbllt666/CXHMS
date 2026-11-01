"""图片解析器（模块11 Task 4）。

复用 `modules/模块8_多模态管线` 的 `MultimodalPipeline.preprocess("image")`
（PaddleOCR + vLLM vision 双通道），把 OCR 文本块与视觉描述合并为
知识库统一的 `ParseResult.text_content`。

关键约束（spec「模块导入边界说明」）：
    - `MultimodalPipeline` 必须**函数内懒加载**（`_load_pipeline_class`），
      避免并行开发期顶层导入失败；
    - 导入或实例化失败 → `parse_status="failed"` + `KNOWLEDGE_PARSE_FAILED`，
      **禁止回退 Mock、禁止把模拟文本记为 parsed（假闭合）**；
    - vision 不可用（`vision_degraded=True`）仍为 `parsed`，并在 metadata 标记；
    - 合并后文本为空也仍为 `parsed`，仅额外记 `empty_text=True`，不报错；
    - 其余任意异常一律转 `failed` + `KNOWLEDGE_PARSE_FAILED`，本函数不抛出。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from backend.core.knowledge.parsers.base import (
    KNOWLEDGE_PARSE_FAILED,
    ParseResult,
    infer_mime,
    sanitize_filename,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 多模态管线懒加载（测试可 monkeypatch 本函数注入假实现）
# --------------------------------------------------------------------------- #


def _load_pipeline_class() -> Any:
    """懒加载 `MultimodalPipeline` 类（backend → 业务模块的单向依赖）。

    导入发生在函数内部，因此并行开发期缺少该模块时，
    本模块仍可被 router 通过 try-except 转成 `failed`，而不影响其它解析器导入。

    Returns:
        `modules.模块8_多模态管线.MultimodalPipeline` 类。

    Raises:
        ImportError: 多模态管线模块不可用。

    Note:
        测试可通过 `monkeypatch.setattr(image_parser, "_load_pipeline_class", ...)`
        注入假管线类，无需真实 PaddleOCR / vLLM。
    """
    from modules.模块8_多模态管线 import MultimodalPipeline

    return MultimodalPipeline


def _instantiate_pipeline(
    pipeline_class: Any, config: Optional[Dict[str, Any]]
) -> Any:
    """实例化多模态管线（config 优先，兼容不接受该关键字的假实现）。

    Args:
        pipeline_class: `MultimodalPipeline` 类或测试注入的假类。
        config: 知识库配置字典；为空则不传。

    Returns:
        可调用 `preprocess(...)` 的管线实例。

    Raises:
        Exception: 构造失败（由调用方统一转 failed）。
    """
    if config:
        try:
            return pipeline_class(config=config)
        except TypeError:
            # 假实现 / 旧签名不接受 config 关键字 → 回退无参构造
            return pipeline_class()
    return pipeline_class()


# --------------------------------------------------------------------------- #
# 文本合并与元数据
# --------------------------------------------------------------------------- #


def _normalize_text(value: Any) -> str:
    """把任意值安全转为去首尾空白的字符串（非字符串一律视为空）。"""
    return value.strip() if isinstance(value, str) else ""


def _extract_ocr_blocks(extra: Any) -> List[Any]:
    """从 `extra_metadata` 提取 OCR 文本块列表（结构异常时返回空列表）。"""
    if not isinstance(extra, dict):
        return []
    blocks = extra.get("ocr_blocks")
    if not isinstance(blocks, (list, tuple)):
        return []
    return list(blocks)


def _block_text(block: Any) -> str:
    """读取单个 OCR 文本块的 text 字段（兼容 dict 与对象两种形态）。"""
    if isinstance(block, dict):
        value = block.get("text")
    else:
        value = getattr(block, "text", None)
    return _normalize_text(value)


def _merge_text(artifact: Any) -> Tuple[str, str, int]:
    """合并 `text_content` / `vision_description` / `ocr_blocks` 为最终文本。

    合并顺序：
        1. `artifact.text_content`（非空则直接使用）；
        2. `extra_metadata.vision_description`（非空且尚未包含在文本中时追加）；
        3. `extra_metadata.ocr_blocks` 的 text 列表（仅当 `text_content` 为空时使用）。

    各片段以换行分隔并整体 strip。

    Args:
        artifact: `MultimodalArtifact`（真实或测试假实现）。

    Returns:
        (merged_text, vision_text, ocr_blocks_count)。
    """
    extra = getattr(artifact, "extra_metadata", None)
    blocks = _extract_ocr_blocks(extra)
    ocr_texts = [text for text in (_block_text(item) for item in blocks) if text]

    vision = ""
    if isinstance(extra, dict):
        vision = _normalize_text(extra.get("vision_description"))

    base = _normalize_text(getattr(artifact, "text_content", ""))

    parts: List[str] = []
    if base:
        parts.append(base)
    elif ocr_texts:
        parts.append("\n".join(ocr_texts))

    if vision and vision not in "\n".join(parts):
        parts.append(vision)

    return "\n".join(parts).strip(), vision, len(blocks)


def _safe_confidence(artifact: Any) -> float:
    """安全读取 artifact.confidence（缺失或类型异常时返回 0.0）。"""
    try:
        return float(getattr(artifact, "confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _failure(path: str, safe_mime: str, error: str) -> ParseResult:
    """构造失败结果（`failed` + `KNOWLEDGE_PARSE_FAILED`，文本为空）。

    Args:
        path: 源文件路径（写入 source_refs）。
        safe_mime: 已推断的 MIME。
        error: 错误摘要（写入 metadata["error"]，不改变 parse_error 错误码）。

    Returns:
        失败 ParseResult。
    """
    return ParseResult(
        text_content="",
        parse_status="failed",
        parse_error=KNOWLEDGE_PARSE_FAILED,
        metadata={"mime": safe_mime, "error": error},
        source_refs=[path] if path else [],
    )


# --------------------------------------------------------------------------- #
# 公开入口
# --------------------------------------------------------------------------- #


def parse_image(
    path: str,
    filename: str,
    mime: str,
    config: Optional[Dict[str, Any]] = None,
) -> ParseResult:
    """解析图片为 `ParseResult`（OCR + vision 双通道合并）。

    Args:
        path: 已落盘的图片文件路径。
        filename: 原始文件名（用于 MIME 兜底与清洗）。
        mime: 客户端上报的 MIME。
        config: 知识库配置（可选）；非空时透传给 `MultimodalPipeline` 构造。

    Returns:
        ParseResult：正常（含 vision 降级、空文本）为 `parsed`；
        文件缺失 / 管线不可用 / 任意异常为 `failed` + `KNOWLEDGE_PARSE_FAILED`。
        本函数不抛出异常。
    """
    safe_name = sanitize_filename(filename)
    safe_mime = infer_mime(safe_name, mime)

    if not path or not os.path.isfile(path):
        logger.warning("图片文件不存在: %s", path)
        return _failure(path, safe_mime, f"图片文件不存在: {path}")

    # 1. 懒加载 + 实例化（失败禁止 Mock 回退）
    try:
        pipeline_class = _load_pipeline_class()
        pipeline = _instantiate_pipeline(pipeline_class, config)
    except Exception as exc:  # noqa: BLE001 - 导入/实例化失败必须落 failed
        logger.warning("多模态管线不可用（禁止 Mock 回退）: %s", exc)
        return _failure(path, safe_mime, f"多模态管线不可用: {exc}")

    # 2. 调用图片预处理
    try:
        artifact = pipeline.preprocess(source_type="image", source_ref=path)
    except Exception as exc:  # noqa: BLE001 - 统一转 failed，不抛出
        logger.warning("图片预处理失败: %s - %s", safe_name, exc)
        return _failure(path, safe_mime, f"图片预处理失败: {exc}")

    # 3. 合并 OCR / vision 并产出元数据
    try:
        text_content, vision, ocr_blocks_count = _merge_text(artifact)
        metadata: Dict[str, Any] = {
            "vision_degraded": bool(getattr(artifact, "vision_degraded", False)),
            "confidence": _safe_confidence(artifact),
            "ocr_blocks_count": ocr_blocks_count,
            "vision_chars": len(vision),
            "chars": len(text_content),
            "mime": safe_mime,
        }
        if not text_content:
            # 空文本不报错，仅显式标记，便于上游观测
            metadata["empty_text"] = True
    except Exception as exc:  # noqa: BLE001 - 合并失败同样转 failed
        logger.warning("图片解析结果合并失败: %s - %s", safe_name, exc)
        return _failure(path, safe_mime, f"图片解析结果合并失败: {exc}")

    return ParseResult(
        text_content=text_content,
        parse_status="parsed",
        parse_error=None,
        metadata=metadata,
        source_refs=[path],
    )
