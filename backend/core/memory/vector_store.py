from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    total_checked: int = 0
    synced: int = 0
    removed: int = 0
    errors: int = 0
    details: List[str] = None


class VectorStoreBase:
    """向量存储基类"""
    
    def is_available(self) -> bool:
        """检查向量存储是否可用"""
        raise NotImplementedError

    async def add_memory_vector(
        self,
        memory_id: int,
        content: str,
        embedding: List[float],
        metadata: Dict = None
    ) -> bool:
        """添加记忆向量"""
        raise NotImplementedError

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 10,
        memory_type: str = None,
        min_score: float = 0.5
    ) -> List[Dict]:
        """搜索相似向量"""
        raise NotImplementedError

    async def delete_by_memory_id(self, memory_id: int) -> bool:
        """根据记忆ID删除向量"""
        raise NotImplementedError

    async def get_vector_by_id(self, memory_id: int) -> Optional[Dict]:
        """根据ID获取向量"""
        raise NotImplementedError

    async def check_exists(self, memory_id: int) -> bool:
        """检查向量是否存在"""
        raise NotImplementedError

    async def sync_with_sqlite(self, sqlite_manager) -> SyncResult:
        """与SQLite同步数据"""
        raise NotImplementedError

    def get_collection_info(self) -> Dict:
        """获取集合信息"""
        raise NotImplementedError

    def clear_collection(self) -> bool:
        """清空集合"""
        raise NotImplementedError

    def close(self):
        """关闭连接"""
        raise NotImplementedError


class QdrantVectorStore(VectorStoreBase):
    """Qdrant向量存储实现"""
    COLLECTION_NAME = "memory_vectors"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        vector_size: int = 768,
        collection_name: str = None,
        embedding_model=None
    ):
        self.host = host
        self.port = port
        self.vector_size = vector_size
        self.collection_name = collection_name or self.COLLECTION_NAME
        self.embedding_model = embedding_model

        self._client = None
        self._lock = threading.Lock()
        self._initialize_client()

    def _initialize_client(self):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance, PointStruct

            self._client = QdrantClient(host=self.host, port=self.port)
            self._ensure_collection()
            logger.info(f"Qdrant向量存储初始化完成: {self.host}:{self.port}")
        except ImportError:
            logger.warning("qdrant-client未安装，向量功能不可用")
            self._client = None

    def _ensure_collection(self):
        if not self._client:
            return

        try:
            collections = self._client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name not in collection_names:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"创建Qdrant集合: {self.collection_name}")
        except Exception as e:
            logger.error(f"检查/创建集合失败: {e}")

    def is_available(self) -> bool:
        return self._client is not None

    async def add_memory_vector(
        self,
        memory_id: int,
        content: str,
        embedding: List[float],
        metadata: Dict = None
    ):
        if not self._client:
            return False

        try:
            from qdrant_client.models import PointStruct

            point = PointStruct(
                id=memory_id,
                vector=embedding,
                payload={
                    "content": content,
                    "memory_id": memory_id,
                    "created_at": datetime.now().isoformat(),
                    **(metadata or {})
                }
            )
            self._client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            logger.debug(f"向量已添加: memory_id={memory_id}")
            return True
        except Exception as e:
            logger.error(f"添加向量失败: {e}")
            return False

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 10,
        memory_type: str = None,
        min_score: float = 0.5
    ) -> List[Dict]:
        if not self._client:
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            search_filter = None
            if memory_type:
                search_filter = Filter(
                    must=[
                        FieldCondition(
                            key="type",
                            match=MatchValue(value=memory_type)
                        )
                    ]
                )

            results = self._client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                query_filter=search_filter
            )

            filtered_results = [
                {
                    "memory_id": r.id,
                    "score": r.score,
                    "content": r.payload.get("content"),
                    "metadata": r.payload
                }
                for r in results
                if r.score >= min_score
            ]

            return filtered_results
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []

    async def delete_by_memory_id(self, memory_id: int) -> bool:
        if not self._client:
            return False

        try:
            self._client.delete_points(
                collection_name=self.collection_name,
                points=[memory_id]
            )
            return True
        except Exception as e:
            logger.error(f"删除向量失败: {e}")
            return False

    async def get_vector_by_id(self, memory_id: int) -> Optional[Dict]:
        if not self._client:
            return None

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            results = self._client.search(
                collection_name=self.collection_name,
                query_vector=[0.0] * self.vector_size,
                limit=1,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="memory_id",
                            match=MatchValue(value=memory_id)
                        )
                    ]
                )
            )

            if results:
                r = results[0]
                return {
                    "memory_id": r.id,
                    "content": r.payload.get("content"),
                    "metadata": r.payload
                }
            return None
        except Exception as e:
            logger.error(f"获取向量失败: {e}")
            return None

    async def check_exists(self, memory_id: int) -> bool:
        result = await self.get_vector_by_id(memory_id)
        return result is not None

    async def sync_with_sqlite(self, sqlite_manager) -> SyncResult:
        if not self._client:
            return SyncResult(errors=1, details=["Qdrant不可用"])

        result = SyncResult(details=[])

        try:
            logger.info("开始SQLite与Qdrant数据同步...")

            memories = sqlite_manager.search_memories(
                memory_type=None,
                limit=10000,
                include_deleted=False
            )

            qdrant_ids = set()
            result.total_checked = len(memories)

            for memory in memories:
                memory_id = memory["id"]
                content = memory["content"]
                qdrant_ids.add(memory_id)

                try:
                    existing = await self.get_vector_by_id(memory_id)

                    if existing is None:
                        logger.info(f"向量不存在，创建: memory_id={memory_id}")
                        if self.embedding_model:
                            embedding = await self.embedding_model.get_embedding(content)
                            await self.add_memory_vector(
                                memory_id=memory_id,
                                content=content,
                                embedding=embedding,
                                metadata=memory
                            )
                            result.synced += 1
                            result.details.append(f"创建: {memory_id}")
                    elif existing.get("content") != content:
                        logger.info(f"内容不一致，更新: memory_id={memory_id}")
                        if self.embedding_model:
                            embedding = await self.embedding_model.get_embedding(content)
                            await self.delete_by_memory_id(memory_id)
                            await self.add_memory_vector(
                                memory_id=memory_id,
                                content=content,
                                embedding=embedding,
                                metadata=memory
                            )
                            result.synced += 1
                            result.details.append(f"更新: {memory_id}")

                except Exception as e:
                    result.errors += 1
                    logger.error(f"同步记忆失败: {memory_id}, {e}")

            logger.info(f"同步完成: checked={result.total_checked}, synced={result.synced}, errors={result.errors}")

        except Exception as e:
            result.errors += 1
            result.details.append(f"同步过程错误: {e}")
            logger.error(f"同步过程失败: {e}")

        return result

    def get_collection_info(self) -> Dict:
        if not self._client:
            return {"error": "Qdrant不可用"}

        try:
            info = self._client.get_collection(self.collection_name)
            return {
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status,
                "collection_name": self.collection_name
            }
        except Exception as e:
            return {"error": str(e)}

    def clear_collection(self) -> bool:
        if not self._client:
            return False

        try:
            from qdrant_client.models import Filter

            self._client.delete_points(
                collection_name=self.collection_name,
                points=Filter()
            )
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
                logger.warning(f"关闭Qdrant客户端失败: {e}")


def create_vector_store(
    backend: str = "milvus_lite",
    **kwargs
) -> VectorStoreBase:
    """
    创建向量存储实例
    
    Args:
        backend: 向量存储后端类型 ("milvus_lite", "qdrant")
        **kwargs: 向量存储配置参数
    
    Returns:
        VectorStoreBase: 向量存储实例
    """
    if backend == "milvus_lite":
        from .milvus_lite_store import MilvusLiteVectorStore
        return MilvusLiteVectorStore(**kwargs)
    elif backend == "qdrant":
        return QdrantVectorStore(**kwargs)
    else:
        logger.warning(f"未知的向量存储后端: {backend}, 使用Milvus Lite")
        from .milvus_lite_store import MilvusLiteVectorStore
        return MilvusLiteVectorStore(**kwargs)
