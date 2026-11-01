"""模块11 独立知识库 per-agent 向量索引（Task 7）。

职责：
- 按 agent 隔离 Weaviate collection（``{collection_prefix}_{safe_agent_id}``，
  ``default`` 使用 ``{collection_prefix}`` 本名，不加后缀）；
- 提供 ``upsert / search / delete / delete_agent_collection`` 四个公开操作；
- embedding 适配：优先批量 ``get_embeddings``，不存在时逐条 ``get_embedding``；
  单条失败跳过并记录 warning，**不写零向量**；
- 连接参数复用 ``config/default.yaml::memory.weaviate`` 与
  ``config/default.yaml::vector.embedding_dimension``，不在本模块硬编码；
- 懒连接：构造时不建连，首次操作时才尝试连接；连接失败置不可用且不抛异常。

设计边界（对齐 spec「向量适配约束」）：
- 除参数类型错误外，所有方法不得向调用方抛出异常；失败一律降级为空/0/False；
- 写入对象属性严格为：item_id / agent_id / item_type / title / content / tags /
  document_id / created_at。

@see .trae/specs/add-standalone-knowledge-base/spec.md
@see backend/core/memory/weaviate_store.py（只读参考，不修改）
"""

import inspect
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)

# --------------------------------------------------------------------------- #
# 绝对路径锚点（rules-0 §三：禁止相对路径 / ".."）
# --------------------------------------------------------------------------- #
_KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.dirname(_KNOWLEDGE_DIR)
_BACKEND_DIR = os.path.dirname(_CORE_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_EMBEDDED_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "weaviate_knowledge")

# 与 config/default.yaml 保持一致的默认值（配置缺失时兜底）
_DEFAULT_COLLECTION_PREFIX = "CXHMSKnowledge"
_DEFAULT_VECTOR_ENABLED = True
_DEFAULT_VECTOR_SIZE = 1024
_DEFAULT_WEAVIATE_HOST = "localhost"
_DEFAULT_WEAVIATE_PORT = 8090
_DEFAULT_WEAVIATE_GRPC_PORT = 50061
_DEFAULT_WEAVIATE_EMBEDDED = False
_DEFAULT_TOP_K_DEFAULT = 8
_DEFAULT_TOP_K_MAX = 50

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_]")


def _as_dict(value: Any) -> dict:
    """把任意值安全收敛为 dict（非映射返回空 dict）。"""
    return value if isinstance(value, dict) else {}


def _first_present(*values: Any) -> Any:
    """返回第一个非 None 值（用于扁平键 / 嵌套键的优先级回退）。"""
    for value in values:
        if value is not None:
            return value
    return None


def _coerce_int(value: Any, default: int) -> int:
    """安全转 int；非法值返回 default。"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool) -> bool:
    """安全转 bool；字符串 "false"/"0"/"no" 视为 False。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


class KnowledgeVectorIndex:
    """per-agent 知识库向量索引。

    Args:
        config: 由 ``KnowledgeManager`` 传入的配置字典（扁平键优先，
            同时兼容 ``knowledge`` / ``memory.weaviate`` / ``vector`` 嵌套结构）。
        embedding_model: 可选 embedding 客户端；支持 ``get_embeddings`` 或
            ``get_embedding``（可为同步或异步）。
    """

    def __init__(self, config: Optional[dict] = None, embedding_model: Any = None):
        config = _as_dict(config)
        self.config = dict(config)
        knowledge_cfg = _as_dict(config.get("knowledge"))
        memory_cfg = _as_dict(config.get("memory"))
        weaviate_cfg = _as_dict(memory_cfg.get("weaviate"))
        vector_cfg = _as_dict(config.get("vector"))

        self.collection_prefix = str(
            _first_present(
                config.get("collection_prefix"),
                knowledge_cfg.get("collection_prefix"),
                _DEFAULT_COLLECTION_PREFIX,
            )
        )
        self.vector_enabled = _coerce_bool(
            _first_present(
                config.get("vector_enabled"), knowledge_cfg.get("vector_enabled")
            ),
            _DEFAULT_VECTOR_ENABLED,
        )
        self.vector_size = _coerce_int(
            _first_present(
                config.get("vector_size"),
                vector_cfg.get("embedding_dimension"),
                weaviate_cfg.get("vector_size"),
                _DEFAULT_VECTOR_SIZE,
            ),
            _DEFAULT_VECTOR_SIZE,
        )
        self.weaviate_host = str(
            _first_present(
                config.get("weaviate_host"),
                weaviate_cfg.get("host"),
                _DEFAULT_WEAVIATE_HOST,
            )
        )
        self.weaviate_port = _coerce_int(
            _first_present(
                config.get("weaviate_port"),
                weaviate_cfg.get("port"),
                _DEFAULT_WEAVIATE_PORT,
            ),
            _DEFAULT_WEAVIATE_PORT,
        )
        self.weaviate_grpc_port = _coerce_int(
            _first_present(
                config.get("weaviate_grpc_port"),
                weaviate_cfg.get("grpc_port"),
                _DEFAULT_WEAVIATE_GRPC_PORT,
            ),
            _DEFAULT_WEAVIATE_GRPC_PORT,
        )
        self.weaviate_embedded = _coerce_bool(
            _first_present(
                config.get("weaviate_embedded"), weaviate_cfg.get("embedded")
            ),
            _DEFAULT_WEAVIATE_EMBEDDED,
        )
        self.weaviate_persistence_path = str(
            _first_present(
                config.get("weaviate_persistence_path"),
                _EMBEDDED_DATA_DIR,
            )
        )

        self.top_k_default = max(
            1,
            _coerce_int(
                _first_present(
                    config.get("vector_top_k_default"),
                    knowledge_cfg.get("vector_top_k_default"),
                    _DEFAULT_TOP_K_DEFAULT,
                ),
                _DEFAULT_TOP_K_DEFAULT,
            ),
        )
        self.top_k_max = max(
            self.top_k_default,
            _coerce_int(
                _first_present(
                    config.get("vector_top_k_max"),
                    knowledge_cfg.get("vector_top_k_max"),
                    _DEFAULT_TOP_K_MAX,
                ),
                _DEFAULT_TOP_K_MAX,
            ),
        )

        self.embedding_model = embedding_model

        # 懒连接状态：构造阶段不建连
        self._client = None
        self._connect_failed = False

    # ------------------------------------------------------------------ #
    # 命名与配置
    # ------------------------------------------------------------------ #

    def _safe_agent_id(self, agent_id: Any) -> str:
        """清洗 agent_id 为可用于 collection 名的安全片段。

        - ``default`` / 空值返回 ``""``（表示不加后缀）；
        - 非字母数字下划线字符替换为 ``_``；
        - 清洗后不以字母或下划线开头时补 ``agent_`` 前缀。

        Args:
            agent_id: 原始 agent 标识

        Returns:
            安全片段；``default`` 返回空字符串
        """
        if agent_id is None:
            return ""
        raw = str(agent_id).strip()
        if not raw or raw == "default":
            return ""
        safe = _SAFE_ID_RE.sub("_", raw)
        if safe == "":
            return ""
        if not (safe[0].isalpha() or safe[0] == "_"):
            safe = f"agent_{safe}"
        return safe

    def _collection_name(self, agent_id: Any) -> str:
        """生成 per-agent collection 名。

        Args:
            agent_id: 原始 agent 标识

        Returns:
            ``{collection_prefix}``（default）或
            ``{collection_prefix}_{safe_agent_id}``
        """
        safe_id = self._safe_agent_id(agent_id)
        if not safe_id:
            return self.collection_prefix
        return f"{self.collection_prefix}_{safe_id}"

    # ------------------------------------------------------------------ #
    # 连接与可用性
    # ------------------------------------------------------------------ #

    def _ensure_client(self):
        """懒连接 Weaviate；失败返回 None 且不抛异常。

        Returns:
            已连接的 weaviate 客户端，或 None
        """
        if self._client is not None:
            return self._client
        if self._connect_failed or not self.vector_enabled:
            return None

        try:
            import weaviate
            from weaviate.classes.init import AdditionalConfig, Timeout
        except ImportError:
            logger.warning("weaviate-client 未安装，知识库向量索引降级为不可用")
            self._connect_failed = True
            return None

        try:
            if self.weaviate_embedded:
                self._client = weaviate.connect_to_embedded(
                    version="1.26.1",
                    persistence_data_path=self.weaviate_persistence_path,
                )
                logger.info("知识库 Embedded Weaviate 已启动")
            else:
                self._client = weaviate.connect_to_local(
                    host=self.weaviate_host,
                    port=self.weaviate_port,
                    grpc_port=self.weaviate_grpc_port,
                    additional_config=AdditionalConfig(
                        timeout=Timeout(init=2, query=3, insert=120)
                    ),
                )
                logger.info(
                    "知识库 Weaviate 客户端已连接: "
                    f"{self.weaviate_host}:{self.weaviate_port}"
                )
            if not self._client.is_ready():
                logger.warning("知识库 Weaviate 客户端未就绪，降级为不可用")
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
                self._connect_failed = True
                return None
            return self._client
        except Exception as exc:  # 连接失败不抛，置不可用
            logger.warning(f"知识库 Weaviate 连接失败，降级为不可用: {exc}")
            self._client = None
            self._connect_failed = True
            return None

    def is_available(self) -> bool:
        """返回向量索引当前是否可用（启用 + 客户端可连接且就绪）。

        Returns:
            bool；任何异常均视为不可用
        """
        if not self.vector_enabled:
            return False
        client = self._ensure_client()
        if client is None:
            return False
        try:
            return bool(client.is_ready())
        except Exception as exc:
            logger.warning(f"知识库 Weaviate 就绪检查失败: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # collection 管理
    # ------------------------------------------------------------------ #

    def _ensure_collection(self, client: Any, agent_id: Any) -> Optional[str]:
        """确保目标 collection 存在（不存在则创建）。

        Args:
            client: weaviate 客户端
            agent_id: 原始 agent 标识

        Returns:
            collection 名；创建失败返回 None
        """
        name = self._collection_name(agent_id)
        try:
            if client.collections.exists(name):
                return name

            from weaviate.classes.config import Configure, DataType, Property

            client.collections.create(
                name=name,
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="item_id", data_type=DataType.TEXT),
                    Property(name="agent_id", data_type=DataType.TEXT),
                    Property(name="item_type", data_type=DataType.TEXT),
                    Property(name="title", data_type=DataType.TEXT),
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="tags", data_type=DataType.TEXT_ARRAY),
                    Property(name="document_id", data_type=DataType.TEXT),
                    Property(name="created_at", data_type=DataType.DATE),
                ],
            )
            logger.info(f"知识库 collection 已创建: {name} (agent_id={agent_id})")
            return name
        except Exception as exc:
            logger.warning(
                f"知识库 collection 创建/检查失败 (agent_id={agent_id}): {exc}"
            )
            return None

    def delete_agent_collection(self, agent_id: str) -> bool:
        """删除整个 per-agent collection（幂等）。

        Args:
            agent_id: 原始 agent 标识

        Returns:
            True 表示删除成功或本来就不存在；不可用时 False
        """
        if not self.vector_enabled:
            return False
        client = self._ensure_client()
        if client is None:
            return False

        name = self._collection_name(agent_id)
        try:
            if client.collections.exists(name):
                client.collections.delete(name)
                logger.info(f"知识库 collection 已删除: {name} (agent_id={agent_id})")
            else:
                logger.debug(f"知识库 collection 不存在，跳过删除: {name}")
            return True
        except Exception as exc:
            logger.warning(f"知识库 collection 删除失败 (agent_id={agent_id}): {exc}")
            return False

    # ------------------------------------------------------------------ #
    # embedding 适配
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        """若为 awaitable 则 await，否则原样返回（兼容同步/异步 embedding 客户端）。"""
        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def _normalize_vector(value: Any) -> Optional[list[float]]:
        """校验并归一化向量；空/非法/全零向量返回 None（不写零向量）。"""
        if value is None:
            return None
        if isinstance(value, (str, bytes)):
            return None
        try:
            vector = [float(component) for component in value]
        except (TypeError, ValueError):
            logger.warning("embedding 返回值非数值序列，跳过该条")
            return None
        if not vector:
            logger.warning("embedding 返回空向量，跳过该条")
            return None
        if all(component == 0.0 for component in vector):
            logger.warning("embedding 返回全零向量，跳过该条（不写零向量）")
            return None
        return vector

    async def _embed_texts(self, texts: list[str]) -> list[Optional[list[float]]]:
        """为文本列表生成向量。

        优先批量 ``get_embeddings``；不存在或批量失败/长度不匹配时，逐条
        ``get_embedding``。单条失败返回 None（调用方跳过该条）。

        Args:
            texts: 待嵌入文本

        Returns:
            与输入等长的向量列表，失败位为 None
        """
        if not texts:
            return []
        if self.embedding_model is None:
            logger.warning("embedding_model 为空，知识库向量写入/检索跳过")
            return [None for _ in texts]

        batch_fn = getattr(self.embedding_model, "get_embeddings", None)
        if callable(batch_fn):
            try:
                batch_result = await self._maybe_await(batch_fn(list(texts)))
                if batch_result is not None and len(batch_result) == len(texts):
                    normalized = [self._normalize_vector(v) for v in batch_result]
                    if all(v is not None for v in normalized):
                        return normalized
                    logger.warning(
                        "embedding 批量结果含空/零向量，逐条降级重试"
                    )
                elif batch_result is not None:
                    logger.warning(
                        "embedding 批量结果长度不匹配 "
                        f"(expected={len(texts)}, got={len(batch_result)})，逐条降级"
                    )
            except Exception as exc:
                logger.warning(f"embedding 批量调用失败，逐条降级: {exc}")

        single_fn = getattr(self.embedding_model, "get_embedding", None)
        results: list[Optional[list[float]]] = []
        for text in texts:
            if not callable(single_fn):
                results.append(None)
                continue
            try:
                value = await self._maybe_await(single_fn(text))
                results.append(self._normalize_vector(value))
            except Exception as exc:
                logger.warning(f"embedding 单条调用失败，跳过该条: {exc}")
                results.append(None)
        return results

    # ------------------------------------------------------------------ #
    # 对象属性与删除
    # ------------------------------------------------------------------ #

    @staticmethod
    def _created_at_value(value: Any) -> str:
        """把 created_at 规整为带时区的 RFC3339 字符串（DATE 属性要求）。"""
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.strip())
            except ValueError:
                logger.warning(f"created_at 非法，使用当前时间: {value}")
            else:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.isoformat()
        return datetime.now().astimezone().isoformat()

    def _build_properties(self, item: dict, agent_id: Any) -> dict:
        """构造 Weaviate 对象属性（字段集严格对齐任务契约）。"""
        return {
            "item_id": str(item.get("item_id") or ""),
            "agent_id": str(item.get("agent_id") or agent_id or ""),
            "item_type": str(item.get("item_type") or "doc_chunk"),
            "title": str(item.get("title") or ""),
            "content": str(item.get("content") or ""),
            "tags": [str(tag) for tag in (item.get("tags") or [])],
            "document_id": str(item.get("document_id") or ""),
            "created_at": self._created_at_value(item.get("created_at")),
        }

    @staticmethod
    def _delete_item_objects(collection: Any, item_id: str) -> int:
        """按 item_id 删除 collection 内既有对象（upsert 的先删后插 / delete 复用）。

        Args:
            collection: weaviate collection 对象
            item_id: 知识条目 ID

        Returns:
            删除对象数；失败返回 0（异常不抛）
        """
        if not item_id:
            return 0
        try:
            from weaviate.classes.query import Filter

            result = collection.query.fetch_objects(
                filters=Filter.by_property("item_id").equal(item_id), limit=100
            )
            deleted = 0
            for obj in result.objects:
                collection.data.delete_by_id(obj.uuid)
                deleted += 1
            return deleted
        except Exception as exc:
            logger.warning(f"知识库向量按 item_id 删除失败 (item_id={item_id}): {exc}")
            return 0

    # ------------------------------------------------------------------ #
    # 公开操作
    # ------------------------------------------------------------------ #

    async def upsert(self, agent_id: str, items: list[dict]) -> int:
        """写入/更新知识条目的向量。

        逐条嵌入并先删同 item_id 的既有对象再插入（幂等覆盖）；嵌入失败或写入
        失败的条目跳过并记录 warning，不写零向量。

        Args:
            agent_id: 原始 agent 标识
            items: 知识条目字典列表（含 item_id / content 等字段）

        Returns:
            成功写入的条目数
        """
        if not self.vector_enabled or not items:
            return 0
        client = self._ensure_client()
        if client is None:
            return 0

        name = self._ensure_collection(client, agent_id)
        if not name:
            return 0

        try:
            collection = client.collections.get(name)
        except Exception as exc:
            logger.warning(f"知识库 collection 获取失败 ({name}): {exc}")
            return 0

        valid_items = [item for item in items if isinstance(item, dict)]
        texts = [str(item.get("content") or "") for item in valid_items]
        vectors = await self._embed_texts(texts)

        written = 0
        for item, vector in zip(valid_items, vectors):
            if vector is None:
                logger.warning(
                    "知识库向量写入跳过: "
                    f"item_id={item.get('item_id')} 原因=embedding 不可用"
                )
                continue
            item_id = str(item.get("item_id") or "")
            if not item_id:
                logger.warning("知识库向量写入跳过: item_id 为空")
                continue
            try:
                # 先删后插，保证同一 item_id 至多 1 个对象（upsert 语义）
                self._delete_item_objects(collection, item_id)
                collection.data.insert(
                    properties=self._build_properties(item, agent_id), vector=vector
                )
                written += 1
            except Exception as exc:
                logger.warning(
                    f"知识库向量写入失败，跳过该条 (item_id={item_id}): {exc}"
                )
        return written

    async def search(
        self,
        agent_id: str,
        query: str,
        limit: int = 8,
        tags: Optional[list[str]] = None,
    ) -> list[dict]:
        """在 per-agent collection 中执行向量检索。

        Args:
            agent_id: 原始 agent 标识
            query: 查询文本
            limit: 返回条数上限（受 ``vector_top_k_max`` 约束）
            tags: 可选标签过滤（任一命中）

        Returns:
            命中列表 ``[{item_id,title,content,score,item_type,document_id,tags}]``；
            不可用或失败返回 ``[]``
        """
        if not self.vector_enabled:
            return []
        client = self._ensure_client()
        if client is None:
            return []

        name = self._collection_name(agent_id)
        try:
            if not client.collections.exists(name):
                logger.debug(f"知识库 collection 不存在，检索返回空: {name}")
                return []
            collection = client.collections.get(name)
        except Exception as exc:
            logger.warning(f"知识库 collection 获取失败 ({name}): {exc}")
            return []

        vectors = await self._embed_texts([str(query or "")])
        query_vector = vectors[0] if vectors else None
        if query_vector is None:
            logger.warning("知识库检索跳过: 查询向量不可用")
            return []

        effective_limit = max(
            1, min(_coerce_int(limit, self.top_k_default), self.top_k_max)
        )
        try:
            vector_query = collection.query.near_vector(
                near_vector=query_vector,
                limit=effective_limit,
                return_metadata=["distance"],
            )
            if tags:
                from weaviate.classes.query import Filter

                vector_query = vector_query.with_filters(
                    Filter.by_property("tags").contains_any([str(t) for t in tags])
                )
            results = vector_query.objects
        except Exception as exc:
            logger.warning(f"知识库向量检索失败 ({name}): {exc}")
            return []

        hits: list[dict] = []
        for obj in results:
            try:
                metadata = getattr(obj, "metadata", None)
                distance = getattr(metadata, "distance", None) if metadata else None
                if isinstance(distance, (int, float)):
                    # 与 Weaviate certainty 公式一致：similarity = 1 - distance/2
                    score = 1.0 - float(distance) / 2.0
                else:
                    score = 0.0
                properties = _as_dict(obj.properties)
                hits.append(
                    {
                        "item_id": properties.get("item_id"),
                        "title": properties.get("title"),
                        "content": properties.get("content"),
                        "score": score,
                        "item_type": properties.get("item_type"),
                        "document_id": properties.get("document_id"),
                        "tags": list(properties.get("tags") or []),
                    }
                )
            except Exception as exc:
                logger.warning(f"知识库检索结果解析失败，跳过该条: {exc}")
        return hits

    async def delete(self, agent_id: str, item_ids: list[str]) -> int:
        """按 item_id 删除向量对象。

        Args:
            agent_id: 原始 agent 标识
            item_ids: 待删除的条目 ID 列表

        Returns:
            实际删除的对象数；不可用/失败返回 0
        """
        if not self.vector_enabled or not item_ids:
            return 0
        client = self._ensure_client()
        if client is None:
            return 0

        name = self._collection_name(agent_id)
        try:
            if not client.collections.exists(name):
                logger.debug(f"知识库 collection 不存在，删除空操作: {name}")
                return 0
            collection = client.collections.get(name)
        except Exception as exc:
            logger.warning(f"知识库 collection 获取失败 ({name}): {exc}")
            return 0

        deleted = 0
        for item_id in item_ids:
            deleted += self._delete_item_objects(collection, str(item_id or ""))
        return deleted

    def close(self) -> None:
        """关闭客户端连接（失败忽略，幂等）。"""
        if self._client is None:
            return
        try:
            self._client.close()
            logger.info("知识库 Weaviate 连接已关闭")
        except Exception as exc:
            logger.warning(f"关闭知识库 Weaviate 客户端失败: {exc}")
        finally:
            self._client = None
            self._connect_failed = False


__all__ = ["KnowledgeVectorIndex"]
