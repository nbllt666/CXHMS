"""模块11 独立知识库数据模型。

字段与 `public/schema/knowledge.json` 的 `knowledge_document` / `knowledge_item` /
`knowledge_search_hit` 三个 definition 逐一对齐（@version 1.0.0）。

设计边界：
- 本文件只做**数据承载与行转换**，不承担任何 SQL / 校验 / 业务逻辑；
- `to_dict()` 返回的字典字段集严格等于数据契约字段集（`additionalProperties: false`），
  不附加 `deduplicated` 等 API 语义字段（该字段由存储层在返回值外层补充）；
- `from_row()` 同时兼容 `sqlite3.Row`、`dict` 与任意支持 `__getitem__` 的映射，
  并对 `metadata` / `tags` 的 JSON 文本做容错解析（脏数据降级为空值，不抛异常）。

@see backend/core/knowledge/store.py
@see public/schema/knowledge.json
"""

import copy
import json
from dataclasses import dataclass, field

# 数据契约字段顺序（to_dict 输出顺序，便于人工比对 schema）
DOCUMENT_FIELDS = (
    "document_id",
    "agent_id",
    "filename",
    "mime",
    "size_bytes",
    "sha256",
    "parse_status",
    "created_at",
    "storage_path",
    "parse_error",
    "metadata",
    "updated_at",
    "is_deleted",
)

ITEM_FIELDS = (
    "item_id",
    "agent_id",
    "item_type",
    "content",
    "fingerprint",
    "created_at",
    "document_id",
    "title",
    "tags",
    "importance",
    "chunk_index",
    "updated_at",
    "is_deleted",
)

SEARCH_HIT_FIELDS = (
    "item_id",
    "title",
    "content",
    "score",
    "item_type",
    "document_id",
    "tags",
)


def _row_value(row: object, key: str, default: object = None) -> object:
    """从行对象安全取值；键不存在或为 NULL 时返回 default。

    Args:
        row: sqlite3.Row / dict / 其他映射
        key: 字段名
        default: 缺失或 NULL 时的回退值

    Returns:
        字段值或 default
    """
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    if value is None:
        return default
    return value


def _load_json(value: object, default: object) -> object:
    """容错解析 JSON 文本字段。

    Args:
        value: 已是 list/dict 时直接返回；None/空串或非法 JSON 时返回 default 的深拷贝
        default: 回退值（dict 或 list）

    Returns:
        解析后的对象
    """
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return copy.deepcopy(default)
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return copy.deepcopy(default)
    try:
        parsed = json.loads(str(value))
    except (ValueError, TypeError):
        return copy.deepcopy(default)
    if not isinstance(parsed, type(default)):
        return copy.deepcopy(default)
    return parsed


def _as_int(value: object, default: int = 0) -> int:
    """把行值安全转换为 int（空值/非法值返回 default）。"""
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class KnowledgeDocument:
    """知识库文档实体（对应 `knowledge_documents` 表 / `knowledge_document` 契约）。"""

    document_id: str
    agent_id: str
    filename: str
    mime: str
    size_bytes: int
    sha256: str
    parse_status: str
    created_at: str
    storage_path: str | None = None
    parse_error: str | None = None
    metadata: dict = field(default_factory=dict)
    updated_at: str | None = None
    is_deleted: int = 0

    def to_dict(self) -> dict:
        """转换为数据契约字段集字典（metadata 做浅拷贝避免外部污染）。"""
        return {
            "document_id": self.document_id,
            "agent_id": self.agent_id,
            "filename": self.filename,
            "mime": self.mime,
            "size_bytes": int(self.size_bytes),
            "sha256": self.sha256,
            "parse_status": self.parse_status,
            "created_at": self.created_at,
            "storage_path": self.storage_path,
            "parse_error": self.parse_error,
            "metadata": dict(self.metadata or {}),
            "updated_at": self.updated_at,
            "is_deleted": int(self.is_deleted),
        }

    @classmethod
    def from_row(cls, row: object) -> "KnowledgeDocument":
        """从 SQLite 行对象构造文档实体（JSON 字段容错解析）。"""
        return cls(
            document_id=str(_row_value(row, "document_id", "")),
            agent_id=str(_row_value(row, "agent_id", "")),
            filename=str(_row_value(row, "filename", "")),
            mime=str(_row_value(row, "mime", "")),
            size_bytes=_as_int(_row_value(row, "size_bytes", 0), 0),
            sha256=str(_row_value(row, "sha256", "")),
            parse_status=str(_row_value(row, "parse_status", "pending")),
            created_at=str(_row_value(row, "created_at", "")),
            storage_path=_row_value(row, "storage_path", None),
            parse_error=_row_value(row, "parse_error", None),
            metadata=_load_json(_row_value(row, "metadata", None), {}),
            updated_at=_row_value(row, "updated_at", None),
            is_deleted=_as_int(_row_value(row, "is_deleted", 0), 0),
        )


@dataclass
class KnowledgeItem:
    """知识条目实体（对应 `knowledge_items` 表 / `knowledge_item` 契约）。"""

    item_id: str
    agent_id: str
    item_type: str
    content: str
    fingerprint: str
    created_at: str
    document_id: str | None = None
    title: str | None = None
    tags: list[str] = field(default_factory=list)
    importance: int = 3
    chunk_index: int | None = None
    updated_at: str | None = None
    is_deleted: int = 0

    def to_dict(self) -> dict:
        """转换为数据契约字段集字典。"""
        return {
            "item_id": self.item_id,
            "agent_id": self.agent_id,
            "item_type": self.item_type,
            "content": self.content,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "document_id": self.document_id,
            "title": self.title,
            "tags": list(self.tags or []),
            "importance": int(self.importance),
            "chunk_index": None if self.chunk_index is None else int(self.chunk_index),
            "updated_at": self.updated_at,
            "is_deleted": int(self.is_deleted),
        }

    @classmethod
    def from_row(cls, row: object) -> "KnowledgeItem":
        """从 SQLite 行对象构造条目实体（JSON 字段容错解析）。"""
        raw_chunk_index = _row_value(row, "chunk_index", None)
        return cls(
            item_id=str(_row_value(row, "item_id", "")),
            agent_id=str(_row_value(row, "agent_id", "")),
            item_type=str(_row_value(row, "item_type", "doc_chunk")),
            content=str(_row_value(row, "content", "")),
            fingerprint=str(_row_value(row, "fingerprint", "")),
            created_at=str(_row_value(row, "created_at", "")),
            document_id=_row_value(row, "document_id", None),
            title=_row_value(row, "title", None),
            tags=[str(tag) for tag in _load_json(_row_value(row, "tags", None), [])],
            importance=_as_int(_row_value(row, "importance", 3), 3),
            chunk_index=(
                None if raw_chunk_index in (None, "") else _as_int(raw_chunk_index, 0)
            ),
            updated_at=_row_value(row, "updated_at", None),
            is_deleted=_as_int(_row_value(row, "is_deleted", 0), 0),
        )


@dataclass
class SearchHit:
    """知识库检索命中实体（`knowledge_search_hit` 契约的存储层简化视图）。"""

    item_id: str
    content: str
    score: float
    item_type: str
    title: str | None = None
    document_id: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为命中字典（供 API 层补 agent_id 等字段）。"""
        return {
            "item_id": self.item_id,
            "title": self.title,
            "content": self.content,
            "score": float(self.score),
            "item_type": self.item_type,
            "document_id": self.document_id,
            "tags": list(self.tags or []),
        }

    @classmethod
    def from_row(cls, row: object, score: float = 0.0) -> "SearchHit":
        """从 SQLite 行对象构造命中实体；score 由检索层计算后注入。"""
        return cls(
            item_id=str(_row_value(row, "item_id", "")),
            content=str(_row_value(row, "content", "")),
            score=score if score is not None else _row_value(row, "score", 0.0),
            item_type=str(_row_value(row, "item_type", "doc_chunk")),
            title=_row_value(row, "title", None),
            document_id=_row_value(row, "document_id", None),
            tags=[str(tag) for tag in _load_json(_row_value(row, "tags", None), [])],
        )
