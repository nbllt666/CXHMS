"""
去重检测模块
检测相似记忆并记录重复关系
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


@dataclass
class DuplicateGroup:
    """去重组"""

    group_id: str
    memory_ids: List[int] = field(default_factory=list)
    canonical_id: Optional[int] = None  # 代表记忆ID
    similarity_matrix: Dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    merged: bool = False
    merged_at: Optional[str] = None
    merged_into: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "memory_ids": self.memory_ids,
            "canonical_id": self.canonical_id,
            "similarity_matrix": self.similarity_matrix,
            "created_at": self.created_at,
            "merged": self.merged,
            "merged_at": self.merged_at,
            "merged_into": self.merged_into,
        }


@dataclass
class SimilarityRecord:
    """相似性记录"""

    memory_id_1: int
    memory_id_2: int
    similarity_score: float
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_duplicate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id_1": self.memory_id_1,
            "memory_id_2": self.memory_id_2,
            "similarity_score": self.similarity_score,
            "checked_at": self.checked_at,
            "is_duplicate": self.is_duplicate,
        }


class DeduplicationEngine:
    """去重检测引擎"""

    def __init__(self, memory_manager, threshold: float = 0.85):
        self.memory_manager = memory_manager
        self.threshold = threshold
        self._similarity_cache: Dict[str, float] = {}
        self._duplicate_groups: Dict[str, DuplicateGroup] = {}

    def _generate_group_id(self, memory_ids: List[int]) -> str:
        """生成去重组ID"""
        sorted_ids = sorted(memory_ids)
        id_str = ",".join(map(str, sorted_ids))
        return hashlib.md5(id_str.encode()).hexdigest()[:16]

    async def check_similarity(self, memory_id_1: int, memory_id_2: int) -> float:
        """检查两个记忆的相似度

        优先使用向量余弦相似度，embedding 不可用时降级为字符级 Jaccard 相似度。
        与 find_duplicate_memory 保持一致的降级策略。
        """
        cache_key = f"{min(memory_id_1, memory_id_2)}:{max(memory_id_1, memory_id_2)}"

        if cache_key in self._similarity_cache:
            return self._similarity_cache[cache_key]

        try:
            # 获取记忆内容
            if asyncio.iscoroutinefunction(self.memory_manager.get_memory):
                memory_1 = await self.memory_manager.get_memory(memory_id_1)
                memory_2 = await self.memory_manager.get_memory(memory_id_2)
            else:
                memory_1 = self.memory_manager.get_memory(memory_id_1)
                memory_2 = self.memory_manager.get_memory(memory_id_2)

            if not memory_1 or not memory_2:
                return 0.0

            content_1 = memory_1.get("content", "")
            content_2 = memory_2.get("content", "")

            # 优先向量相似度，embedding 不可用时降级为字符级 Jaccard
            try:
                similarity = await self.check_vector_similarity(content_1, content_2)
            except Exception as e:
                logger.warning(
                    f"向量相似度计算失败，降级为 Jaccard [{type(e).__name__}]: {e}"
                )
                similarity = self._calculate_text_similarity(content_1, content_2)

            # 缓存结果
            self._similarity_cache[cache_key] = similarity

            return similarity

        except Exception as e:
            # 不再吞掉异常返回 0.0，而是记录错误类型并向上传播，避免掩盖真实故障
            logger.error(f"计算相似度失败 [{type(e).__name__}]: {e}", exc_info=True)
            raise

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的Jaccard相似度

        Args:
            text1: 第一个文本
            text2: 第二个文本

        Returns:
            相似度分数 (0.0 - 1.0)
        """
        if not text1 or not text2:
            return 0.0

        # 转换为小写并按字符切分成集合（对中文有效，避免空格 split 失效）
        set1 = set(text1.lower())
        set2 = set(text2.lower())

        if not set1 or not set2:
            return 0.0

        # 计算Jaccard相似度
        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度

        Args:
            vec1: 第一个向量
            vec2: 第二个向量

        Returns:
            余弦相似度分数 (-1.0 - 1.0，语义相似度场景下通常为 0.0 - 1.0)
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    async def check_vector_similarity(self, content1: str, content2: str) -> float:
        """计算两个文本内容的向量余弦相似度

        使用 embedding 模型生成两个内容的向量，计算余弦相似度。
        调用方式参考 MemoryManager._sync_vector_for_memory 中的 get_embedding 调用。

        Args:
            content1: 第一个文本内容
            content2: 第二个文本内容

        Returns:
            余弦相似度分数 (0.0 - 1.0)

        Raises:
            RuntimeError: 当 embedding 模型不可用或生成空向量时抛出，
                          由调用方降级为字符级 Jaccard
        """
        embedding_model = getattr(self.memory_manager, "_embedding_model", None)
        if embedding_model is None:
            raise RuntimeError("embedding 模型不可用")

        if not content1 or not content2:
            return 0.0

        # 生成向量（参考项目中 _sync_vector_for_memory 的调用方式）
        emb1 = await embedding_model.get_embedding(content1)
        emb2 = await embedding_model.get_embedding(content2)

        if not emb1 or not emb2:
            raise RuntimeError("embedding 生成失败，返回空向量")

        return self._cosine_similarity(emb1, emb2)

    async def find_similar_memories(
        self,
        memory_id: int,
        threshold: float = None,
        limit: int = 10,
        workspace_id: str = "default",
        agent_id: str = "default",
    ) -> List[SimilarityRecord]:
        """查找与指定记忆相似的其他记忆

        优先使用向量余弦相似度，embedding 不可用时降级为字符级 Jaccard 相似度。

        Args:
            memory_id: 目标记忆ID
            threshold: 相似度阈值，默认使用引擎阈值
            limit: 返回数量上限
            workspace_id: 工作区ID
            agent_id: Agent ID
        """
        if threshold is None:
            threshold = self.threshold

        similar_memories = []

        try:
            # 获取目标记忆内容
            if asyncio.iscoroutinefunction(self.memory_manager.get_memory):
                target_memory = await self.memory_manager.get_memory(
                    memory_id, agent_id=agent_id
                )
            else:
                target_memory = self.memory_manager.get_memory(memory_id, agent_id=agent_id)

            if not target_memory:
                logger.warning(f"未找到目标记忆: {memory_id}")
                return []

            target_content = target_memory.get("content", "")

            # 获取候选记忆（传递 workspace_id 和 agent_id 以限定范围）
            if asyncio.iscoroutinefunction(self.memory_manager.search_memories):
                all_memories = await self.memory_manager.search_memories(
                    memory_type=None,
                    limit=10000,
                    include_deleted=False,
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                )
            else:
                all_memories = self.memory_manager.search_memories(
                    memory_type=None,
                    limit=10000,
                    include_deleted=False,
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                )

            # 判断 embedding 是否可用（只需检测一次）
            embedding_available = (
                getattr(self.memory_manager, "_embedding_model", None) is not None
            )

            for other_memory in all_memories:
                other_id = other_memory["id"]
                if other_id == memory_id:
                    continue

                other_content = other_memory.get("content", "")

                # 优先向量相似度，embedding 不可用时降级为字符级 Jaccard
                if embedding_available:
                    try:
                        similarity = await self.check_vector_similarity(
                            target_content, other_content
                        )
                    except Exception as e:
                        logger.warning(
                            f"向量相似度计算失败，降级为 Jaccard [{type(e).__name__}]: {e}"
                        )
                        similarity = self._calculate_text_similarity(
                            target_content, other_content
                        )
                        # 后续直接走 Jaccard，避免重复失败
                        embedding_available = False
                else:
                    similarity = self._calculate_text_similarity(
                        target_content, other_content
                    )

                if similarity >= threshold:
                    record = SimilarityRecord(
                        memory_id_1=memory_id,
                        memory_id_2=other_id,
                        similarity_score=similarity,
                        is_duplicate=similarity >= self.threshold,
                    )
                    similar_memories.append(record)

            # 按相似度排序
            similar_memories.sort(key=lambda x: x.similarity_score, reverse=True)

            return similar_memories[:limit]

        except Exception as e:
            logger.error(f"查找相似记忆失败 [{type(e).__name__}]: {e}", exc_info=True)
            return []

    async def find_duplicate_memory(
        self,
        content: str,
        workspace_id: str = "default",
        agent_id: str = "default",
        threshold: float = None,
        limit: int = 100,
    ) -> Optional[Tuple[int, float]]:
        """查找与给定内容重复的已存在记忆（用于写入去重）

        优先使用向量余弦相似度，embedding 不可用时降级为字符级 Jaccard。

        Args:
            content: 待写入的记忆内容
            workspace_id: 工作区ID
            agent_id: Agent ID
            threshold: 相似度阈值，默认使用引擎阈值
            limit: 候选记忆数量上限

        Returns:
            (memory_id, similarity_score) 如果找到重复，否则 None
        """
        if threshold is None:
            threshold = self.threshold

        if not content:
            return None

        try:
            # 获取同 agent 的近期记忆作为候选
            if asyncio.iscoroutinefunction(self.memory_manager.search_memories):
                candidates = await self.memory_manager.search_memories(
                    memory_type=None,
                    limit=limit,
                    include_deleted=False,
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                )
            else:
                candidates = self.memory_manager.search_memories(
                    memory_type=None,
                    limit=limit,
                    include_deleted=False,
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                )

            if not candidates:
                return None

            embedding_available = (
                getattr(self.memory_manager, "_embedding_model", None) is not None
            )

            best_match = None
            best_score = 0.0

            for candidate in candidates:
                candidate_content = candidate.get("content", "")

                if embedding_available:
                    try:
                        similarity = await self.check_vector_similarity(
                            content, candidate_content
                        )
                    except Exception as e:
                        logger.warning(
                            f"向量相似度计算失败，降级为 Jaccard [{type(e).__name__}]: {e}"
                        )
                        similarity = self._calculate_text_similarity(
                            content, candidate_content
                        )
                        embedding_available = False
                else:
                    similarity = self._calculate_text_similarity(
                        content, candidate_content
                    )

                if similarity > best_score:
                    best_score = similarity
                    best_match = candidate

            if best_match and best_score >= threshold:
                logger.info(
                    f"发现重复记忆: existing_id={best_match['id']}, similarity={best_score:.4f}"
                )
                return (best_match["id"], best_score)

            return None

        except Exception as e:
            logger.error(f"查找重复记忆失败 [{type(e).__name__}]: {e}", exc_info=True)
            return None

    async def detect_duplicates_batch(
        self, memory_ids: List[int] = None, threshold: float = None
    ) -> List[DuplicateGroup]:
        """批量检测重复记忆"""
        if threshold is None:
            threshold = self.threshold

        if memory_ids is None:
            # 获取所有记忆
            if asyncio.iscoroutinefunction(self.memory_manager.search_memories):
                all_memories = await self.memory_manager.search_memories(
                    memory_type=None, limit=10000, include_deleted=False
                )
            else:
                all_memories = self.memory_manager.search_memories(
                    memory_type=None, limit=10000, include_deleted=False
                )
            memory_ids = [m["id"] for m in all_memories]

        # 构建相似性图
        similarity_graph: Dict[int, Set[int]] = {mid: set() for mid in memory_ids}

        logger.info(f"开始批量去重检测，记忆数量: {len(memory_ids)}")

        # 计算所有记忆对的相似度
        for i, id_1 in enumerate(memory_ids):
            for id_2 in memory_ids[i + 1 :]:
                similarity = await self.check_similarity(id_1, id_2)

                if similarity >= threshold:
                    similarity_graph[id_1].add(id_2)
                    similarity_graph[id_2].add(id_1)

        # 使用并查集找到连通分量（重复组）
        groups = self._find_connected_components(similarity_graph)

        # 创建 DuplicateGroup 对象
        duplicate_groups = []
        for group_memories in groups:
            if len(group_memories) > 1:  # 只保留有重复的记忆组
                group_id = self._generate_group_id(list(group_memories))

                # 计算相似度矩阵
                similarity_matrix = {}
                for id_1 in group_memories:
                    for id_2 in group_memories:
                        if id_1 < id_2:
                            sim = await self.check_similarity(id_1, id_2)
                            similarity_matrix[f"{id_1}:{id_2}"] = sim

                # 选择代表性记忆（创建时间最早的）
                if asyncio.iscoroutinefunction(self.memory_manager.get_memory):
                    created_times = {}
                    for mid in group_memories:
                        memory = await self.memory_manager.get_memory(mid)
                        created_times[mid] = memory.get("created_at", "") if memory else ""
                    canonical_id = min(group_memories, key=lambda mid: created_times[mid])
                else:
                    def get_created_time(memory_id):
                        memory = self.memory_manager.get_memory(memory_id)
                        if memory is None:
                            return ""
                        return memory.get("created_at", "")

                    canonical_id = min(group_memories, key=get_created_time)

                group = DuplicateGroup(
                    group_id=group_id,
                    memory_ids=list(group_memories),
                    canonical_id=canonical_id,
                    similarity_matrix=similarity_matrix,
                )

                duplicate_groups.append(group)
                self._duplicate_groups[group_id] = group

        logger.info(f"检测到 {len(duplicate_groups)} 个重复组")

        return duplicate_groups

    def _find_connected_components(self, graph: Dict[int, Set[int]]) -> List[Set[int]]:
        """查找连通分量"""
        visited = set()
        components = []

        def dfs(node, component):
            visited.add(node)
            component.add(node)
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, component)

        for node in graph:
            if node not in visited:
                component = set()
                dfs(node, component)
                components.append(component)

        return components

    async def record_search_similarity(
        self, query_memory_id: int, result_memory_id: int, similarity_score: float
    ):
        """记录搜索时发现的相似性"""
        if similarity_score >= self.threshold:
            logger.info(
                f"搜索发现重复记忆",
                extra={
                    "query_memory_id": query_memory_id,
                    "result_memory_id": result_memory_id,
                    "similarity_score": similarity_score,
                },
            )

            # 注意：这里可以扩展为将相似性记录保存到数据库
            # 目前仅记录到日志中

    def get_duplicate_groups(self) -> List[DuplicateGroup]:
        """获取所有去重组"""
        return list(self._duplicate_groups.values())

    def get_duplicate_group_by_memory(self, memory_id: int) -> Optional[DuplicateGroup]:
        """根据记忆ID获取所属的去重组"""
        for group in self._duplicate_groups.values():
            if memory_id in group.memory_ids:
                return group
        return None

    def clear_cache(self):
        """清除相似度缓存"""
        self._similarity_cache.clear()
        logger.info("相似度缓存已清除")
