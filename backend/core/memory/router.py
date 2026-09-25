import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from backend.core.logging_config import get_contextual_logger
from backend.core.memory.decay import (
    RELEVANCE_SOURCE_SEARCH,
    RELEVANCE_SOURCE_UNRESOLVED,
)

logger = get_contextual_logger(__name__)


@dataclass
class RoutingResult:
    memories: List[Dict]
    total_score: float
    source_counts: Dict[str, int]
    applied_weights: Dict[str, float]
    applied_rules: List[str]
    context: Dict = field(default_factory=dict)


@dataclass
class RoutingConfig:
    importance_weight: float = 0.35
    time_weight: float = 0.25
    relevance_weight: float = 0.4
    hard_rules_enabled: bool = True
    scene_awareness_enabled: bool = True
    max_memories: int = 10
    min_score_threshold: float = 0.3
    high_priority_threshold: float = 0.8


class MemoryRouter:
    SCENE_CONFIGS = {
        "task": {
            "description": "任务型对话",
            "relevance_weight": 0.5,
            "importance_weight": 0.30,
            "time_weight": 0.20,
        },
        "chat": {
            "description": "闲聊/情感对话",
            "relevance_weight": 0.35,
            "importance_weight": 0.45,
            "time_weight": 0.20,
        },
        "first_interaction": {
            "description": "首次交互",
            "relevance_weight": 0.40,
            "importance_weight": 0.30,
            "time_weight": 0.30,
        },
        "recall": {
            "description": "记忆召回",
            "relevance_weight": 0.50,
            "importance_weight": 0.25,
            "time_weight": 0.25,
        },
        "learning": {
            "description": "学习/知识获取",
            "relevance_weight": 0.45,
            "importance_weight": 0.35,
            "time_weight": 0.20,
        },
        "problem_solving": {
            "description": "问题解决",
            "relevance_weight": 0.55,
            "importance_weight": 0.25,
            "time_weight": 0.20,
        },
        "creative": {
            "description": "创造性对话",
            "relevance_weight": 0.30,
            "importance_weight": 0.30,
            "time_weight": 0.40,
        },
    }

    def __init__(
        self, memory_manager, vector_store=None, embedding_model=None, config: RoutingConfig = None
    ):
        self.memory_manager = memory_manager
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.config = config or RoutingConfig()

        from backend.core.memory.decay import DecayCalculator

        self.decay_calculator = DecayCalculator()

        from backend.core.memory.hybrid_search import HybridSearch, HybridSearchOptions

        self.hybrid_search = None
        if vector_store and embedding_model:
            self.hybrid_search = HybridSearch(vector_store, memory_manager, embedding_model)

    def set_config(self, config: RoutingConfig):
        self.config = config

    async def route(
        self,
        query: str,
        session_id: str = None,
        scene_type: str = "chat",
        context: Dict = None,
        options: Dict = None,
        agent_id: str = "default",
    ) -> RoutingResult:
        options = options or {}

        applied_rules = []
        applied_weights = self._get_weights(scene_type)
        source_counts = {"permanent": 0, "long_term": 0, "short_term": 0}

        all_memories = []

        try:
            recent_memories = await asyncio.to_thread(
                self._get_recent_memories, session_id, agent_id
            )
            if recent_memories:
                all_memories.extend(recent_memories)
                # 原标签「最近交互记忆优先」与实际行为不符（该规则从未接线），
                # 改为如实描述：最近记忆仅作为候选纳入，不享有相关度豁免
                applied_rules.append("同会话最近记忆纳入候选")

            search_results = await self._search_memories(query, options, agent_id)
            logger.info(f"记忆路由: query='{query}', hybrid_search={self.hybrid_search is not None}, search_results={len(search_results)}")

            # 候选合并：同会话最近记忆在前、搜索结果在后，统一交给共享评分入口；
            # 最近记忆不设任何相关度豁免，相关度一律走共享入口的解析口径
            candidates = list(all_memories) + list(search_results)

            scored_memories = self._score_memories(
                candidates, query, applied_weights, context or {}
            )

            # 顺序固定：先评分 → 再去重 → 后过滤（去重依赖 final_score，过滤前必须完成去重）
            deduped_memories = self._dedupe_memories(scored_memories)
            filtered = self._apply_filters(deduped_memories)
            logger.info(f"记忆路由: scored={len(scored_memories)}, filtered={len(filtered)}")

            final_memories = self._apply_scene_adjustment(filtered, scene_type, applied_weights)

            total_score = sum(m.get("final_score", 0) for m in final_memories)

            for m in final_memories:
                mem_type = m.get("type", "long_term")
                if mem_type in source_counts:
                    source_counts[mem_type] += 1

            return RoutingResult(
                memories=final_memories[: self.config.max_memories],
                total_score=total_score,
                source_counts=source_counts,
                applied_weights=applied_weights,
                applied_rules=applied_rules,
                context={
                    "query": query,
                    "scene_type": scene_type,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"记忆路由失败: {e}")
            return RoutingResult(
                memories=[],
                total_score=0.0,
                source_counts=source_counts,
                applied_weights=applied_weights,
                applied_rules=applied_rules,
                context={"error": str(e)},
            )

    def _get_weights(self, scene_type: str) -> Dict[str, float]:
        if not self.config.scene_awareness_enabled:
            return {
                "importance": self.config.importance_weight,
                "time": self.config.time_weight,
                "relevance": self.config.relevance_weight,
            }

        scene_config = self.SCENE_CONFIGS.get(scene_type, self.SCENE_CONFIGS["chat"])
        return {
            "importance": scene_config["importance_weight"],
            "time": scene_config["time_weight"],
            "relevance": scene_config["relevance_weight"],
        }

    def _get_recent_memories(self, session_id: str, agent_id: str = "default") -> List[Dict]:
        if not session_id:
            return []

        try:
            recent_count = 0
            memories = []
            page = 0
            page_size = 20

            max_pages = 10
            while recent_count < 50 and page < max_pages:
                results = self.memory_manager.search_memories(
                    query=None,
                    memory_type=None,
                    tags=[session_id] if session_id else None,
                    limit=page_size,
                    offset=page * page_size,
                    agent_id=agent_id,
                )

                if not results:
                    break

                # 检索阶段已用 tags=[session_id] 精确过滤，直接使用返回结果；
                # 顶层 session_id 键不存在（在 metadata 里），原过滤恒为 False
                # 会导致检索结果全部被丢弃，"同会话最近记忆纳入候选"规则永久失效
                memories.extend(results)
                recent_count += len(results)

                page += 1

            return memories[:30]

        except Exception as e:
            logger.error(f"获取最近记忆失败: {e}")
        return []

    async def _search_memories(self, query: str, options: Dict, agent_id: str = "default") -> List[Dict]:
        try:
            limit = options.get("limit", 50)

            if self.hybrid_search and query:
                from backend.core.memory.hybrid_search import HybridSearchOptions

                search_options = HybridSearchOptions(
                    query=query,
                    limit=limit,
                    memory_type=options.get("memory_type"),
                    tags=options.get("tags"),
                    vector_weight=0.6,
                    keyword_weight=0.4,
                    min_score=0.2,
                    agent_id=agent_id,
                )
                results = await self.hybrid_search.search(search_options)

                memories = []
                for r in results:
                    memory = {
                        "id": r.memory_id,
                        "content": r.content,
                        "score": r.score,
                        "source": r.source,
                        "metadata": r.metadata or {},
                    }
                    memories.append(memory)

                return memories

            return await asyncio.to_thread(
                self.memory_manager.search_memories,
                query=query,
                memory_type=options.get("memory_type"),
                tags=options.get("tags"),
                limit=limit,
                agent_id=agent_id,
            )

        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            return []

    def _score_memories(
        self, memories: List[Dict], query: str, weights: Dict[str, float], context: Dict
    ) -> List[Dict]:
        """对候选记忆打分。

        统一走 ``DecayCalculator.calculate_final_score``（相关度门控公式，唯一打分入口），
        结果写入 ``memory["final_score"]`` / ``memory["component_scores"]``。
        单条记忆评分异常时 fail-closed（``final_score = 0.0``），该记忆仍保留在返回
        列表中，由后续 ``_apply_filters`` 按阈值淘汰，等价于不注入。
        """
        scored = []

        for memory in memories:
            try:
                # 共享入口：权重以 (w_importance, w_time, w_relevance) 三元组传入
                final_score, component_scores = self.decay_calculator.calculate_final_score(
                    memory,
                    weights=(
                        weights["importance"],
                        weights["time"],
                        weights["relevance"],
                    ),
                    query=query,
                )
                memory["final_score"] = final_score
                memory["component_scores"] = component_scores

                scored.append(memory)

            except Exception as e:
                logger.warning(f"记忆评分失败: {e}")
                # fail-closed：禁止任何兜底分数，置 0 后由 _apply_filters 淘汰
                memory["final_score"] = 0.0
                # 前两维尽力取值（异常状态下可能同样取不到或非数值），取不到即填 0.0
                try:
                    importance_fallback = float(
                        self.decay_calculator.calculate_importance_score(memory)
                    )
                except Exception:
                    importance_fallback = 0.0
                try:
                    time_fallback = float(self.decay_calculator.calculate_time_score(memory))
                except Exception:
                    time_fallback = 0.0
                memory["component_scores"] = {
                    "importance": importance_fallback,
                    "time": time_fallback,
                    "relevance": 0.0,
                    "relevance_source": RELEVANCE_SOURCE_UNRESOLVED,
                }

                scored.append(memory)

        return scored

    def _dedupe_memories(self, memories: List[Dict]) -> List[Dict]:
        """按 id 去重（缺 id 时退回用 content 作键），保持首次出现顺序。

        同一键保留 ``final_score`` 较高者；``final_score`` 相等时优先保留
        ``component_scores.relevance_source == "search_score"`` 的那条。
        必须在评分之后、过滤之前调用（依赖 final_score 判定保留哪一条）。
        """
        best: Dict = {}
        positions: Dict = {}

        for memory in memories:
            key = memory.get("id")
            if key is None:
                # 缺 id 时退回 content 作去重键（元组前缀避免与真实 id 撞键）
                key = ("__content__", memory.get("content"))

            if key not in best:
                # 记录首次出现位置，保证输出稳定
                positions[key] = len(positions)
                best[key] = memory
                continue

            incumbent = best[key]
            candidate_score = memory.get("final_score", 0)
            incumbent_score = incumbent.get("final_score", 0)
            if candidate_score > incumbent_score:
                best[key] = memory
                continue
            if candidate_score == incumbent_score:
                candidate_source = (memory.get("component_scores") or {}).get(
                    "relevance_source"
                )
                incumbent_source = (incumbent.get("component_scores") or {}).get(
                    "relevance_source"
                )
                # 同分时优先保留 search_score 来源，避免来源归属失真
                if (
                    candidate_source == RELEVANCE_SOURCE_SEARCH
                    and incumbent_source != RELEVANCE_SOURCE_SEARCH
                ):
                    best[key] = memory

        ordered_keys = sorted(best.keys(), key=lambda k: positions[k])
        return [best[k] for k in ordered_keys]

    def _apply_filters(self, memories: List[Dict]) -> List[Dict]:
        filtered = []

        for memory in memories:
            score = memory.get("final_score", 0)

            # permanent 不再无条件放行：与普通记忆同走分数阈值判定
            if score >= self.config.high_priority_threshold:
                filtered.append(memory)
            elif score >= self.config.min_score_threshold:
                filtered.append(memory)
            elif self._is_explicitly_mentioned(memory):
                filtered.append(memory)

        return filtered

    def _is_explicitly_mentioned(self, memory: Dict) -> bool:
        return memory.get("explicitly_mentioned", False)

    def _apply_scene_adjustment(
        self, memories: List[Dict], scene_type: str, weights: Dict[str, float]
    ) -> List[Dict]:
        if scene_type == "task":
            memories.sort(
                key=lambda m: m.get("component_scores", {}).get("relevance", 0), reverse=True
            )
        elif scene_type == "first_interaction":
            for m in memories:
                m["final_score"] = min(1.0, m.get("final_score", 0) * 1.2)

        return memories

    def get_routing_status(self) -> Dict:
        return {
            "enabled": True,
            "config": {
                "importance_weight": self.config.importance_weight,
                "time_weight": self.config.time_weight,
                "relevance_weight": self.config.relevance_weight,
                "hard_rules_enabled": self.config.hard_rules_enabled,
                "scene_awareness_enabled": self.config.scene_awareness_enabled,
                "max_memories": self.config.max_memories,
                "min_score_threshold": self.config.min_score_threshold,
            },
            "scene_configs": {
                k: {
                    "description": v["description"],
                    "weights": {
                        "importance": v["importance_weight"],
                        "time": v["time_weight"],
                        "relevance": v["relevance_weight"],
                    },
                }
                for k, v in self.SCENE_CONFIGS.items()
            },
        }
