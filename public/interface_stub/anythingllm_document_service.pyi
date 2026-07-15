"""AnythingLLM Document API 接口契约存根。

定义 7 个 Document 端点签名 + search_all_memories 方法签名。
实现必须严格匹配此存根定义的签名，否则契约测试不通过。

端点清单（7个）：
  1. POST   /api/v1/document/upload                          — 上传文件
  2. POST   /api/v1/document/raw-text                        — 通过文本创建文档
  3. GET    /api/v1/documents                                — 列出所有文档
  4. GET    /api/v1/document/{docName}                       — 获取单个文档
  5. DELETE /api/v1/document/{docName}                       — 删除文档
  6. POST   /api/v1/workspace/{slug}/update-embeddings       — 管理 workspace 文档关联
  7. GET    /api/v1/document/metadata-schema                 — 获取元数据 schema

MemoryManager 扩展方法：
  - search_all_memories(query, workspace_id, limit)          — 同时查询 memories 与 permanent_memories

@version 1.0.0
@see public/schema/anythingllm_document.json
@see public/config_template/anythingllm_document_config.json
"""

from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """文档响应结构。

    字段定义与 public/schema/anythingllm_document.json 一致。
    """
    doc_name: str
    title: str
    doc_author: str
    description: str
    doc_source: Optional[str]
    mime_type: Optional[str]
    word_count: int
    token_count_estimate: int
    text_content: Optional[str]
    memory_id: Optional[int]
    folder: str
    file_path: Optional[str]
    created_at: str
    updated_at: Optional[str]
    is_deleted: bool


class UploadResponse(BaseModel):
    """上传响应。"""
    success: bool
    documents: List[Dict[str, Any]]


class RawTextRequest(BaseModel):
    """文本上传请求。"""
    textContent: str
    metadata: Dict[str, Any]
    addToWorkspaces: Optional[str] = None


class UpdateEmbeddingsRequest(BaseModel):
    """workspace 文档关联请求。"""
    adds: List[str]
    deletes: List[str]


class MetadataSchemaResponse(BaseModel):
    """元数据 schema 响应。"""
    schema: Dict[str, str]


# ===== 7 个 Document 端点签名 =====

async def upload_document(
    file: UploadFile,
    addToWorkspaces: Optional[str] = None,
    metadata: Optional[str] = None,
) -> UploadResponse:
    """POST /api/v1/document/upload — 上传文件。

    Args:
        file: 上传的文件（FastAPI UploadFile）
        addToWorkspaces: 可选，加入指定 workspace slug
        metadata: 可选，自定义元数据（multipart 场景下以 JSON 字符串形式传递，
            实现层在函数体内 ``json.loads(metadata)`` 解析为 dict；FastAPI Form
            不支持 Dict 类型，故存根声明为 str 以严格匹配实现签名）

    Returns:
        UploadResponse: {success: bool, documents: List[Dict]}

    Raises:
        HTTPException(413): 文件超过大小限制（max_file_size 配置项）
        HTTPException(500): 内部错误（解析失败 / IO 异常）
    """
    ...


async def upload_raw_text(
    request: RawTextRequest,
) -> UploadResponse:
    """POST /api/v1/document/raw-text — 通过文本创建文档。

    Args:
        request: {textContent: str, metadata: Dict, addToWorkspaces: Optional[str]}

    Returns:
        UploadResponse: {success: bool, documents: List[Dict]}

    Raises:
        HTTPException(500): 内部错误（解析失败 / 数据库写入失败）
    """
    ...


async def list_documents() -> Dict[str, Any]:
    """GET /api/v1/documents — 列出所有文档。

    Returns:
        {"localFiles": {"name": "documents", "type": "folder", "items": [...]}}

    Note:
        不抛出 HTTPException；空列表时返回空 items 数组。
    """
    ...


async def get_document(docName: str) -> Dict[str, Any]:
    """GET /api/v1/document/{docName} — 获取单个文档。

    Args:
        docName: 文档唯一名（{title}-{uuid}.json）

    Returns:
        文档详情 dict（字段符合 public/schema/anythingllm_document.json）

    Raises:
        HTTPException(404): 文档不存在
    """
    ...


async def delete_document(docName: str) -> Dict[str, bool]:
    """DELETE /api/v1/document/{docName} — 删除文档。

    Args:
        docName: 文档唯一名

    Returns:
        {"success": true} 或 {"success": false}

    Raises:
        HTTPException(404): 文档不存在
    """
    ...


async def update_workspace_embeddings(
    slug: str,
    request: UpdateEmbeddingsRequest,
) -> Dict[str, Any]:
    """POST /api/v1/workspace/{slug}/update-embeddings — 管理 workspace 文档关联。

    Args:
        slug: workspace slug（= agent_id）
        request: {adds: List[str], deletes: List[str]}

    Returns:
        {"success": true, "added": [...], "removed": [...]}

    Raises:
        HTTPException(404): workspace 不存在
    """
    ...


async def get_metadata_schema() -> MetadataSchemaResponse:
    """GET /api/v1/document/metadata-schema — 获取元数据 schema。

    Returns:
        MetadataSchemaResponse: {"schema": {field_name: field_type, ...}}

    Note:
        不抛出 HTTPException。
    """
    ...


# ===== MemoryManager 扩展方法签名 =====

def search_all_memories(
    query: str,
    workspace_id: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """同时查询 memories 表和 permanent_memories 表，合并结果返回。

    Args:
        query: 搜索关键词
        workspace_id: 工作区ID（仅用于 memories 表过滤；permanent_memories 不按 workspace 过滤）
        limit: 返回数量限制（合并后取前 N 条）

    Returns:
        合并后的记忆列表，每条记录附带 _source_table 字段（值为 'memories' 或 'permanent_memories'）

    Raises:
        sqlite3.Error: 数据库查询失败
    """
    ...
