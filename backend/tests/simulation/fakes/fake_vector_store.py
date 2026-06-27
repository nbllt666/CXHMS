"""内存向量存储的假实现，用于端到端测试。

不依赖任何外部向量数据库（Qdrant、Milvus、Chroma 等），
所有记录保存在内存 list 中，方便测试断言与清理。
"""

import math
import threading
from typing import Dict, List, Optional

from backend.core.memory.vector_store import SyncResult, VectorStoreBase


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度。

    对于零向量或长度为零的输入返回 0.0，避免除零错误。
    """
    if not a or not b:
        return 0.0

    # 长度不一致时按较短的截断，避免测试中维度不匹配导致崩溃
    min_len = min(len(a), len(b))
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(min_len):
        av = a[i]
        bv = b[i]
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class InMemoryVectorStore(VectorStoreBase):
    """基于内存 list 的向量存储，用于测试。

    所有方法均为线程安全（使用 threading.Lock 保护内部 list）。
    行为对齐真实 VectorStoreBase 契约，但不访问任何外部服务。
    """

    def __init__(self):
        self._records: List[Dict] = []
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return True

    async def add_memory_vector(
        self,
        memory_id: int,
        content: str,
        embedding: List[float],
        metadata: Dict = None,
    ) -> bool:
        record = {
            "memory_id": memory_id,
            "content": content,
            "embedding": list(embedding) if embedding is not None else [],
            "metadata": dict(metadata) if metadata else {},
        }
        with self._lock:
            # 同 memory_id 重复添加则覆盖
            for i, existing in enumerate(self._records):
                if existing["memory_id"] == memory_id:
                    self._records[i] = record
                    return True
            self._records.append(record)
        return True

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 10,
        memory_type: str = None,
        min_score: float = 0.5,
        agent_id: str = None,
    ) -> List[Dict]:
        with self._lock:
            # 复制一份快照，避免在锁外计算时被并发修改
            snapshot = [
                {
                    "memory_id": r["memory_id"],
                    "content": r["content"],
                    "embedding": list(r["embedding"]),
                    "metadata": dict(r["metadata"]),
                }
                for r in self._records
            ]

        scored = []
        for r in snapshot:
            metadata = r["metadata"]
            # memory_type 过滤：metadata.get("memory_type") 或 metadata.get("type")
            if memory_type is not None:
                rec_type = metadata.get("memory_type", metadata.get("type"))
                if rec_type != memory_type:
                    continue
            # agent_id 过滤：metadata.get("agent_id")
            if agent_id is not None:
                rec_agent = metadata.get("agent_id")
                if rec_agent != agent_id:
                    continue

            score = cosine_similarity(query_embedding, r["embedding"])
            if score < min_score:
                continue
            scored.append(
                {
                    "memory_id": r["memory_id"],
                    "content": r["content"],
                    "score": score,
                    "metadata": metadata,
                }
            )

        # 按相似度降序排序，取前 limit 个
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    async def delete_by_memory_id(self, memory_id: int) -> bool:
        with self._lock:
            for i, existing in enumerate(self._records):
                if existing["memory_id"] == memory_id:
                    del self._records[i]
                    return True
        return False

    async def get_vector_by_id(self, memory_id: int) -> Optional[Dict]:
        with self._lock:
            for r in self._records:
                if r["memory_id"] == memory_id:
                    # 返回包含 embedding 的完整记录
                    return {
                        "memory_id": r["memory_id"],
                        "content": r["content"],
                        "embedding": list(r["embedding"]),
                        "metadata": dict(r["metadata"]),
                    }
        return None

    async def check_exists(self, memory_id: int) -> bool:
        with self._lock:
            return any(r["memory_id"] == memory_id for r in self._records)

    async def sync_with_sqlite(self, sqlite_manager, last_sync_time: str = None) -> SyncResult:
        # 测试用：不进行真实同步，直接返回空结果
        return SyncResult(total_checked=0, synced=0, removed=0, errors=0, details=[])

    def get_collection_info(self) -> Dict:
        with self._lock:
            count = len(self._records)
        return {
            "status": "available",
            "name": "in_memory",
            "count": count,
        }

    def clear_collection(self) -> bool:
        with self._lock:
            self._records.clear()
        return True

    def close(self):
        # no-op
        return None
