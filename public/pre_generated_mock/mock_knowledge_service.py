"""KnowledgeManager 预生成 Mock 实现。

对应接口契约: public/interface_stub/knowledge_service.pyi
对应数据契约: public/schema/knowledge.json
对应配置契约: public/config_template/knowledge_config.json

Mock 策略（rules-3 §四 Mock 机制三原则）：
- 预生成：返回符合 knowledge.json 字段约束的固定样例数据（document_id / item_id 以 mock- 前缀）。
- 零等待：下游分支无需等待 backend/core/knowledge 真实实现即可联调上传/检索/列表/删除。
- 可覆盖：需要特殊场景时在 public/global_mock/ 提供同名实现覆盖默认值。

替换边界：真实实现就位后，把
    from public.pre_generated_mock.mock_knowledge_service import MockKnowledgeService
改为
    from backend.core.knowledge.manager import KnowledgeManager
即可，调用方代码无需其他改动（签名与 .pyi 契约一致）。

边界约束：本 Mock 不导入 backend/core/knowledge，不依赖 jsonschema，不修改
public/pre_generated_mock/__init__.py（消费方直接按模块路径导入本文件）。

@version 1.0.0
"""

import hashlib
from datetime import datetime, timezone


def _iso_now() -> str:
    """返回 ISO 8601 带时区时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _sha256_of(data: bytes | None, source_path: str | None) -> str:
    """计算模拟内容 SHA-256（无输入时用 source_path / 空串的摘要，保证 64 位十六进制）。"""
    if data is not None:
        return hashlib.sha256(data).hexdigest()
    seed = source_path or ""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _fingerprint_of(*parts: str) -> str:
    """按部件拼接计算 MD5 指纹。"""
    return hashlib.md5(":".join(parts).encode("utf-8")).hexdigest()


class MockKnowledgeService:
    """知识库管理器预生成 Mock。

    内存 dict 存储，方法签名与 public/interface_stub/knowledge_service.pyi 的
    KnowledgeManager 完全一致（10 个公开方法 + __init__）。
    """

    def __init__(self, agent_id="default", config=None, embedding_model=None, vector_index=None):
        """初始化 Mock。

        Args:
            agent_id: 模拟 agent 标识，默认 'default'
            config: 模拟 knowledge 配置段（可选）
            embedding_model: 模拟嵌入模型（占位，未使用）
            vector_index: 模拟向量索引（占位，未使用）
        """
        self.agent_id = agent_id
        self.config = dict(config or {})
        self.embedding_model = embedding_model
        self.vector_index = vector_index
        self._documents = {}
        self._items = {}
        self._seq = 0

    def _next_id(self, prefix: str) -> str:
        """生成带 mock- 前缀的递增标识。"""
        self._seq += 1
        return "mock-{0}-{1:04d}".format(prefix, self._seq)

    def _document_view(self, record: dict) -> dict:
        """返回文档记录的浅拷贝，避免调用方污染内存态。"""
        return dict(record)

    def _item_view(self, record: dict) -> dict:
        """返回条目记录的浅拷贝。"""
        return dict(record)

    async def add_document(
        self,
        filename,
        mime,
        data=None,
        source_path=None,
        tags=(),
        title=None,
    ) -> dict:
        """模拟上传并解析文档，立即返回 parsed 状态的文档记录。"""
        document_id = self._next_id("doc")
        record = {
            "document_id": document_id,
            "agent_id": self.agent_id,
            "filename": filename,
            "mime": mime,
            "size_bytes": len(data) if data is not None else 0,
            "sha256": _sha256_of(data, source_path),
            "parse_status": "parsed",
            "created_at": _iso_now(),
            "storage_path": source_path,
            "parse_error": None,
            "metadata": {"mock": True},
            "updated_at": None,
            "is_deleted": 0,
        }
        self._documents[document_id] = record

        # 每个文档生成一条 doc_chunk 模拟条目
        chunk_content = "Mock 解析文本：" + str(title or filename)
        item_id = self._next_id("item")
        item = {
            "item_id": item_id,
            "agent_id": self.agent_id,
            "item_type": "doc_chunk",
            "content": chunk_content,
            "fingerprint": _fingerprint_of(document_id, "0", chunk_content),
            "created_at": _iso_now(),
            "document_id": document_id,
            "title": title or filename,
            "tags": list(tags or ()),
            "importance": 3,
            "chunk_index": 0,
            "updated_at": None,
            "is_deleted": 0,
        }
        self._items[item_id] = item

        # 返回值严格符合 knowledge.json 的 knowledge_document 字段（additionalProperties: false，
        # 不附加 schema 外字段；deduplicated 等 API 语义由路由层补足）
        return self._document_view(record)

    async def add_experience(
        self,
        title=None,
        content="",
        tags=(),
        importance=3,
    ) -> dict:
        """模拟写入可复用经验（item_type=experience）。"""
        normalized = " ".join(str(content or "").split())
        resolved_title = title or normalized[:40]
        item_id = self._next_id("item")
        fingerprint = _fingerprint_of(normalized)
        existing = self._find_by_fingerprint(fingerprint)
        if existing is not None:
            # 指纹重复时返回既有条目（仍为 knowledge_item 的合法字段集）
            return self._item_view(existing)

        item = {
            "item_id": item_id,
            "agent_id": self.agent_id,
            "item_type": "experience",
            "content": content,
            "fingerprint": fingerprint,
            "created_at": _iso_now(),
            "document_id": None,
            "title": resolved_title or None,
            "tags": list(tags or ()),
            "importance": int(importance),
            "chunk_index": None,
            "updated_at": None,
            "is_deleted": 0,
        }
        self._items[item_id] = item
        return self._item_view(item)

    def _find_by_fingerprint(self, fingerprint: str) -> dict | None:
        """按指纹查找未删除条目。"""
        for record in self._items.values():
            if record["fingerprint"] == fingerprint and record["is_deleted"] == 0:
                return record
        return None

    async def search(self, query, top_k=8, tags=None, item_type=None) -> list:
        """模拟混合检索：对 content/title/tags 做大小写无关包含匹配，按分数降序。"""
        needle = str(query or "").strip().lower()
        tag_filter = list(tags or ())
        hits = []
        for record in self._items.values():
            if record["is_deleted"] != 0:
                continue
            if item_type is not None and record["item_type"] != item_type:
                continue
            if tag_filter and not set(tag_filter).issubset(set(record["tags"])):
                continue
            haystack = " ".join(
                [str(record["content"]), str(record["title"] or ""), " ".join(record["tags"])]
            ).lower()
            if needle and needle not in haystack:
                continue
            score = 1.0 if needle and needle in str(record["content"]).lower() else 0.5
            hit = self._item_view(record)
            hit["score"] = score
            hits.append(hit)
        hits.sort(key=lambda h: (-h["score"], h["item_id"]))
        return hits[: int(top_k)]

    def list_items(self, item_type=None, tags=None, q=None, limit=20, offset=0) -> dict:
        """模拟分页列出条目。"""
        tag_filter = list(tags or ())
        needle = str(q or "").strip().lower()
        matched = []
        for record in self._items.values():
            if record["is_deleted"] != 0:
                continue
            if item_type is not None and record["item_type"] != item_type:
                continue
            if tag_filter and not set(tag_filter).issubset(set(record["tags"])):
                continue
            if needle:
                haystack = (str(record["content"]) + " " + str(record["title"] or "")).lower()
                if needle not in haystack:
                    continue
            matched.append(self._item_view(record))
        matched.sort(key=lambda r: (r["created_at"], r["item_id"]))
        start = max(0, int(offset))
        end = start + max(0, int(limit))
        return {"items": matched[start:end], "total": len(matched), "limit": int(limit), "offset": start}

    def get_item(self, item_id) -> dict | None:
        """模拟按 item_id 查询条目；不存在或已删除返回 None。"""
        record = self._items.get(item_id)
        if record is None or record["is_deleted"] != 0:
            return None
        return self._item_view(record)

    async def delete_item(self, item_id) -> bool:
        """模拟软删除条目；返回是否发生删除。"""
        record = self._items.get(item_id)
        if record is None or record["is_deleted"] != 0:
            return False
        record["is_deleted"] = 1
        record["updated_at"] = _iso_now()
        return True

    def list_documents(self, limit=20, offset=0) -> dict:
        """模拟分页列出文档。"""
        matched = [self._document_view(r) for r in self._documents.values() if r["is_deleted"] == 0]
        matched.sort(key=lambda r: (r["created_at"], r["document_id"]))
        start = max(0, int(offset))
        end = start + max(0, int(limit))
        return {"documents": matched[start:end], "total": len(matched), "limit": int(limit), "offset": start}

    def get_document(self, document_id) -> dict | None:
        """模拟按 document_id 查询文档；不存在或已删除返回 None。"""
        record = self._documents.get(document_id)
        if record is None or record["is_deleted"] != 0:
            return None
        return self._document_view(record)

    async def delete_document(self, document_id) -> bool:
        """模拟删除文档及其全部分块；返回是否发生删除。"""
        record = self._documents.get(document_id)
        if record is None or record["is_deleted"] != 0:
            return False
        record["is_deleted"] = 1
        record["updated_at"] = _iso_now()
        for item in self._items.values():
            if item["document_id"] == document_id and item["is_deleted"] == 0:
                item["is_deleted"] = 1
                item["updated_at"] = _iso_now()
        return True

    def health(self) -> dict:
        """模拟健康检查（不访问真实依赖）。"""
        return {
            "status": "ok",
            "enabled": bool(self.config.get("enabled", True)),
            "vector_enabled": False,
            "fts_enabled": bool(self.config.get("fts_enabled", True)),
            "asr_provider": self.config.get("asr_provider", "faster_whisper"),
            "ffmpeg_available": False,
            "mock": True,
        }
