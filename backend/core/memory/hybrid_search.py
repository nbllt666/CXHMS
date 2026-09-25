import asyncio
import inspect
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


@dataclass
class SearchResult:
    memory_id: int
    content: str
    score: float
    source: str
    metadata: Dict = None


@dataclass
class HybridSearchOptions:
    query: str
    memory_type: str = None
    tags: List[str] = None
    limit: int = 10
    vector_weight: float = 0.6
    keyword_weight: float = 0.4
    min_score: float = 0.3
    use_vector: bool = True
    use_keyword: bool = True
    workspace_id: str = None
    agent_id: str = "default"


# 虚字集合（用于剔除含虚字的 2 字对；这不是分词，只是单字过滤）。
# 2 字滑窗产生的假组合若含虚字（如「什么」「么咖」），噪声大且几乎不携带语义，故直接剔除。
_FUNCTION_CHARS = set(
    "我你他她它们的地得了吗呢啊吧是在有和与就都也很太不没要想能会可以个这那么什怎为还要把被给对从到向"
)


def extract_key_terms(query: str, max_terms: int = 8) -> List[str]:
    """提取 query 的「2 字滑窗」关键片段（不做中文分词、不依赖词典）。

    中文实词以 2 字为主（咖啡 / 喜欢 / 偏好），相邻 2 字组合即可覆盖真词；
    含虚字的 2 字对（如「什么」「么咖」）予以剔除以降低噪声。

    规则：
        - ``query`` 为 ``None`` 或长度 < 2 → 返回 ``[]``；
        - 对 ``query`` 做相邻 2 字滑窗 ``query[i:i+2]``；
        - 若该 2 字对任一字符在 ``_FUNCTION_CHARS`` 中 → 丢弃；
        - 去重且保持出现顺序；截断到 ``max_terms``。

    Args:
        query: 待提取的查询字符串
        max_terms: 返回词元数量上限（默认 8，用于控制下游 SQL OR 数量）

    Returns:
        保序去重后的 2 字词元列表
    """
    if not query or len(query) < 2:
        return []

    terms: List[str] = []
    seen = set()
    for i in range(len(query) - 1):
        pair = query[i : i + 2]
        # 含任意虚字则丢弃（如「什么」「么咖」「我喜」）
        if pair[0] in _FUNCTION_CHARS or pair[1] in _FUNCTION_CHARS:
            continue
        if pair in seen:
            continue
        seen.add(pair)
        terms.append(pair)
        if len(terms) >= max_terms:
            break
    return terms


def calculate_keyword_relevance(content: str, query: str) -> float:
    """关键词实时相关度（模块级单一真相源，供多条路径复用）。

    ⚠️ 本函数为「相关度门控」的输入源：``0.0`` 表示完全无关，不得回退为任何非零默认值。
    三分支语义：

        - 分支 A（保持原语义）：``query`` 整句命中 ``content``
          → ``min(1.0 - position/length + 0.1, 1.0)``；
        - 分支 B（新增，2 字滑窗部分命中）：整句未命中，但 ``extract_key_terms(query)``
          中至少 1 个词元出现在 ``content`` 里
          → ``0.5 + 0.5 * (命中词元数 / 词元总数)``，上限 ``1.0``；
        - 分支 C（不变量）：整句未命中且词元全部未命中 → **仍返回 ``0.0``**。

    ``content`` 或 ``query`` 为空 / ``None`` 时返回 ``0.0``。

    Args:
        content: 待评估的记忆内容
        query: 当前查询字符串

    Returns:
        相关度分数，值域 ``[0, 1]``
    """
    # 先判空，避免 None.lower() 抛异常
    if not content or not query:
        return 0.0

    query_lower = query.lower()
    content_lower = content.lower()

    # 分支 A：整句命中，保持既有位置衰减语义
    if query_lower in content_lower:
        position = content_lower.find(query_lower)
        length = len(content_lower)
        # 位置越靠前相关度越高；length 为 0 时退化为固定基准分（防御性分支）
        base_score = 1.0 - (position / length) if length > 0 else 0.5
        return min(base_score + 0.1, 1.0)

    # 分支 B：整句未命中，退化为 2 字滑窗词元的部分命中（保底 0.5 使单个实词即可越过阈值）
    key_terms = extract_key_terms(query)
    if key_terms:
        hit_count = sum(1 for term in key_terms if term.lower() in content_lower)
        if hit_count > 0:
            return min(0.5 + 0.5 * (hit_count / len(key_terms)), 1.0)

    # 分支 C：完全无重叠 → 0.0（相关度硬门控不变量，严禁放宽）
    return 0.0


class HybridSearch:
    def __init__(self, vector_store, sqlite_manager, embedding_model=None):
        self.vector_store = vector_store
        self.sqlite_manager = sqlite_manager
        self.embedding_model = embedding_model

    async def search(self, options: HybridSearchOptions) -> List[SearchResult]:
        results: List[SearchResult] = []

        vector_results = []
        keyword_results = []

        if options.use_vector and options.query and self.vector_store and self.embedding_model:
            vector_results = await self._vector_search(options)

        if options.use_keyword and options.query:
            keyword_results = await self._keyword_search(options)

        merged = self._merge_results(
            vector_results, keyword_results, options.vector_weight, options.keyword_weight
        )

        filtered = [r for r in merged if r.score >= options.min_score]

        filtered.sort(key=lambda x: x.score, reverse=True)

        return filtered[: options.limit]

    async def _vector_search(self, options: HybridSearchOptions) -> List[SearchResult]:
        try:
            # Check vector store availability BEFORE getting embedding (which can be slow)
            is_available_fn = getattr(self.vector_store, "is_available", None)
            if is_available_fn is not None:
                available = await is_available_fn() if asyncio.iscoroutinefunction(is_available_fn) else is_available_fn()
                if not available:
                    logger.warning("向量存储不可用，跳过向量搜索（含 embedding 请求）")
                    return []

            embedding = await self.embedding_model.get_embedding(options.query)

            # 构建搜索参数，条件性传递 agent_id 以支持 agent 隔离
            # 仅当向量存储的 search_similar 支持 agent_id 参数时才传递，避免破坏不支持的实现（如 Chroma）
            search_kwargs = {
                "query_embedding": embedding,
                "limit": options.limit * 2,
                "memory_type": options.memory_type,
            }
            sig = inspect.signature(self.vector_store.search_similar)
            if "agent_id" in sig.parameters:
                search_kwargs["agent_id"] = options.agent_id

            vector_results = await self.vector_store.search_similar(**search_kwargs)

            return [
                SearchResult(
                    memory_id=r["memory_id"],
                    content=r["content"],
                    score=r["score"],
                    source="vector",
                    metadata=r.get("metadata"),
                )
                for r in vector_results
            ]
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []

    async def _keyword_search(self, options: HybridSearchOptions) -> List[SearchResult]:
        try:
            # B5: 必须透传 workspace_id/agent_id，否则关键词搜索会跨 agent 泄漏
            keyword_results = self.sqlite_manager.search_memories(
                query=options.query,
                memory_type=options.memory_type,
                tags=options.tags,
                limit=options.limit * 2,
                workspace_id=options.workspace_id or "default",
                agent_id=options.agent_id,
            )

            return [
                SearchResult(
                    memory_id=r["id"],
                    content=r["content"],
                    score=self._calculate_keyword_score(r["content"], options.query),
                    source="keyword",
                    metadata=r,
                )
                for r in keyword_results
            ]
        except Exception as e:
            logger.error(f"关键词搜索失败: {e}")
            return []

    def _calculate_keyword_score(self, content: str, query: str) -> float:
        """委托模块级 calculate_keyword_relevance（保留方法以兼容既有调用方与外部脚本）"""
        return calculate_keyword_relevance(content, query)

    def _merge_results(
        self,
        vector_results: List[SearchResult],
        keyword_results: List[SearchResult],
        vector_weight: float,
        keyword_weight: float,
    ) -> List[SearchResult]:
        merged_dict: Dict[int, SearchResult] = {}

        for r in vector_results:
            if r.memory_id in merged_dict:
                existing = merged_dict[r.memory_id]
                new_score = r.score * vector_weight
                if new_score > existing.score:
                    existing.score = new_score
                    existing.content = r.content
            else:
                merged_dict[r.memory_id] = SearchResult(
                    memory_id=r.memory_id,
                    content=r.content,
                    score=r.score * vector_weight,
                    source="vector",
                    metadata=r.metadata,
                )

        for r in keyword_results:
            if r.memory_id in merged_dict:
                existing = merged_dict[r.memory_id]
                combined_score = existing.score * (1 - keyword_weight) + r.score * keyword_weight
                existing.score = combined_score
                existing.source = "hybrid"
                if r.metadata:
                    existing.metadata = r.metadata
            else:
                merged_dict[r.memory_id] = SearchResult(
                    memory_id=r.memory_id,
                    content=r.content,
                    score=r.score * keyword_weight,
                    source="keyword",
                    metadata=r.metadata,
                )

        return list(merged_dict.values())

    async def semantic_search(
        self, query: str, memory_type: str = None, limit: int = 10, agent_id: str = "default"
    ) -> List[Dict]:
        options = HybridSearchOptions(
            query=query,
            memory_type=memory_type,
            limit=limit,
            use_vector=True,
            use_keyword=False,
            agent_id=agent_id,
        )

        results = await self.search(options)

        return [
            {
                "memory_id": r.memory_id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
            }
            for r in results
        ]

    async def keyword_search(
        self, query: str, memory_type: str = None, tags: List[str] = None, limit: int = 10
    ) -> List[Dict]:
        options = HybridSearchOptions(
            query=query,
            memory_type=memory_type,
            tags=tags,
            limit=limit,
            use_vector=False,
            use_keyword=True,
        )

        results = await self.search(options)

        return [
            {
                "memory_id": r.memory_id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
            }
            for r in results
        ]
