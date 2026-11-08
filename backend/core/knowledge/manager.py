"""模块11 独立知识库管理器（per-agent 隔离）。

对外契约见 `public/interface_stub/knowledge_service.pyi`：`KnowledgeManager` 10 个
公开方法 + `__init__`（共 11 个类签名）。本模块另提供两个内部装配辅助
（`intake_document` / `process_document`）供 API 层实现「上传即返回 pending、
后台解析」，以及 `KnowledgeRegistry` 负责按 agent 懒创建与生命周期管理。

隔离规则（spec「独立存储与 Per-Agent 隔离」）：
- default：`data/knowledge.db`、`data/knowledge_files/default/`、`CXHMSKnowledge`
- 其他：`data/knowledge_{safe}.db`、`data/knowledge_files/{safe}/`、`CXHMSKnowledge_{safe}`
- `agent_id` 原始值入数据列；文件名/目录/collection 只使用清洗值。

default 保护：`KnowledgeRegistry.close_agent` / `close_all` 不得删除主 collection。
"""

import asyncio
import hashlib
import logging
import os
import re
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Mapping, Sequence

from backend.core.knowledge.chunker import chunk_text
from backend.core.knowledge.config import load_knowledge_config, resolve_project_path
from backend.core.knowledge.exceptions import (
    KnowledgeStoreError,
    KnowledgeUnsupportedMediaError,
    KnowledgeValidationError,
)
from backend.core.knowledge.parsers.base import (
    KNOWLEDGE_PARSE_FAILED,
    classify_mime,
    infer_mime,
    sanitize_filename,
)
from backend.core.knowledge.parsers.router import parse
from backend.core.knowledge.store import KnowledgeStore
from backend.core.knowledge.vector_index import KnowledgeVectorIndex

logger = logging.getLogger(__name__)

_AGENT_ID_RE = re.compile(r"[^a-zA-Z0-9_]")
_MAX_TITLE_CHARS = 40
_COPY_CHUNK_BYTES = 1024 * 1024
DEFAULT_AGENT_ID = "default"


def safe_agent_id(agent_id: Any) -> str:
    """清洗 agent_id 为可安全用于文件名/目录/collection 的片段。

    - `default` / 空值返回 `default`；
    - 非字母数字下划线替换为 `_`；
    - 清洗后不以字母或下划线开头时补 `agent_` 前缀。
    """
    raw = str(agent_id or "").strip()
    if not raw or raw == DEFAULT_AGENT_ID:
        return DEFAULT_AGENT_ID
    cleaned = _AGENT_ID_RE.sub("_", raw)
    if not cleaned:
        return DEFAULT_AGENT_ID
    if not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"agent_{cleaned}"
    return cleaned


def is_default_agent(agent_id: Any) -> bool:
    """判断是否为 default agent（主库 / 主 collection）。"""
    return safe_agent_id(agent_id) == DEFAULT_AGENT_ID


class KnowledgeManager:
    """单 agent 知识库管理器（SQLite + 文件目录 + 向量 collection）。"""

    def __init__(
        self,
        agent_id: str,
        config: Mapping[str, Any],
        embedding_model: Any | None = None,
        vector_index: Any | None = None,
    ) -> None:
        """构造知识库管理器。

        Args:
            agent_id: agent 标识（default 回退主库）
            config: knowledge 配置段（缺失字段自动补齐）
            embedding_model: 嵌入模型（可为 None，向量不可用时降级 FTS/LIKE）
            vector_index: 向量索引适配器（可为 None，内部按配置创建）

        Raises:
            KnowledgeStoreError: 存储初始化失败（503）
        """
        self.agent_id = str(agent_id or DEFAULT_AGENT_ID)
        self._safe_agent_id = safe_agent_id(self.agent_id)
        self.is_default = self._safe_agent_id == DEFAULT_AGENT_ID
        self.config = load_knowledge_config(dict(config or {}))

        db_dir = resolve_project_path(str(self.config["db_dir"]))
        prefix = str(self.config["db_filename_prefix"])
        db_name = f"{prefix}.db" if self.is_default else f"{prefix}_{self._safe_agent_id}.db"
        self.db_path = os.path.join(db_dir, db_name)

        self.files_root = os.path.join(
            resolve_project_path(str(self.config["files_dir"])),
            DEFAULT_AGENT_ID if self.is_default else self._safe_agent_id,
        )
        os.makedirs(self.files_root, exist_ok=True)

        self.store = KnowledgeStore(self.db_path)

        self._owns_vector_index = vector_index is None
        self.vector_index = (
            vector_index
            if vector_index is not None
            else KnowledgeVectorIndex(config=self.config, embedding_model=embedding_model)
        )
        self.last_search_fallback = False

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    def _ensure_enabled(self) -> None:
        """知识库总开关关闭时统一抛 503。"""
        if not self.config.get("enabled", True):
            raise KnowledgeStoreError(
                "知识库未启用", {"agent_id": self.agent_id, "enabled": False}
            )

    def _metadata_of(self, document: Mapping[str, Any]) -> dict:
        """读取文档 metadata（容错为空字典）。"""
        metadata = document.get("metadata")
        return dict(metadata) if isinstance(metadata, Mapping) else {}

    @staticmethod
    def _normalize_tags(tags: Sequence[str] | None) -> list[str]:
        """把标签序列规范化为去空字符串列表（保序去重）。"""
        if not tags:
            return []
        result: list[str] = []
        for tag in tags:
            text = str(tag).strip()
            if text and text not in result:
                result.append(text)
        return result

    def _whitelist_for(self, kind: str) -> list[str]:
        """按媒体大类读取 MIME 白名单。"""
        key = {
            "document": "allowed_document_mimes",
            "image": "allowed_image_mimes",
            "audio": "allowed_audio_mimes",
            "video": "allowed_video_mimes",
        }.get(kind)
        if key is None:
            return []
        return [str(item) for item in self.config.get(key) or []]

    def _read_payload(
        self, data: bytes | None, source_path: str | None
    ) -> bytes:
        """读取上传内容（内存字节优先，其次源文件）。"""
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if source_path:
            try:
                with open(str(source_path), "rb") as handle:
                    return handle.read()
            except OSError as exc:
                raise KnowledgeValidationError(
                    "读取源文件失败", {"source_path": str(source_path), "error": str(exc)}
                ) from exc
        raise KnowledgeValidationError("必须提供 data 或 source_path")

    def _stream_copy(
        self, source_path: str, storage_path: str, limit_bytes: int
    ) -> tuple[int, str]:
        """分块复制源文件到知识库目录并计算 SHA-256。

        媒体文件可能达数百 MB，必须避免整块读入内存（spec 内存约束）。

        Returns:
            `(size_bytes, sha256_hex)`

        Raises:
            KnowledgeValidationError: 读取失败或复制过程中超出大小上限
            KnowledgeStoreError: 目标写入失败
        """
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with open(str(source_path), "rb") as src, open(storage_path, "wb") as dst:
                while True:
                    block = src.read(_COPY_CHUNK_BYTES)
                    if not block:
                        break
                    size_bytes += len(block)
                    if size_bytes > limit_bytes:
                        raise KnowledgeValidationError(
                            "文件大小超过限制",
                            {"size_bytes": size_bytes, "limit_bytes": limit_bytes},
                        )
                    digest.update(block)
                    dst.write(block)
        except KnowledgeValidationError:
            self._remove_file(storage_path)
            raise
        except OSError as exc:
            self._remove_file(storage_path)
            raise KnowledgeStoreError(
                "复制上传文件失败",
                {"source_path": str(source_path), "error": str(exc)},
            ) from exc
        return size_bytes, digest.hexdigest()

    # ------------------------------------------------------------------ #
    # 上传与后台解析
    # ------------------------------------------------------------------ #
    def intake_document(
        self,
        filename: str,
        mime: str,
        data: bytes | None = None,
        source_path: str | None = None,
        tags: Sequence[str] | None = None,
        title: str | None = None,
    ) -> dict:
        """落盘上传内容并登记 pending 文档（可被去重短路）。

        Returns:
            文档字典（含 `deduplicated` 标记）
        """
        self._ensure_enabled()

        safe_name = sanitize_filename(filename)
        safe_mime = infer_mime(safe_name, mime)
        kind = classify_mime(safe_mime)
        if kind == "unsupported" or safe_mime not in self._whitelist_for(kind):
            raise KnowledgeUnsupportedMediaError(
                f"不支持的 MIME 类型: {safe_mime}",
                {"mime": safe_mime, "filename": safe_name},
            )

        limit_mb = int(
            self.config["max_document_size_mb"]
            if kind == "document"
            else self.config["max_media_size_mb"]
        )
        limit_bytes = limit_mb * 1024 * 1024

        document_id = uuid.uuid4().hex
        extension = os.path.splitext(safe_name)[1].lower()
        storage_path = os.path.join(self.files_root, f"{document_id}{extension}")

        # 已有落盘文件时走分块复制（避免整块读入内存）；纯 bytes 入参才走内存路径
        streamed = not isinstance(data, (bytes, bytearray)) and bool(source_path)
        if streamed:
            size_bytes, sha256_hex = self._stream_copy(
                str(source_path), storage_path, limit_bytes
            )
        else:
            payload = self._read_payload(data, source_path)
            if len(payload) > limit_bytes:
                raise KnowledgeValidationError(
                    "文件大小超过限制",
                    {
                        "size_bytes": len(payload),
                        "limit_mb": limit_mb,
                        "category": kind,
                    },
                )
            try:
                with open(storage_path, "wb") as handle:
                    handle.write(payload)
            except OSError as exc:
                raise KnowledgeStoreError(
                    "写入知识库文件失败",
                    {"storage_path": storage_path, "error": str(exc)},
                ) from exc
            size_bytes = len(payload)
            sha256_hex = _sha256_hex(payload)

        metadata = {
            "category": kind,
            "tags": self._normalize_tags(tags),
            "title": str(title).strip() if title else None,
        }
        record = {
            "document_id": document_id,
            "agent_id": self.agent_id,
            "filename": safe_name,
            "mime": safe_mime,
            "size_bytes": size_bytes,
            "sha256": sha256_hex,
            "storage_path": storage_path,
            "parse_status": "pending",
            "parse_error": None,
            "metadata": metadata,
            "created_at": None,
            "updated_at": None,
            "is_deleted": 0,
        }

        try:
            stored = self.store.upsert_document(record)
        except Exception:
            self._remove_file(storage_path)
            raise

        if stored.get("deduplicated"):
            self._remove_file(storage_path)
            return stored
        return stored

    async def process_document(self, document_id: str) -> dict | None:
        """解析已登记文档并建立 FTS / 向量索引（后台任务入口）。

        Returns:
            更新后的文档字典；文档不存在返回 None
        """
        self._ensure_enabled()
        document = self.store.get_document(document_id)
        if document is None:
            return None

        metadata = self._metadata_of(document)
        self.store.update_document_status(document_id, "parsing", None, metadata)

        try:
            result = await asyncio.to_thread(
                parse,
                str(document.get("storage_path") or ""),
                str(document.get("filename") or ""),
                str(document.get("mime") or ""),
                self.config,
            )
        except Exception as exc:  # 解析器契约不抛异常，此处兜底不可预期错误
            logger.warning("知识文档解析异常 (document_id=%s): %s", document_id, exc)
            metadata["error"] = str(exc)
            return self.store.update_document_status(
                document_id, "failed", KNOWLEDGE_PARSE_FAILED, metadata
            )

        merged_metadata = dict(metadata)
        merged_metadata.update(result.metadata or {})

        if result.parse_status != "parsed":
            return self.store.update_document_status(
                document_id,
                result.parse_status,
                result.parse_error or KNOWLEDGE_PARSE_FAILED,
                merged_metadata,
            )

        chunks = chunk_text(
            result.text_content,
            int(self.config["chunk_size"]),
            int(self.config["chunk_overlap"]),
            int(self.config["max_chunks_per_document"]),
        )
        if not chunks:
            merged_metadata["error"] = "解析文本为空"
            return self.store.update_document_status(
                document_id, "failed", KNOWLEDGE_PARSE_FAILED, merged_metadata
            )

        title = merged_metadata.get("title") or document.get("filename") or ""
        item_tags = self._normalize_tags(merged_metadata.get("tags"))
        items: list[dict] = []
        for index, content in enumerate(chunks):
            item = self.store.insert_item(
                {
                    "item_id": uuid.uuid4().hex,
                    "agent_id": self.agent_id,
                    "document_id": document_id,
                    "item_type": "doc_chunk",
                    "title": f"{title} [{index + 1}]",
                    "content": content,
                    "tags": item_tags,
                    "importance": 3,
                    "chunk_index": index,
                    "created_at": None,
                    "updated_at": None,
                    "is_deleted": 0,
                }
            )
            items.append(item)

        vector_indexed = 0
        try:
            vector_indexed = await self.vector_index.upsert(self.agent_id, items)
        except Exception as exc:  # 向量失败不影响 FTS 可用性
            logger.warning("知识文档向量写入失败 (document_id=%s): %s", document_id, exc)

        merged_metadata["chunk_count"] = len(items)
        merged_metadata["vector_indexed"] = int(vector_indexed)
        return self.store.update_document_status(
            document_id, "parsed", None, merged_metadata
        )

    async def add_document(
        self,
        filename: str,
        mime: str,
        data: bytes | None = None,
        source_path: str | None = None,
        tags: Sequence[str] = (),
        title: str | None = None,
    ) -> dict:
        """上传并解析文档（文本/图片/音频/视频）。

        Raises:
            KnowledgeUnsupportedMediaError: MIME 不在白名单（415）
            KnowledgeValidationError: 参数或数据不符合契约（400）
            KnowledgeStoreError: 存储不可用（503）
        """
        stored = self.intake_document(
            filename=filename,
            mime=mime,
            data=data,
            source_path=source_path,
            tags=tags,
            title=title,
        )
        if stored.get("deduplicated"):
            return stored
        updated = await self.process_document(str(stored["document_id"]))
        return updated if updated is not None else stored

    # ------------------------------------------------------------------ #
    # 经验写入
    # ------------------------------------------------------------------ #
    async def add_experience(
        self,
        title: str | None = None,
        content: str = "",
        tags: Sequence[str] = (),
        importance: int = 3,
    ) -> dict:
        """写入可复用经验（item_type=experience）。

        Raises:
            KnowledgeValidationError: content 为空或 importance 越界（400）
            KnowledgeStoreError: 存储不可用（503）
        """
        self._ensure_enabled()
        text = str(content or "").strip()
        if not text:
            raise KnowledgeValidationError("经验内容不能为空")

        try:
            level = int(importance)
        except (TypeError, ValueError) as exc:
            raise KnowledgeValidationError(
                "importance 必须为 1..5 的整数", {"importance": importance}
            ) from exc
        if level < 1 or level > 5:
            raise KnowledgeValidationError(
                "importance 必须为 1..5 的整数", {"importance": importance}
            )

        resolved_title = str(title).strip() if title else ""
        if not resolved_title:
            resolved_title = " ".join(text.split())[:_MAX_TITLE_CHARS]

        stored = self.store.insert_item(
            {
                "item_id": uuid.uuid4().hex,
                "agent_id": self.agent_id,
                "document_id": None,
                "item_type": "experience",
                "title": resolved_title,
                "content": text,
                "tags": self._normalize_tags(tags),
                "importance": level,
                "chunk_index": None,
                "created_at": None,
                "updated_at": None,
                "is_deleted": 0,
            }
        )
        if not stored.get("deduplicated"):
            try:
                await self.vector_index.upsert(self.agent_id, [stored])
            except Exception as exc:  # 向量失败不阻断经验落库
                logger.warning("知识经验向量写入失败: %s", exc)
        return stored

    # ------------------------------------------------------------------ #
    # 检索
    # ------------------------------------------------------------------ #
    async def search(
        self,
        query: str,
        top_k: int = 8,
        tags: Sequence[str] | None = None,
        item_type: str | None = None,
    ) -> list[dict]:
        """混合检索（向量 + FTS，RRF 融合；向量不可用时降级关键词）。"""
        self._ensure_enabled()
        text = str(query or "").strip()
        if not text:
            return []

        limit = self._clamp_top_k(top_k)
        candidates = max(1, limit * 2)
        tag_list = self._normalize_tags(tags) or None

        vector_hits: list[dict] = []
        vector_available = False
        if bool(self.config.get("vector_enabled", True)):
            # 不仅看配置开关，还要看向量后端实际是否就绪，否则 fallback 标志会失真
            is_available = getattr(self.vector_index, "is_available", None)
            try:
                vector_available = bool(is_available()) if callable(is_available) else True
            except Exception as exc:
                logger.warning("知识库向量可用性探测失败: %s", exc)
                vector_available = False
        if vector_available:
            try:
                vector_hits = await self.vector_index.search(
                    self.agent_id, text, limit=candidates, tags=tag_list
                )
            except Exception as exc:
                logger.warning("知识库向量检索失败，降级关键词: %s", exc)
                vector_hits = []
                vector_available = False
        self.last_search_fallback = not vector_available

        keyword_hits: list[dict] = []
        if self.config.get("fts_enabled", True):
            try:
                keyword_hits = self.store.keyword_search(
                    text, limit=candidates, tags=tag_list
                )
            except Exception as exc:
                logger.warning("知识库关键词检索失败: %s", exc)
                keyword_hits = []

        rrf_k = max(1, int(self.config.get("vector_rrf_k", 60)))
        scores: dict[str, float] = {}
        for ranked in (vector_hits, keyword_hits):
            for rank, hit in enumerate(ranked, start=1):
                item_id = str(hit.get("item_id") or "")
                if not item_id:
                    continue
                scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rrf_k + rank)

        results: list[dict] = []
        for item_id, score in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0])):
            item = self.store.get_item(item_id)
            if item is None:
                continue
            if item_type is not None and item.get("item_type") != item_type:
                continue
            results.append(
                {
                    "item_id": item["item_id"],
                    "agent_id": item["agent_id"],
                    "item_type": item["item_type"],
                    "content": item["content"],
                    "fingerprint": item["fingerprint"],
                    "created_at": item["created_at"],
                    "score": float(score),
                    "document_id": item.get("document_id"),
                    "title": item.get("title"),
                    "tags": list(item.get("tags") or []),
                }
            )
            if len(results) >= limit:
                break
        return results

    def _clamp_top_k(self, top_k: int) -> int:
        """收敛检索 top_k 到配置上限。"""
        default = max(1, int(self.config.get("search_top_k_default", 8)))
        maximum = max(default, int(self.config.get("search_top_k_max", 50)))
        try:
            value = int(top_k)
        except (TypeError, ValueError):
            value = default
        return max(1, min(value, maximum))

    # ------------------------------------------------------------------ #
    # 条目
    # ------------------------------------------------------------------ #
    def list_items(
        self,
        item_type: str | None = None,
        tags: Sequence[str] | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """分页列出知识条目。"""
        self._ensure_enabled()
        return self.store.list_items(
            item_type=item_type,
            tags=self._normalize_tags(tags),
            q=q,
            limit=limit,
            offset=offset,
        )

    def get_item(self, item_id: str) -> dict | None:
        """按 item_id 查询条目；不存在返回 None。"""
        self._ensure_enabled()
        return self.store.get_item(item_id)

    async def delete_item(self, item_id: str) -> bool:
        """软删除条目并删除其向量；返回是否删除成功。"""
        self._ensure_enabled()
        target = str(item_id)
        if self.store.get_item(target) is None:
            return False
        deleted = self.store.soft_delete_item(target)
        if deleted:
            try:
                await self.vector_index.delete(self.agent_id, [target])
            except Exception as exc:
                logger.warning("知识条目向量删除失败 (item_id=%s): %s", target, exc)
        return deleted

    # ------------------------------------------------------------------ #
    # 文档
    # ------------------------------------------------------------------ #
    def list_documents(self, limit: int = 20, offset: int = 0) -> dict:
        """分页列出文档与解析状态。"""
        self._ensure_enabled()
        return self.store.list_documents(limit=limit, offset=offset)

    def get_document(self, document_id: str) -> dict | None:
        """按 document_id 查询文档（metadata 附解析文本预览）。"""
        self._ensure_enabled()
        document = self.store.get_document(document_id)
        if document is None:
            return None
        items = self.store.list_items_by_document(document_id)
        preview_chars = max(1, int(self.config.get("preview_chars", 500)))
        preview = "\n".join(str(item.get("content") or "") for item in items)
        metadata = self._metadata_of(document)
        metadata["chunk_count"] = len(items)
        metadata["preview"] = preview[:preview_chars]
        result = dict(document)
        result["metadata"] = metadata
        return result

    async def delete_document(self, document_id: str) -> bool:
        """删除文档及其分块、向量与物理文件；返回是否删除成功。"""
        self._ensure_enabled()
        target = str(document_id)
        document = self.store.get_document(target)
        if document is None:
            return False

        item_ids = self.store.list_item_ids_by_document(target)
        deleted = self.store.soft_delete_document(target)
        if not deleted:
            return False

        if item_ids:
            try:
                await self.vector_index.delete(self.agent_id, item_ids)
            except Exception as exc:
                logger.warning("知识文档向量删除失败 (document_id=%s): %s", target, exc)
        self._remove_file(document.get("storage_path"))
        return True

    # ------------------------------------------------------------------ #
    # 健康检查与关闭
    # ------------------------------------------------------------------ #
    def health(self) -> dict:
        """知识库健康检查（`enabled=false` 时按 spec 统一返回 503）。"""
        self._ensure_enabled()
        ffmpeg_ok = False
        try:
            from backend.core.knowledge.media import ffmpeg_available

            ffmpeg_ok = bool(ffmpeg_available(self.config))
        except Exception as exc:  # 媒体模块缺失不应阻塞健康检查
            logger.warning("ffmpeg 可用性探测失败: %s", exc)
        return {
            "enabled": bool(self.config.get("enabled", True)),
            "vector_enabled": bool(self.config.get("vector_enabled", True)),
            "fts_enabled": bool(self.config.get("fts_enabled", True))
            and bool(getattr(self.store, "_fts5_available", False)),
            "asr_provider": str(self.config.get("asr_provider", "faster_whisper")),
            "ffmpeg_available": ffmpeg_ok,
        }

    def close(self) -> None:
        """关闭存储连接与自有向量客户端（幂等）。"""
        try:
            self.store.close()
        except Exception as exc:  # pragma: no cover - 关闭容错
            logger.warning("关闭知识库存储失败: %s", exc)
        if self._owns_vector_index:
            try:
                self.vector_index.close()
            except Exception as exc:  # pragma: no cover - 关闭容错
                logger.warning("关闭知识库向量索引失败: %s", exc)

    # ------------------------------------------------------------------ #
    # 文件清理
    # ------------------------------------------------------------------ #
    def _remove_file(self, path: Any) -> None:
        """仅删除位于本 agent 文件目录内的文件（防路径穿越）。"""
        if not path:
            return
        absolute = os.path.abspath(str(path))
        root = os.path.abspath(self.files_root)
        if not absolute.startswith(root + os.sep):
            logger.warning("拒绝删除知识库目录外文件: %s", absolute)
            return
        if not os.path.isfile(absolute):
            return
        try:
            os.remove(absolute)
        except OSError as exc:
            logger.warning("删除知识库文件失败 (%s): %s", absolute, exc)


class KnowledgeRegistry:
    """按 agent 懒创建的知识库管理器注册表。"""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        embedding_model: Any | None = None,
        parse_max_workers: int | None = None,
    ) -> None:
        """初始化注册表。

        Args:
            config: knowledge 配置段（None 时按 config/default.yaml 加载）
            embedding_model: 嵌入模型（透传给每个管理器）
            parse_max_workers: 解析线程池大小（None 时取配置值）
        """
        self.config = load_knowledge_config(dict(config or {}))
        self.embedding_model = embedding_model
        workers = parse_max_workers or int(self.config.get("parse_max_workers", 2))
        self.parse_max_workers = max(1, min(int(workers), 8))
        self._managers: dict[str, KnowledgeManager] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=self.parse_max_workers, thread_name_prefix="knowledge-parse"
        )

    def get_manager(self, agent_id: str = DEFAULT_AGENT_ID) -> KnowledgeManager:
        """获取（必要时创建）指定 agent 的管理器。"""
        key = safe_agent_id(agent_id)
        with self._lock:
            manager = self._managers.get(key)
            if manager is None:
                manager = KnowledgeManager(
                    agent_id=str(agent_id or DEFAULT_AGENT_ID),
                    config=self.config,
                    embedding_model=self.embedding_model,
                )
                self._managers[key] = manager
            return manager

    def remove_manager(self, agent_id: str = DEFAULT_AGENT_ID) -> None:
        """关闭并移除指定 agent 的管理器（不删除向量 collection）。"""
        key = safe_agent_id(agent_id)
        with self._lock:
            manager = self._managers.pop(key, None)
        if manager is not None:
            manager.close()

    def close_agent(self, agent_id: str = DEFAULT_AGENT_ID) -> None:
        """关闭指定 agent 的管理器并清理其向量 collection（default 受保护）。"""
        key = safe_agent_id(agent_id)
        with self._lock:
            manager = self._managers.pop(key, None)
        if manager is None:
            return
        if key != DEFAULT_AGENT_ID:
            try:
                manager.vector_index.delete_agent_collection(manager.agent_id)
            except Exception as exc:
                logger.warning("清理 agent 向量 collection 失败: %s", exc)
        else:
            logger.info("default agent 关闭：保留主 collection 不做删除")
        manager.close()

    def close_all(self, delete_collections: bool = False) -> None:
        """关闭全部管理器并释放线程池（可重复调用）。"""
        with self._lock:
            managers = list(self._managers.items())
            self._managers.clear()
        for key, manager in managers:
            if delete_collections and key != DEFAULT_AGENT_ID:
                try:
                    manager.vector_index.delete_agent_collection(manager.agent_id)
                except Exception as exc:
                    logger.warning("清理 agent 向量 collection 失败: %s", exc)
            manager.close()
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:  # pragma: no cover - 兼容旧 Python
            self._executor.shutdown(wait=False)

    def submit_parse(self, fn: Any, *args: Any, **kwargs: Any) -> Future:
        """把解析任务提交到 parse_max_workers 线程池。"""
        return self._executor.submit(fn, *args, **kwargs)


def _sha256_hex(payload: bytes) -> str:
    """计算 SHA-256 十六进制摘要。"""
    import hashlib

    return hashlib.sha256(payload).hexdigest()
