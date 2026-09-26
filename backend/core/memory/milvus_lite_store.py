import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


@dataclass
class SyncResult:
    total_checked: int = 0
    synced: int = 0
    removed: int = 0
    errors: int = 0
    skipped: int = 0
    details: List[str] = None


class MilvusLiteVectorStore:
    COLLECTION_NAME = "memory_vectors"

    # 回滚取回查询的字段分级（GN-004 第十四轮 O-1）：
    # 基础字段 = 向量回滚材料（必需）；扩展字段 = metadata 投影（可选，schema 缺失时降级丢弃）
    _BASE_OUTPUT_FIELDS = ["vector", "content", "memory_id"]
    _EXTENDED_OUTPUT_FIELDS = [
        *_BASE_OUTPUT_FIELDS,
        "created_at",
        "agent_id",
        "type",
        "importance",
    ]

    def __init__(
        self,
        db_path: str = "data/milvus_lite.db",
        vector_size: int = 768,
        collection_name: str = None,
        embedding_model=None,
    ):
        self.db_path = db_path
        self.vector_size = vector_size
        self.collection_name = collection_name or self.COLLECTION_NAME
        self.embedding_model = embedding_model

        self._client = None
        self._collection = None
        self._lock = threading.Lock()
        self._initialize_client()

    def _initialize_client(self):
        try:
            from pymilvus import MilvusClient

            os.makedirs(
                os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".",
                exist_ok=True,
            )

            self._client = MilvusClient(self.db_path)
            self._ensure_collection()
            logger.info(f"Milvus Lite向量存储初始化完成: {self.db_path}")
        except ImportError:
            logger.warning("pymilvus未安装，向量功能不可用")
            self._client = None
        except Exception as e:
            logger.error(f"Milvus Lite初始化失败: {e}")
            self._client = None

    def _ensure_collection(self):
        if not self._client:
            return

        try:
            collections = self._client.list_collections()

            if self.collection_name not in collections:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    dimension=self.vector_size,
                    metric_type="COSINE",
                )
                logger.info(f"创建Milvus Lite集合: {self.collection_name}")
        except Exception as e:
            logger.error(f"检查/创建集合失败: {e}")

    def is_available(self) -> bool:
        return self._client is not None

    async def add_memory_vector(
        self, memory_id: int, content: str, embedding: List[float], metadata: Dict = None
    ) -> bool:
        if not self._client:
            return False

        # 空向量防御：embedding 为空（None / 空序列）时写入会产生无向量对象，
        # 读取路径将抛异常，故直接拒绝写入（日志如实，不谎报成功）。
        if not embedding:
            logger.warning(
                f"Milvus Lite 空向量防御: memory_id={memory_id}, "
                f"原因=embedding 为空（None 或空序列），未写入"
            )
            return False

        previous = None  # 前置初始化：except 中引用时不受「被调函数是否抛异常」影响（GN-004 第十二轮 N-3）
        try:
            # 写入幂等：Milvus insert 为追加语义，重复写入会产生重复实体，
            # 故插入前先删除同 memory_id 的既存实体（先删后插），使同一 memory_id 至多保留 1 个实体。
            # 无旧实体时 delete_by_memory_id 返回 False 属正常，不作为失败处理。
            # 回滚材料：删除前先取回旧实体（含向量），若插入抛异常则回填——避免「旧已删、新未写」
            previous = await self._get_vector_with_embedding(memory_id)
            await self.delete_by_memory_id(memory_id)

            data = [
                {
                    "id": memory_id,
                    "vector": embedding,
                    "content": content,
                    "memory_id": memory_id,
                    "created_at": datetime.now().isoformat(),
                    **(metadata or {}),
                }
            ]

            self._client.insert(collection_name=self.collection_name, data=data)
            logger.debug(f"向量已添加: memory_id={memory_id}")
            return True
        except Exception as e:
            logger.error(f"添加向量失败: {e}")
            await self._rollback_to_previous(previous)
            return False

    async def _get_vector_with_embedding(self, memory_id: int) -> Optional[Dict]:
        """取回含向量的既有实体（供「先删后插」失败回滚使用）。

        ``get_vector_by_id`` 的 ``output_fields`` 不含向量字段，故此处单独查询。

        字段分级 + 降级重试（GN-004 第十四轮 O-1）：先按扩展字段查询（向量 + metadata 投影），
        若因 schema 缺字段而失败，则降级为仅基础字段重试——**保证向量回滚材料仍可得**，
        避免「为保留 metadata 反而使向量回滚一并失效」。

        Args:
            memory_id: 记忆 ID

        Returns:
            含 ``vector`` / ``content`` / ``metadata`` 的字典；不存在或两次查询均失败时返回 None
        """
        if not self._client:
            return None

        for fields, is_fallback in (
            (self._EXTENDED_OUTPUT_FIELDS, False),
            (self._BASE_OUTPUT_FIELDS, True),
        ):
            try:
                results = self._client.query(
                    collection_name=self.collection_name,
                    filter=f'memory_id == "{memory_id}"',
                    output_fields=list(fields),
                )
                if results:
                    r = results[0]
                    if is_fallback:
                        logger.warning(
                            f"扩展字段查询失败，已降级为仅取回向量（metadata 投影无法保留）: "
                            f"memory_id={memory_id}"
                        )
                    return {
                        "vector": r.get("vector"),
                        "content": r.get("content"),
                        "metadata": r,
                    }
                return None
            except Exception as e:  # noqa: BLE001
                if is_fallback:
                    logger.warning(f"取回旧向量失败（将无法回滚）: memory_id={memory_id}, {e}")
                    return None
                logger.warning(
                    f"扩展字段查询异常，尝试降级为仅取回向量: memory_id={memory_id}, {e}"
                )
        return None

    async def _rollback_to_previous(self, previous: Optional[Dict]) -> None:
        """插入失败后尽力回填删除前的旧实体（best-effort，失败仅记日志）。

        Args:
            previous: 删除前取回的旧实体（含 vector）；为空则无旧实体可回填
        """
        if not previous or not previous.get("vector"):
            return
        try:
            meta = previous.get("metadata") or {}
            memory_id = meta.get("memory_id")
            # 回填须保留原 metadata 投影字段（agent_id / type / importance 等），
            # 否则 agent 隔离过滤会漏检（GN-004 第十二轮 N-2；取回侧见 F-2）
            payload = {
                k: v
                for k, v in meta.items()
                if k not in ("id", "vector", "memory_id", "created_at", "content")
            }
            self._client.insert(
                collection_name=self.collection_name,
                data=[
                    {
                        "id": memory_id,
                        "vector": previous["vector"],
                        "content": previous.get("content") or "",
                        "memory_id": memory_id,
                        "created_at": meta.get("created_at") or datetime.now().isoformat(),
                        **payload,
                    }
                ],
            )
            logger.warning(f"插入失败后已回填旧向量: memory_id={memory_id}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"回填旧向量失败（旧向量已丢失）: {e}")

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 10,
        memory_type: str = None,
        min_score: float = 0.5,
        agent_id: str = None,
    ) -> List[Dict]:
        if not self._client:
            return []

        try:
            # 构建过滤表达式，支持 agent_id 过滤（agent 隔离）
            expr_parts = []
            if memory_type:
                expr_parts.append(f'type == "{memory_type}"')
            if agent_id and agent_id != "default":
                expr_parts.append(f'agent_id == "{agent_id}"')
            expr = " and ".join(expr_parts) if expr_parts else None

            search_kwargs = {
                "collection_name": self.collection_name,
                "data": [query_embedding],
                "limit": limit,
                "output_fields": ["content", "memory_id", "created_at"],
            }
            if expr:
                search_kwargs["filter"] = expr

            results = self._client.search(**search_kwargs)

            filtered_results = []
            for result in results[0]:
                # Milvus 返回的是距离（越小越相似），用 1 - distance 转为相似度分数
                similarity_score = 1 - result["distance"]
                if similarity_score >= min_score:
                    filtered_results.append(
                        {
                            "memory_id": result["id"],
                            "score": similarity_score,
                            "content": result["entity"].get("content"),
                            "metadata": result["entity"],
                        }
                    )

            return filtered_results
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []

    async def delete_by_memory_id(self, memory_id: int) -> bool:
        if not self._client:
            return False

        try:
            self._client.delete(collection_name=self.collection_name, ids=[memory_id])
            return True
        except Exception as e:
            logger.error(f"删除向量失败: {e}")
            return False

    async def get_vector_by_id(self, memory_id: int) -> Optional[Dict]:
        if not self._client:
            return None

        try:
            if not isinstance(memory_id, int):
                logger.warning(f"无效的memory_id类型: {type(memory_id)}, 期望int")
                return None

            results = self._client.query(
                collection_name=self.collection_name,
                filter=f'memory_id == "{memory_id}"',
                output_fields=["content", "memory_id", "created_at"],
            )

            if results:
                r = results[0]
                return {"memory_id": r["id"], "content": r.get("content"), "metadata": r}
            return None
        except Exception as e:
            logger.error(f"获取向量失败: {e}")
            return None

    async def check_exists(self, memory_id: int) -> bool:
        result = await self.get_vector_by_id(memory_id)
        return result is not None

    async def sync_with_sqlite(self, sqlite_manager, last_sync_time: str = None) -> SyncResult:
        if not self._client:
            return SyncResult(errors=1, details=["Milvus Lite不可用"])

        result = SyncResult(details=[])

        try:
            if last_sync_time:
                logger.info(f"开始增量同步 (since {last_sync_time})...")
            else:
                logger.info("开始SQLite与Milvus Lite全量数据同步...")

            memories = sqlite_manager.search_memories(
                memory_type=None, limit=10000, include_deleted=False
            )

            if last_sync_time:
                memories = [
                    m
                    for m in memories
                    if m.get("updated_at") and m.get("updated_at") > last_sync_time
                ]
                logger.info(f"增量同步: 筛选出 {len(memories)} 条需要同步的记忆")

            result.total_checked = len(memories)

            for memory in memories:
                memory_id = memory["id"]
                content = memory["content"]

                try:
                    existing = await self.get_vector_by_id(memory_id)

                    if existing is None:
                        logger.info(f"向量不存在，创建: memory_id={memory_id}")
                        if self.embedding_model:
                            embedding = await self.embedding_model.get_embedding(content)
                            success = await self.add_memory_vector(
                                memory_id=memory_id,
                                content=content,
                                embedding=embedding,
                                metadata=memory,
                            )
                            if success:
                                result.synced += 1
                                result.details.append(f"创建: {memory_id}")
                            else:
                                # 未写入（空向量防御等返回 False）：如实计 errors，不虚报 synced（对齐 chroma 口径）
                                result.errors += 1
                        else:
                            # embedding 模型缺失：未尝试写入，计 skipped（区别于写入失败的 errors；GN-004 第十/十一轮 O-2）
                            result.skipped += 1
                    elif existing.get("content") != content:
                        logger.info(f"内容不一致，更新: memory_id={memory_id}")
                        if self.embedding_model:
                            embedding = await self.embedding_model.get_embedding(content)
                            # 不再在此处 delete：add_memory_vector 内部已「先删后插」并持有回滚材料；
                            # 外层 delete 会使内部取回的 previous 恒为 None，回滚被架空（GN-004 第十二轮 N-1）
                            success = await self.add_memory_vector(
                                memory_id=memory_id,
                                content=content,
                                embedding=embedding,
                                metadata=memory,
                            )
                            if success:
                                result.synced += 1
                                result.details.append(f"更新: {memory_id}")
                            else:
                                # 未写入（空向量防御等返回 False）：如实计 errors，不虚报 synced（对齐 chroma 口径）
                                result.errors += 1
                        else:
                            # embedding 模型缺失：未尝试写入，计 skipped（区别于写入失败的 errors；GN-004 第十/十一轮 O-2）
                            result.skipped += 1

                except Exception as e:
                    result.errors += 1
                    logger.error(f"同步记忆失败: {memory_id}, {e}")

            logger.info(
                f"同步完成: checked={result.total_checked}, synced={result.synced}, "
                f"errors={result.errors}, skipped={result.skipped}"
            )

        except Exception as e:
            result.errors += 1
            result.details.append(f"同步过程错误: {e}")
            logger.error(f"同步过程失败: {e}")

        return result

    def get_collection_info(self) -> Dict:
        if not self._client:
            return {"error": "Milvus Lite不可用"}

        try:
            info = self._client.get_collection_stats(collection_name=self.collection_name)
            return {
                "row_count": info.get("row_count", 0),
                "status": "active",
                "collection_name": self.collection_name,
                "dimension": self.vector_size,
            }
        except Exception as e:
            return {"error": str(e)}

    def clear_collection(self) -> bool:
        if not self._client:
            return False

        try:
            self._client.drop_collection(collection_name=self.collection_name)
            self._ensure_collection()
            logger.info(f"集合已清空: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"清空集合失败: {e}")
            return False

    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"关闭Milvus Lite客户端失败: {e}")
