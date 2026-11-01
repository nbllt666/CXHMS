"""模块11 独立知识库 SQLite 存储层。

职责（严格对齐 `spec.md`「冻结的 SQLite 结构」与「文本读取与流式边界」）：
- 每线程独立 SQLite 连接（`threading.local`），WAL 模式，禁止跨线程复用同一连接；
- 建表 `knowledge_documents` / `knowledge_items` / `knowledge_items_fts`；
- FTS5 使用 `tokenize='trigram'`，建表失败时置 `_fts5_available=False` 并降级 LIKE；
- 写入前按 `public/schema/knowledge.json` 用 `jsonschema` 校验，不合规抛
  `KnowledgeValidationError` 且不落库（rules-3 §一 validation）；
- 指纹语义：`doc_chunk` = md5(document_id:chunk_index:规范化内容)，
  `experience` = md5(规范化内容)；规范化 = strip + 压缩连续空白；
- 全部 SQL 参数化；tags 以 JSON 文本存储、Python 侧精确过滤。

路径解析（rules-0 §三）：禁止相对路径与 `..`，全部由
`os.path.dirname(os.path.abspath(__file__))` 逐级向上推导绝对路径。

契约字段见 `public/schema/knowledge.json`，实体见 `models.py`。
"""

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

try:
    import jsonschema
except ImportError:  # pragma: no cover - requirements 由 Task 5 保证安装
    jsonschema = None

from backend.core.knowledge.exceptions import (
    KnowledgeStoreError,
    KnowledgeValidationError,
)
from backend.core.knowledge.models import (
    KnowledgeDocument,
    KnowledgeItem,
    SearchHit,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 绝对路径锚点（禁止相对路径 / ".."）
# --------------------------------------------------------------------------- #
_KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.dirname(_KNOWLEDGE_DIR)
_BACKEND_DIR = os.path.dirname(_CORE_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_SCHEMA_PATH = os.path.join(_PROJECT_ROOT, "public", "schema", "knowledge.json")

_WHITESPACE_RE = re.compile(r"\s+")

_DOCUMENT_COLUMNS = (
    "document_id",
    "agent_id",
    "filename",
    "mime",
    "size_bytes",
    "sha256",
    "storage_path",
    "parse_status",
    "parse_error",
    "metadata",
    "created_at",
    "updated_at",
    "is_deleted",
)

_ITEM_COLUMNS = (
    "item_id",
    "agent_id",
    "document_id",
    "item_type",
    "title",
    "content",
    "tags",
    "importance",
    "chunk_index",
    "fingerprint",
    "created_at",
    "updated_at",
    "is_deleted",
)


def _iso_now() -> str:
    """返回 ISO 8601（UTC）时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


def normalize_content(content: str) -> str:
    """规范化内容：strip + 压缩连续空白（指纹计算专用）。"""
    return _WHITESPACE_RE.sub(" ", str(content or "")).strip()


def compute_fingerprint(
    item_type: str,
    content: str,
    document_id: str | None = None,
    chunk_index: int | None = None,
) -> str:
    """按冻结规则计算内容指纹。

    Args:
        item_type: `doc_chunk` / `experience`
        content: 条目正文
        document_id: doc_chunk 的来源文档 ID
        chunk_index: doc_chunk 的分块序号

    Returns:
        32 位 MD5 十六进制指纹
    """
    normalized = normalize_content(content)
    if item_type == "doc_chunk":
        doc_part = "" if document_id is None else str(document_id)
        index_part = "" if chunk_index is None else str(chunk_index)
        seed = f"{doc_part}:{index_part}:{normalized}"
    else:
        seed = normalized
    return hashlib.md5(seed.encode("utf-8")).hexdigest()


def _load_json_value(value: object, default: object) -> object:
    """JSON 文本容错解析（空值/非法 JSON 回退 default）。"""
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return default
    if not isinstance(parsed, type(default)):
        return default
    return parsed


def _parse_tags(value: object) -> list[str]:
    """把 tags 列解析为字符串列表。"""
    raw = _load_json_value(value, [])
    if not isinstance(raw, list):
        return []
    return [str(tag) for tag in raw]


def _matches_tags(row: object, tags: list[str] | None) -> bool:
    """判断行 tags 是否包含全部筛选标签（子集语义）。"""
    if not tags:
        return True
    row_tags = set(_parse_tags(row["tags"]))
    return set(tags).issubset(row_tags)


def _like_pattern(term: str) -> str:
    """构造转义后的 LIKE 模式（% 与 _ 转义，配合 ESCAPE '\\'）。"""
    escaped = (
        str(term).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _bigram_terms(query: str) -> list[str]:
    """2 字滑窗切分（去重保序），用于 trigram 空命中与短查询兜底。"""
    text = str(query or "").strip()
    if len(text) < 2:
        return []
    terms = []
    seen = set()
    for index in range(len(text) - 1):
        term = text[index:index + 2]
        if term.strip() and term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _trigram_expression(query: str) -> str:
    """构造 FTS5 trigram OR 查询表达式（每个 trigram 用引号包裹）。"""
    safe = str(query or "")[:500].replace('"', '""')
    trigrams = []
    seen = set()
    for index in range(len(safe) - 2):
        term = safe[index:index + 3]
        if term not in seen:
            seen.add(term)
            trigrams.append(term)
    return " OR ".join(f'"{term}"' for term in trigrams)


class KnowledgeStore:
    """知识库 SQLite 存储（单 agent 一库，路径由调用方注入）。"""

    def __init__(self, db_path: str):
        """初始化存储：建立连接、表结构与契约校验器。

        Args:
            db_path: 数据库文件绝对路径（外部注入，不在内部推导）
        """
        if not db_path:
            raise KnowledgeStoreError("db_path 不能为空")
        self.db_path = str(db_path)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._fts5_available = False

        parent_dir = os.path.dirname(os.path.abspath(self.db_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        self._schema = self._load_contract_schema()
        self._document_schema = self._build_ref_schema("knowledge_document")
        self._item_schema = self._build_ref_schema("knowledge_item")
        self._init_db()

    # ------------------------------------------------------------------ #
    # 契约校验
    # ------------------------------------------------------------------ #
    def _load_contract_schema(self) -> dict:
        """加载 `public/schema/knowledge.json`（绝对路径）。"""
        try:
            with open(_SCHEMA_PATH, "r", encoding="utf-8") as handle:
                schema = json.load(handle)
        except (OSError, ValueError) as exc:
            raise KnowledgeStoreError(
                f"加载数据契约失败: {_SCHEMA_PATH}", {"error": str(exc)}
            ) from exc
        if not isinstance(schema, dict) or not isinstance(schema.get("definitions"), dict):
            raise KnowledgeStoreError(f"数据契约结构非法: {_SCHEMA_PATH}")
        return schema

    def _build_ref_schema(self, definition: str) -> dict:
        """按契约 definitions 构造单实体校验子 Schema。"""
        definitions = self._schema.get("definitions", {})
        if definition not in definitions:
            raise KnowledgeStoreError(f"数据契约缺少 definition: {definition}")
        return {
            "$schema": self._schema.get(
                "$schema", "http://json-schema.org/draft-07/schema#"
            ),
            "definitions": definitions,
            "$ref": f"#/definitions/{definition}",
        }

    def _validate(self, instance: dict, definition: str, schema: dict) -> None:
        """按契约校验实体；不合规抛 `KnowledgeValidationError`（不落库）。"""
        if jsonschema is None:
            raise KnowledgeStoreError("jsonschema 未安装，无法执行契约校验")
        try:
            jsonschema.validate(instance=instance, schema=schema)
        except jsonschema.ValidationError as exc:
            path = "/".join(str(part) for part in exc.absolute_path) or "<root>"
            raise KnowledgeValidationError(
                f"{definition} 不符合数据契约: {exc.message} (path={path})",
                {
                    "definition": definition,
                    "path": list(exc.absolute_path),
                    "validator": exc.validator,
                },
            ) from exc
        except jsonschema.SchemaError as exc:  # pragma: no cover - 契约自身损坏
            raise KnowledgeStoreError(
                f"数据契约自身非法: {definition}", {"error": str(exc)}
            ) from exc

    # ------------------------------------------------------------------ #
    # 连接与建表
    # ------------------------------------------------------------------ #
    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程独占连接（失效连接自动重建）。"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                self._safe_close(conn)
                self._local.conn = None

        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
        except sqlite3.Error as exc:
            raise KnowledgeStoreError(
                f"打开知识库失败: {self.db_path}", {"error": str(exc)}
            ) from exc
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
        except sqlite3.Error as exc:  # pragma: no cover - 文件系统异常
            logger.warning("设置 SQLite PRAGMA 失败: %s", exc)
        self._local.conn = conn
        return conn

    @staticmethod
    def _safe_close(conn: sqlite3.Connection | None) -> None:
        """静默关闭连接（不抛异常）。"""
        if conn is None:
            return
        try:
            conn.close()
        except sqlite3.Error:  # pragma: no cover
            pass

    def close(self) -> None:
        """关闭当前线程连接（供测试 fixture / 管理器关闭使用，可重复调用）。"""
        conn = getattr(self._local, "conn", None)
        self._safe_close(conn)
        self._local.conn = None

    def _init_db(self) -> None:
        """建表、建索引、建 FTS5 表并回填索引。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                document_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                storage_path TEXT,
                parse_status TEXT NOT NULL,
                parse_error TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                is_deleted INTEGER DEFAULT 0,
                UNIQUE(agent_id, sha256)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_items (
                item_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                document_id TEXT,
                item_type TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                tags TEXT,
                importance INTEGER DEFAULT 3,
                chunk_index INTEGER,
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                is_deleted INTEGER DEFAULT 0,
                UNIQUE(agent_id, fingerprint)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_deleted "
            "ON knowledge_documents(is_deleted)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_items_deleted "
            "ON knowledge_items(is_deleted)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_items_document "
            "ON knowledge_items(document_id)"
        )
        conn.commit()

        self._init_fts(cursor)
        conn.commit()

    def _init_fts(self, cursor: sqlite3.Cursor) -> None:
        """创建 FTS5 trigram 表；失败则降级 LIKE（`_fts5_available=False`）。"""
        try:
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='knowledge_items_fts'"
            )
            existing = cursor.fetchone()
            if existing and existing[0] and "trigram" not in existing[0]:
                # 旧表使用非 trigram 分词器（中文整体作 token）→ 重建
                cursor.execute("DROP TABLE knowledge_items_fts")
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_items_fts USING fts5(
                    item_id UNINDEXED,
                    title,
                    content,
                    tags,
                    tokenize='trigram'
                )
                """
            )
            # 回填：清理已软删除/已不存在的索引行，补齐缺失行（幂等）
            cursor.execute(
                "DELETE FROM knowledge_items_fts WHERE item_id NOT IN "
                "(SELECT item_id FROM knowledge_items WHERE is_deleted = 0)"
            )
            cursor.execute(
                "INSERT INTO knowledge_items_fts(item_id, title, content, tags) "
                "SELECT item_id, title, content, tags FROM knowledge_items "
                "WHERE is_deleted = 0 AND item_id NOT IN "
                "(SELECT item_id FROM knowledge_items_fts)"
            )
            self._fts5_available = True
        except sqlite3.Error as exc:
            self._fts5_available = False
            logger.warning(
                "FTS5 trigram 不可用，keyword_search 将降级 LIKE 全表扫: %s", exc
            )

    # ------------------------------------------------------------------ #
    # 文档
    # ------------------------------------------------------------------ #
    def _normalize_document(self, record: dict) -> dict:
        """规范化文档记录：补 schema 默认值并裁剪多余字段。"""
        metadata = _load_json_value(record.get("metadata"), {})
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "document_id": record.get("document_id"),
            "agent_id": record.get("agent_id"),
            "filename": record.get("filename"),
            "mime": record.get("mime"),
            "size_bytes": record.get("size_bytes"),
            "sha256": record.get("sha256"),
            "storage_path": record.get("storage_path"),
            "parse_status": record.get("parse_status"),
            "parse_error": record.get("parse_error"),
            "metadata": metadata,
            "created_at": record.get("created_at") or _iso_now(),
            "updated_at": record.get("updated_at"),
            "is_deleted": int(record.get("is_deleted") or 0),
        }

    def upsert_document(self, record: dict) -> dict:
        """写入文档记录；同 agent 内 SHA-256 冲突时返回既有记录。

        Args:
            record: 文档记录（字段对齐 `knowledge_document`）

        Returns:
            文档字典；冲突/复活时附 `deduplicated` 标记

        Raises:
            KnowledgeValidationError: 记录不符合数据契约
            KnowledgeStoreError: 数据库写入失败
        """
        normalized = self._normalize_document(dict(record or {}))
        self._validate(normalized, "knowledge_document", self._document_schema)

        document = KnowledgeDocument.from_row(normalized)
        payload = document.to_dict()

        with self._write_lock:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT * FROM knowledge_documents WHERE agent_id = ? AND sha256 = ?",
                    (normalized["agent_id"], normalized["sha256"]),
                ).fetchone()
                if existing is not None and int(existing["is_deleted"] or 0) == 0:
                    result = KnowledgeDocument.from_row(existing).to_dict()
                    result["deduplicated"] = True
                    return result

                columns = ", ".join(_DOCUMENT_COLUMNS)
                placeholders = ", ".join("?" for _ in _DOCUMENT_COLUMNS)
                values = [
                    json.dumps(payload["metadata"], ensure_ascii=False)
                    if column == "metadata"
                    else payload[column]
                    for column in _DOCUMENT_COLUMNS
                ]
                if existing is not None:
                    # 软删除后再次上传同内容：复活既有行（UNIQUE 约束不可再插）
                    assignments = ", ".join(
                        f"{column} = ?" for column in _DOCUMENT_COLUMNS
                    )
                    conn.execute(
                        f"UPDATE knowledge_documents SET {assignments} "
                        f"WHERE document_id = ?",
                        values + [existing["document_id"]],
                    )
                else:
                    conn.execute(
                        f"INSERT INTO knowledge_documents ({columns}) "
                        f"VALUES ({placeholders})",
                        values,
                    )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise KnowledgeStoreError(
                    "写入知识文档失败", {"error": str(exc), "db_path": self.db_path}
                ) from exc

        result = dict(payload)
        result["deduplicated"] = False
        return result

    def get_document(self, document_id: str) -> dict | None:
        """按 document_id 查询未删除文档；不存在返回 None。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM knowledge_documents WHERE document_id = ? AND is_deleted = 0",
            (str(document_id),),
        ).fetchone()
        return None if row is None else KnowledgeDocument.from_row(row).to_dict()

    def list_documents(self, limit: int = 20, offset: int = 0) -> dict:
        """分页列出未删除文档（created_at 倒序）。"""
        page_limit = max(0, int(limit))
        page_offset = max(0, int(offset))
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(1) FROM knowledge_documents WHERE is_deleted = 0"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM knowledge_documents WHERE is_deleted = 0 "
            "ORDER BY created_at DESC, document_id ASC LIMIT ? OFFSET ?",
            (page_limit, page_offset),
        ).fetchall()
        return {
            "documents": [KnowledgeDocument.from_row(row).to_dict() for row in rows],
            "total": int(total),
            "limit": page_limit,
            "offset": page_offset,
        }

    def soft_delete_document(self, document_id: str) -> bool:
        """软删除文档，并级联软删除其全部条目（含 FTS 索引清理）。

        Returns:
            是否发生删除（已删除或不存在返回 False）
        """
        target = str(document_id)
        with self._write_lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "UPDATE knowledge_documents SET is_deleted = 1, updated_at = ? "
                    "WHERE document_id = ? AND is_deleted = 0",
                    (_iso_now(), target),
                )
                deleted = cursor.rowcount > 0
                if deleted:
                    self._soft_delete_items_locked(conn, document_id=target)
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise KnowledgeStoreError(
                    "软删除知识文档失败", {"error": str(exc)}
                ) from exc
            return deleted

    # ------------------------------------------------------------------ #
    # 条目
    # ------------------------------------------------------------------ #
    def _normalize_item(self, record: dict) -> dict:
        """规范化条目记录：计算指纹、补默认值并裁剪多余字段。"""
        item_type = str(record.get("item_type") or "")
        content = "" if record.get("content") is None else str(record.get("content"))
        raw_tags = record.get("tags")
        if raw_tags is None:
            tags = []
        elif isinstance(raw_tags, str):
            tags = [raw_tags]
        else:
            tags = [str(tag) for tag in raw_tags]

        raw_chunk_index = record.get("chunk_index")
        chunk_index = None
        if raw_chunk_index not in (None, ""):
            try:
                chunk_index = int(raw_chunk_index)
            except (TypeError, ValueError) as exc:
                raise KnowledgeValidationError(
                    "chunk_index 必须为整数或 null",
                    {"chunk_index": raw_chunk_index},
                ) from exc

        try:
            importance = 3 if record.get("importance") is None else int(
                record.get("importance")
            )
        except (TypeError, ValueError) as exc:
            raise KnowledgeValidationError(
                "importance 必须为 1..5 的整数", {"importance": record.get("importance")}
            ) from exc

        fingerprint = compute_fingerprint(
            item_type=item_type,
            content=content,
            document_id=record.get("document_id"),
            chunk_index=chunk_index,
        )

        return {
            "item_id": record.get("item_id"),
            "agent_id": record.get("agent_id"),
            "item_type": item_type,
            "content": content,
            "fingerprint": fingerprint,
            "created_at": record.get("created_at") or _iso_now(),
            "document_id": record.get("document_id"),
            "title": record.get("title"),
            "tags": tags,
            "importance": importance,
            "chunk_index": chunk_index,
            "updated_at": record.get("updated_at"),
            "is_deleted": int(record.get("is_deleted") or 0),
        }

    def _sync_fts_row(self, conn: sqlite3.Connection, payload: dict) -> None:
        """同步单条 FTS 索引（软删除时移除；FTS 不可用时无操作）。"""
        if not self._fts5_available:
            return
        try:
            conn.execute(
                "DELETE FROM knowledge_items_fts WHERE item_id = ?",
                (payload["item_id"],),
            )
            if int(payload.get("is_deleted") or 0) == 0:
                conn.execute(
                    "INSERT INTO knowledge_items_fts(item_id, title, content, tags) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        payload["item_id"],
                        payload["title"],
                        payload["content"],
                        json.dumps(payload["tags"], ensure_ascii=False),
                    ),
                )
        except sqlite3.Error as exc:  # pragma: no cover - 索引写失败降级
            logger.warning("同步 FTS 索引失败，keyword_search 将退化为 LIKE: %s", exc)

    def insert_item(self, record: dict) -> dict:
        """写入知识条目；指纹冲突时返回既有条目。

        Args:
            record: 条目记录（字段对齐 `knowledge_item`；指纹由本层计算）

        Returns:
            条目字典；冲突/复活时附 `deduplicated` 标记

        Raises:
            KnowledgeValidationError: 记录不符合数据契约
            KnowledgeStoreError: 数据库写入失败
        """
        normalized = self._normalize_item(dict(record or {}))
        self._validate(normalized, "knowledge_item", self._item_schema)

        item = KnowledgeItem.from_row(normalized)
        payload = item.to_dict()

        with self._write_lock:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT * FROM knowledge_items WHERE agent_id = ? AND fingerprint = ?",
                    (normalized["agent_id"], normalized["fingerprint"]),
                ).fetchone()
                if existing is not None and int(existing["is_deleted"] or 0) == 0:
                    result = KnowledgeItem.from_row(existing).to_dict()
                    result["deduplicated"] = True
                    return result

                columns = ", ".join(_ITEM_COLUMNS)
                placeholders = ", ".join("?" for _ in _ITEM_COLUMNS)
                values = [
                    json.dumps(payload["tags"], ensure_ascii=False)
                    if column == "tags"
                    else payload[column]
                    for column in _ITEM_COLUMNS
                ]
                if existing is not None:
                    assignments = ", ".join(
                        f"{column} = ?" for column in _ITEM_COLUMNS
                    )
                    conn.execute(
                        f"UPDATE knowledge_items SET {assignments} WHERE item_id = ?",
                        values + [existing["item_id"]],
                    )
                else:
                    conn.execute(
                        f"INSERT INTO knowledge_items ({columns}) VALUES ({placeholders})",
                        values,
                    )
                self._sync_fts_row(conn, payload)
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise KnowledgeStoreError(
                    "写入知识条目失败", {"error": str(exc), "db_path": self.db_path}
                ) from exc

        result = dict(payload)
        result["deduplicated"] = False
        return result

    def get_item(self, item_id: str) -> dict | None:
        """按 item_id 查询未删除条目；不存在返回 None。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM knowledge_items WHERE item_id = ? AND is_deleted = 0",
            (str(item_id),),
        ).fetchone()
        return None if row is None else KnowledgeItem.from_row(row).to_dict()

    def list_items(
        self,
        item_type: str | None = None,
        tags: list[str] | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """分页列出未删除条目。

        q 非空时复用 `keyword_search` 的命中 id 集合再分页；tags 为子集语义。
        """
        page_limit = max(0, int(limit))
        page_offset = max(0, int(offset))
        tag_filter = [str(tag) for tag in (tags or [])]
        query = str(q or "").strip()
        conn = self._get_conn()

        if query:
            hits = self._search_ranked(query, tag_filter)
            ordered_ids = [hit["item_id"] for hit in hits]
            if not ordered_ids:
                return {
                    "items": [],
                    "total": 0,
                    "limit": page_limit,
                    "offset": page_offset,
                }
            placeholders = ", ".join("?" for _ in ordered_ids)
            sql = (
                f"SELECT * FROM knowledge_items WHERE is_deleted = 0 "
                f"AND item_id IN ({placeholders})"
            )
            params = list(ordered_ids)
            if item_type is not None:
                sql += " AND item_type = ?"
                params.append(str(item_type))
            rows = conn.execute(sql, params).fetchall()
            row_map = {row["item_id"]: row for row in rows}
            filtered = [
                row_map[item_id]
                for item_id in ordered_ids
                if item_id in row_map and _matches_tags(row_map[item_id], tag_filter)
            ]
        else:
            sql = "SELECT * FROM knowledge_items WHERE is_deleted = 0"
            params = []
            if item_type is not None:
                sql += " AND item_type = ?"
                params.append(str(item_type))
            rows = conn.execute(sql, params).fetchall()
            filtered = [row for row in rows if _matches_tags(row, tag_filter)]
            filtered.sort(key=lambda row: str(row["item_id"]))
            filtered.sort(key=lambda row: str(row["created_at"]), reverse=True)

        total = len(filtered)
        page = filtered[page_offset:page_offset + page_limit]
        return {
            "items": [KnowledgeItem.from_row(row).to_dict() for row in page],
            "total": total,
            "limit": page_limit,
            "offset": page_offset,
        }

    def _soft_delete_items_locked(
        self, conn: sqlite3.Connection, item_id: str | None = None,
        document_id: str | None = None,
    ) -> int:
        """在已持锁的连接上执行条目软删除（内部辅助）。"""
        if item_id is not None:
            rows = conn.execute(
                "SELECT item_id FROM knowledge_items "
                "WHERE item_id = ? AND is_deleted = 0",
                (item_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT item_id FROM knowledge_items "
                "WHERE document_id = ? AND is_deleted = 0",
                (document_id,),
            ).fetchall()
        if not rows:
            return 0
        target_ids = [row["item_id"] for row in rows]
        conn.execute(
            "UPDATE knowledge_items SET is_deleted = 1, updated_at = ? "
            f"WHERE item_id IN ({', '.join('?' for _ in target_ids)})",
            [_iso_now()] + target_ids,
        )
        if self._fts5_available:
            try:
                conn.execute(
                    "DELETE FROM knowledge_items_fts "
                    f"WHERE item_id IN ({', '.join('?' for _ in target_ids)})",
                    target_ids,
                )
            except sqlite3.Error as exc:  # pragma: no cover
                logger.warning("清理 FTS 索引失败: %s", exc)
        return len(target_ids)

    def soft_delete_item(self, item_id: str) -> bool:
        """软删除单条条目并移除 FTS 索引；返回是否发生删除。"""
        with self._write_lock:
            conn = self._get_conn()
            try:
                count = self._soft_delete_items_locked(conn, item_id=str(item_id))
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise KnowledgeStoreError(
                    "软删除知识条目失败", {"error": str(exc)}
                ) from exc
            return count > 0

    def soft_delete_items_by_document(self, document_id: str) -> int:
        """按文档软删除其全部条目；返回受影响条目数。"""
        with self._write_lock:
            conn = self._get_conn()
            try:
                count = self._soft_delete_items_locked(
                    conn, document_id=str(document_id)
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise KnowledgeStoreError(
                    "按文档软删除知识条目失败", {"error": str(exc)}
                ) from exc
            return count

    def count_items_by_document(self, document_id: str) -> int:
        """统计文档下未删除的条目数。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(1) FROM knowledge_items "
            "WHERE document_id = ? AND is_deleted = 0",
            (str(document_id),),
        ).fetchone()
        return int(row[0])

    # ------------------------------------------------------------------ #
    # 关键词检索
    # ------------------------------------------------------------------ #
    def keyword_search(
        self, query: str, limit: int = 50, tags: list[str] | None = None
    ) -> list[dict]:
        """关键词检索（FTS5 trigram → 2 字滑窗 → LIKE 降级链）。

        Args:
            query: 查询字符串
            limit: 返回上限
            tags: 标签子集过滤

        Returns:
            命中字典列表（含 score；命中即 ≥1.0）
        """
        text = str(query or "").strip()
        if not text:
            return []
        ranked = self._search_ranked(text, [str(tag) for tag in (tags or [])])
        return ranked[:max(0, int(limit))]

    def _search_ranked(self, query: str, tags: list[str]) -> list[dict]:
        """执行检索并返回全量排序命中（分页由调用方负责）。"""
        conn = self._get_conn()
        rows: list[sqlite3.Row] = []
        fts_attempted = False

        if self._fts5_available and len(query) >= 3:
            fts_attempted = True
            expression = _trigram_expression(query)
            if expression:
                try:
                    rows = conn.execute(
                        "SELECT i.* FROM knowledge_items_fts f "
                        "JOIN knowledge_items i ON i.item_id = f.item_id "
                        "WHERE knowledge_items_fts MATCH ? AND i.is_deleted = 0",
                        (expression,),
                    ).fetchall()
                except sqlite3.Error as exc:
                    logger.warning(
                        "FTS5 查询失败，降级 LIKE: query=%r, err=%s", query, exc
                    )
                    rows = []
                    fts_attempted = False

        if not rows and not fts_attempted:
            rows = self._like_search(conn, [_like_pattern(query)])

        if not rows:
            bigrams = _bigram_terms(query)
            if bigrams:
                rows = self._like_search(conn, [_like_pattern(term) for term in bigrams])

        hits = []
        for row in rows:
            if not _matches_tags(row, tags):
                continue
            score = self._simple_score(row, query)
            hits.append(SearchHit.from_row(row, score=score).to_dict())
        hits.sort(key=lambda hit: (-float(hit["score"]), str(hit["item_id"])))
        return hits

    def _like_search(
        self, conn: sqlite3.Connection, patterns: list[str]
    ) -> list[sqlite3.Row]:
        """LIKE 降级检索（title/content 任一命中）。"""
        if not patterns:
            return []
        clauses = " OR ".join(
            "(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')"
            for _ in patterns
        )
        params = []
        for pattern in patterns:
            params.extend([pattern, pattern])
        try:
            return conn.execute(
                f"SELECT * FROM knowledge_items WHERE is_deleted = 0 "
                f"AND ({clauses})",
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("LIKE 降级检索失败，返回空结果: %s", exc)
            return []

    @staticmethod
    def _simple_score(row: object, query: str) -> float:
        """简单计分：整串命中记 1.0，否则按 2 字词元出现次数计分（下限 1.0）。"""
        title = str(row["title"] or "")
        content = str(row["content"] or "")
        haystack = f"{title}\n{content}"
        if query and query in haystack:
            return 1.0
        terms = _bigram_terms(query)
        occurrences = sum(haystack.count(term) for term in terms if term)
        return float(max(occurrences, 1))
