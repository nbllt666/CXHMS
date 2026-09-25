"""记忆召回零相关度误召回 —— 复现/回归脚本

调试会话: memory-recall-zero-relevance（原插桩已按 TRAE-debugger 协议清理，
本脚本已同步去除对 `_dbg_report` 的依赖，可独立运行）
运行: python tests/manual/repro_memory_recall_zero_relevance.py   (cwd = 仓库根)

预期：修复前场景 A 的无关记忆 `final_score ≈ 0.825` 且被保留；
      修复后应为 `final_score = 0.0` 且被淘汰（场景 B 同理，异常记忆由 0.3 降为 0.0）。

本脚本仅作调试脚手架（可用 print 输出摘要），不改动业务逻辑。
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.memory.hybrid_search import HybridSearch  # noqa: E402
from backend.core.memory.router import MemoryRouter  # noqa: E402

NOW = datetime.now().isoformat()
QUERY_UNRELATED = "量子纠缠退相干实验数据"


class FakeMemoryManager:
    """最小 fake：query=None 走“最近记忆”通道，否则走“搜索”通道。"""

    def __init__(self, recent, search):
        self._recent = recent
        self._search = search
        self.calls = []

    def search_memories(
        self,
        query=None,
        memory_type=None,
        tags=None,
        limit=10,
        offset=0,
        agent_id="default",
        **kwargs,
    ):
        self.calls.append(
            {"query": query, "tags": tags, "limit": limit, "offset": offset}
        )
        if query is None:
            # 分页语义：仅首页返回，避免 _get_recent_memories 分页循环重复计数
            return [dict(m) for m in self._recent] if offset == 0 else []
        return [dict(m) for m in self._search]


def build_router(search=None, recent=None):
    fake = FakeMemoryManager(recent or [], search or [])
    return MemoryRouter(memory_manager=fake, vector_store=None, embedding_model=None), fake


def scenario_a(router):
    """假设 1（可加性）+ 假设 2（伪造 0.5）：无关 query、无 score 字段。"""
    mem = {
        "id": 1,
        "content": "今天天气很好",
        "importance_score": 1.0,
        "created_at": NOW,
        "permanent": False,
    }
    weights = router._get_weights("chat")
    scored = router._score_memories([mem], QUERY_UNRELATED, weights, {})
    kept = router._apply_filters(scored)

    print("\n=== 场景 A：无关 query + 无 score 字段（H1 / H2）===")
    print(f"query          = {QUERY_UNRELATED}")
    print(f"weights(chat)  = {weights}")
    print(f"final_score    = {mem.get('final_score')}")
    print(f"component_scores = {mem.get('component_scores')}")
    print(f"has_score_key  = {'score' in mem}")
    print(f"relevance 实际取值 = {mem.get('component_scores', {}).get('relevance')}")
    print(f"通过 _apply_filters = {mem in kept}  (kept={len(kept)})")
    return {
        "final_score": mem.get("final_score"),
        "relevance": mem.get("component_scores", {}).get("relevance"),
        "kept": mem in kept,
    }


def scenario_b(router):
    """假设 3（异常兜底 0.3）：构造评分抛异常的记忆。"""
    print("\n=== 场景 B：评分异常兜底（H3）===")

    # B1: importance_score 为无法参与运算的类型 -> 评分内部抛异常
    b1 = {
        "id": 2,
        "content": "评分异常记忆-非数值importance",
        "importance_score": "abc",
        "created_at": NOW,
        "permanent": False,
    }
    weights = router._get_weights("chat")
    scored1 = router._score_memories([b1], QUERY_UNRELATED, weights, {})
    kept1 = router._apply_filters(scored1)
    print(f"B1 importance_score='abc' -> final_score = {b1.get('final_score')}, kept = {b1 in kept1}")

    # B2: weights 缺 relevance 键 -> KeyError -> 同一 except 分支
    b2 = {
        "id": 3,
        "content": "评分异常记忆-缺权重组",
        "importance_score": 1.0,
        "created_at": NOW,
        "permanent": False,
    }
    bad_weights = {"importance": 0.45, "time": 0.20}
    scored2 = router._score_memories([b2], QUERY_UNRELATED, bad_weights, {})
    kept2 = router._apply_filters(scored2)
    print(f"B2 weights 缺 relevance -> final_score = {b2.get('final_score')}, kept = {b2 in kept2}")
    print(f"min_score_threshold = {router.config.min_score_threshold}")

    return {
        "b1_final_score": b1.get("final_score"),
        "b1_kept": b1 in kept1,
        "b2_final_score": b2.get("final_score"),
        "b2_kept": b2 in kept2,
    }


def scenario_c():
    """假设 5（all_memories 死代码）：recent 通道记忆是否进入评分。"""
    recent = [
        {
            "id": 100,
            "content": "我记得你喜欢喝咖啡",
            "importance_score": 1.0,
            "created_at": NOW,
            "tags": ["s1"],
        },
        {
            "id": 101,
            "content": "上次我们聊到了旅行计划",
            "importance_score": 0.9,
            "created_at": NOW,
            "tags": ["s1"],
        },
    ]
    search = [
        {
            "id": 200,
            "content": "用户是一名后端工程师",
            "importance_score": 1.0,
            "created_at": NOW,
            "score": 0.85,
        },
        {
            "id": 201,
            "content": "用户喜欢读科幻小说",
            "importance_score": 0.9,
            "created_at": NOW,
            "score": 0.8,
        },
    ]
    router, fake = build_router(search=search, recent=recent)
    result = asyncio.run(
        router.route(query=QUERY_UNRELATED, session_id="s1", scene_type="chat")
    )

    print("\n=== 场景 C：route() 全链路（H5）===")
    print(f"manager calls  = {fake.calls}")
    print(f"applied_rules  = {result.applied_rules}")
    print(f"返回记忆 ids    = {[m.get('id') for m in result.memories]}")
    print(f"返回 final_scores = {[m.get('final_score') for m in result.memories]}")

    recent_ids = {100, 101}
    returned_ids = {m.get("id") for m in result.memories}
    print(f"recent 通道 id 是否出现在结果中 = {sorted(recent_ids & returned_ids)}")
    return {
        "applied_rules": result.applied_rules,
        "returned_ids": sorted(returned_ids),
        "recent_ids_returned": sorted(recent_ids & returned_ids),
    }


def scenario_d():
    """假设 4（keyword 未命中返 0.1）：直接调用未绑定方法。"""
    miss = HybridSearch._calculate_keyword_score(None, "完全无关内容", "量子纠缠")
    hit = HybridSearch._calculate_keyword_score(None, "量子纠缠退相干实验数据记录", "量子纠缠")
    print("\n=== 场景 D：关键词相关度（H4）===")
    print(f"未命中返回值 = {miss}")
    print(f"命中返回值   = {hit}")
    return {"miss": miss, "hit": hit}


def main():
    router_for_ab, _ = build_router()
    print(f"[env] python={sys.version.split()[0]} repo_root={REPO_ROOT}")
    print(f"[env] weights_chat={router_for_ab._get_weights('chat')}")
    print(
        f"[env] min_score_threshold={router_for_ab.config.min_score_threshold} "
        f"high_priority_threshold={router_for_ab.config.high_priority_threshold}"
    )

    a = scenario_a(router_for_ab)
    b = scenario_b(router_for_ab)
    c = scenario_c()
    d = scenario_d()

    print("\n=== 汇总 ===")
    print(f"A: final_score={a['final_score']}, relevance={a['relevance']}, kept={a['kept']}")
    print(f"B: b1={b['b1_final_score']}/{b['b1_kept']}, b2={b['b2_final_score']}/{b['b2_kept']}")
    print(f"C: applied_rules={c['applied_rules']}, recent_ids_returned={c['recent_ids_returned']}")
    print(f"D: miss={d['miss']}, hit={d['hit']}")


if __name__ == "__main__":
    main()
