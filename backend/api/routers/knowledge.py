"""模块11 独立知识库 API 路由（`/api/knowledge/*`）。

端点（10 个）：
- GET    /knowledge/health
- POST   /knowledge/upload
- POST   /knowledge/entries
- GET    /knowledge/items
- GET    /knowledge/items/{item_id}
- DELETE /knowledge/items/{item_id}
- POST   /knowledge/search
- GET    /knowledge/documents
- GET    /knowledge/documents/{document_id}
- DELETE /knowledge/documents/{document_id}

错误语义：
- 413 上传体积超限（流式写盘阶段拦截，不落库）
- 415 MIME 不在白名单
- 422 请求体/表单校验失败（FastAPI 默认）
- 503 `enabled=false` 或存储不可用（KnowledgeStoreError → 全局 handler）
"""

import json
import logging
import os
import tempfile
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend.core.knowledge.exceptions import KnowledgeUnsupportedMediaError
from backend.core.knowledge.parsers.base import classify_mime, infer_mime
from backend.dependencies import get_knowledge_manager, get_knowledge_registry

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)

_READ_CHUNK_BYTES = 1024 * 1024


class ExperienceCreateRequest(BaseModel):
    """写入经验条目请求。"""

    agent_id: str = "default"
    title: Optional[str] = None
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    importance: int = 3


class KnowledgeSearchRequest(BaseModel):
    """混合检索请求。"""

    agent_id: str = "default"
    query: str = Field(..., min_length=1)
    top_k: int = 8
    tags: Optional[list[str]] = None
    item_type: Optional[str] = None


def _parse_tags(raw: Optional[str]) -> list[str]:
    """解析 multipart 中的 tags 字段（JSON 数组或逗号分隔）。"""
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in text.split(",") if item.strip()]


def _resolve_media_category(manager: Any, filename: str, content_type: str) -> tuple[str, str]:
    """推断 MIME 并校验白名单，返回 `(mime, category)`。"""
    mime = infer_mime(filename, content_type)
    category = classify_mime(mime)
    whitelist = manager.config.get(f"allowed_{category}_mimes", []) if category else []
    if category == "unsupported" or mime not in [str(item) for item in whitelist]:
        raise KnowledgeUnsupportedMediaError(
            f"不支持的 MIME 类型: {mime}",
            {"mime": mime, "filename": filename},
        )
    return mime, category


async def _stream_to_temp(upload: UploadFile, limit_mb: int) -> tuple[str, str]:
    """流式落盘到临时文件并执行体积上限校验。

    Returns:
        `(temporary_path, original_filename)`

    Raises:
        HTTPException: 413 当上传体积超过 `limit_mb`
    """
    filename = os.path.basename(str(upload.filename or "upload.bin"))
    suffix = os.path.splitext(filename)[1]
    limit_bytes = max(1, int(limit_mb)) * 1024 * 1024
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    total = 0
    try:
        while True:
            block = await upload.read(_READ_CHUNK_BYTES)
            if not block:
                break
            total += len(block)
            if total > limit_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件超出大小限制（{int(limit_mb)}MB）",
                )
            handle.write(block)
        handle.flush()
    except Exception:
        handle.close()
        try:
            os.remove(handle.name)
        except OSError:
            pass
        raise
    handle.close()
    return handle.name, filename


@router.get("/health")
async def knowledge_health(manager: Any = Depends(get_knowledge_manager)) -> dict:
    """知识库健康状态（enabled / 向量 / FTS / ASR / ffmpeg）。"""
    return manager.health()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    agent_id: str = Form("default"),
    tags: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    registry: Any = Depends(get_knowledge_registry),
) -> dict:
    """上传文档/图片/音视频：返回 pending 记录，解析在后台执行。"""
    manager = registry.get_manager(agent_id)
    filename = os.path.basename(str(file.filename or "upload.bin"))
    mime, category = _resolve_media_category(manager, filename, file.content_type or "")
    limit_mb = int(
        manager.config["max_document_size_mb"]
        if category == "document"
        else manager.config["max_media_size_mb"]
    )

    temporary_path, filename = await _stream_to_temp(file, limit_mb)
    try:
        stored = manager.intake_document(
            filename=filename,
            mime=mime,
            source_path=temporary_path,
            tags=_parse_tags(tags),
            title=title,
        )
    finally:
        try:
            os.remove(temporary_path)
        except OSError:
            pass

    if not stored.get("deduplicated"):
        background_tasks.add_task(manager.process_document, stored["document_id"])
    return {
        "document_id": stored["document_id"],
        "parse_status": stored.get("parse_status", "pending"),
        "deduplicated": bool(stored.get("deduplicated")),
    }


@router.post("/entries")
async def create_entry(
    payload: ExperienceCreateRequest,
    registry: Any = Depends(get_knowledge_registry),
) -> dict:
    """写入经验条目（`item_type=experience`）。"""
    manager = registry.get_manager(payload.agent_id)
    return await manager.add_experience(
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        importance=payload.importance,
    )


@router.get("/items")
async def list_items(
    item_type: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    manager: Any = Depends(get_knowledge_manager),
) -> dict:
    """分页列出知识条目（支持类型/标签/关键词过滤）。"""
    tag_list = _parse_tags(tags)
    return manager.list_items(
        item_type=item_type, tags=tag_list, q=q, limit=limit, offset=offset
    )


@router.get("/items/{item_id}")
async def get_item(item_id: str, manager: Any = Depends(get_knowledge_manager)) -> dict:
    """条目详情。"""
    item = manager.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return item


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: str, manager: Any = Depends(get_knowledge_manager)
) -> dict:
    """软删除条目并删除其向量。"""
    success = await manager.delete_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return {"success": True}


@router.post("/search")
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    registry: Any = Depends(get_knowledge_registry),
) -> dict:
    """混合检索（向量 + FTS，RRF 融合；向量不可用时 fallback=true）。"""
    manager = registry.get_manager(payload.agent_id)
    hits = await manager.search(
        query=payload.query,
        top_k=payload.top_k,
        tags=payload.tags,
        item_type=payload.item_type,
    )
    return {
        "hits": hits,
        "total": len(hits),
        "fallback": bool(getattr(manager, "last_search_fallback", False)),
    }


@router.get("/documents")
async def list_documents(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    manager: Any = Depends(get_knowledge_manager),
) -> dict:
    """文档列表与解析状态。"""
    return manager.list_documents(limit=limit, offset=offset)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str, manager: Any = Depends(get_knowledge_manager)
) -> dict:
    """文档详情（解析状态 + 文本预览 + 分块数）。"""
    document = manager.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    metadata = document.get("metadata") or {}
    result = dict(document)
    result["text_preview"] = metadata.get("preview")
    result["chunk_count"] = int(metadata.get("chunk_count") or 0)
    return result


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str, manager: Any = Depends(get_knowledge_manager)
) -> dict:
    """删除文档（级联删分块、向量与物理文件）。"""
    success = await manager.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识文档不存在")
    return {"success": True}
