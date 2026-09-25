"""记忆召回「相关度门控」修复单元测试。

覆盖 spec ``fix-memory-recall-relevance-gate``（v4）冻结口径：
    - 相关度硬门控：``relevance = 0`` → ``final_score`` 严格为 ``0.0``，
      不受 importance / time / permanent 抬升
    - ``permanent=True`` 且 ``relevance > 0`` 时 ``+0.15`` 生效并封顶 1.0
    - 高相关记忆仍可召回（越过 ``min_score_threshold``）
    - ``w_i + w_t == 0`` 退化配置下 ``inner = 0.0``，不抛异常
    - ``resolve_relevance`` 来源枚举（``search_score`` / ``keyword_realtime`` /
      ``no_query`` / ``unresolved``）
    - ``_score_memories`` 异常 fail-closed（``final_score = 0.0`` +
      ``relevance_source = "unresolved"``），并被 ``_apply_filters`` 淘汰
    - ``calculate_keyword_relevance`` 未命中返 ``0.0``、命中在开头返 ``1.0``、
      空值返 ``0.0``
    - ``_apply_filters``：permanent 不再无条件放行；``explicitly_mentioned`` 保留
    - ``_dedupe_memories``：按 ``id``（缺 id 按 ``content``）去重，
      保留 ``final_score`` 较高者，同分优先 ``search_score`` 来源，保持首现顺序
    - ``route()`` 接线：最近记忆并入候选无豁免、``applied_rules`` 标签正确、
      同 ``id`` 只出现一次

设计原则：
    - 只调用生产代码既有接口，不修改生产逻辑、不放宽断言
    - 评分类用例直接实例化 ``DecayCalculator``；router 类用例用
      ``memory_manager=None`` 的最小 ``MemoryRouter``（这些方法不触碰 manager）
    - ``route()`` 用例用最小 fake memory_manager（``search_memories`` 按
      ``tags`` 分流最近通道 / 搜索通道），不依赖真实 SQLite 与向量库
"""

import asyncio
from datetime import datetime

import pytest

from backend.core.memory.decay import (
    DecayCalculator,
    RELEVANCE_SOURCE_KEYWORD,
    RELEVANCE_SOURCE_NO_QUERY,
    RELEVANCE_SOURCE_SEARCH,
    RELEVANCE_SOURCE_UNRESOLVED,
)
from backend.core.memory.hybrid_search import (
    HybridSearch,
    calculate_keyword_relevance,
)
from backend.core.memory.router import MemoryRouter, RoutingConfig

pytestmark = pytest.mark.unit

# chat 场景权重（与 MemoryRouter.SCENE_CONFIGS["chat"] 一致）
CHAT_WEIGHTS = {"importance": 0.45, "time": 0.20, "relevance": 0.35}

NOW = datetime.now().isoformat()


# --------------------------------------------------------------------------- #
# 夹具与工具
# --------------------------------------------------------------------------- #


def _make_router(**config_kwargs) -> MemoryRouter:
    """构造最小 MemoryRouter（memory_manager=None；被测方法不触碰 manager）。"""
    return MemoryRouter(memory_manager=None, config=RoutingConfig(**config_kwargs))


class _FakeMemoryManager:
    """最小 fake memory_manager：按 ``tags`` 分流最近通道 / 搜索通道。

    - ``_get_recent_memories`` 以 ``query=None, tags=[session_id]`` 调用 → 返回 recent
    - ``_search_memories`` 回落路径以 ``query=<query>, tags=None`` 调用 → 返回 search
    """

    def __init__(self, recent, search):
        self._recent = recent
        self._search = search

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
        if tags:
            # 分页语义：仅首页返回，避免 _get_recent_memories 分页循环重复计数
            return [dict(m) for m in self._recent] if offset == 0 else []
        return [dict(m) for m in self._search]


# --------------------------------------------------------------------------- #
# 1. 相关度硬门控：relevance = 0 → final_score 严格 0.0
# --------------------------------------------------------------------------- #


def test_zero_relevance_forces_zero_final_score():
    """relevance=0 时 final_score 严格为 0.0（permanent / importance / time 均不得抬升）。"""
    calc = DecayCalculator()

    # 无关 query + 无 score + importance=1.0 + permanent=True（时间分数 = 1.0）
    memory = {
        "id": 1,
        "content": "今天天气很好",
        "importance_score": 1.0,
        "created_at": NOW,
        "permanent": True,
    }
    final, comp = calc.calculate_final_score(
        memory, weights=(0.45, 0.20, 0.35), query="量子纠缠退相干实验数据"
    )

    assert comp["relevance"] == 0.0
    assert comp["relevance_source"] == RELEVANCE_SOURCE_KEYWORD
    assert comp["importance"] == 1.0
    assert comp["time"] == pytest.approx(1.0)
    assert final == 0.0, "相关度为零时 final_score 必须严格为 0.0（硬门控）"

    # 非 permanent、时间分数接近 1.0 的极端组合同样不得抬升
    memory_plain = {
        "id": 2,
        "content": "今天天气很好",
        "importance_score": 1.0,
        "created_at": NOW,
        "permanent": False,
    }
    final_plain, comp_plain = calc.calculate_final_score(
        memory_plain, weights=(0.45, 0.20, 0.35), query="量子纠缠退相干实验数据"
    )
    assert comp_plain["time"] > 0.9
    assert final_plain == 0.0


# --------------------------------------------------------------------------- #
# 2. permanent 加成：仅 relevance > 0 生效且封顶 1.0
# --------------------------------------------------------------------------- #


def test_permanent_boost_only_when_relevant_and_capped():
    """permanent 且 relevance>0 时 +0.15 生效；最终分数不超过 1.0。"""
    calc = DecayCalculator()

    memory = {
        "id": 1,
        "content": "关于苹果的记忆",
        "importance_score": 1.0,
        "created_at": NOW,
        "score": 0.5,
        "permanent": True,
    }
    final, comp = calc.calculate_final_score(memory, weights=(0.45, 0.20, 0.35), query="苹果")

    assert comp["relevance"] == 0.5
    assert comp["relevance_source"] == RELEVANCE_SOURCE_SEARCH

    # 用返回值复算「未加成基分」，避免依赖 time 维度的绝对取值
    inner = (comp["importance"] * 0.45 + comp["time"] * 0.20) / (0.45 + 0.20)
    base = comp["relevance"] * ((1 - 0.35) * inner + 0.35)
    assert final == pytest.approx(min(base + 0.15, 1.0))
    assert final <= 1.0

    # 封顶：满相关度 + 满内层 → 加成后仍为 1.0
    full = {
        "id": 2,
        "content": "关于苹果的记忆",
        "importance_score": 1.0,
        "created_at": NOW,
        "score": 1.0,
        "permanent": True,
    }
    final_full, _ = calc.calculate_final_score(full, weights=(0.45, 0.20, 0.35), query="苹果")
    assert final_full == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 3. 高相关记忆仍可召回
# --------------------------------------------------------------------------- #


def test_high_relevance_memory_is_recalled():
    """高相关记忆（score=0.8、importance/time 正常）final_score > 0.3 且被保留。"""
    router = _make_router()
    memory = {
        "id": 3,
        "content": "关于苹果的记忆",
        "score": 0.8,
        "importance_score": 0.6,
        "created_at": NOW,
    }

    scored = router._score_memories([memory], "苹果", CHAT_WEIGHTS, {})
    assert memory["final_score"] > 0.3
    assert memory["component_scores"]["relevance_source"] == RELEVANCE_SOURCE_SEARCH

    kept = router._apply_filters(scored)
    assert memory in kept, "高相关记忆应被正常召回"


# --------------------------------------------------------------------------- #
# 4. w_i + w_t == 0 退化配置
# --------------------------------------------------------------------------- #


def test_zero_importance_time_weight_sum_does_not_raise():
    """weights=(0, 0, 0.4) 时内层归零，不抛异常（除零保护）。"""
    calc = DecayCalculator()

    # relevance = 0 → final_score == 0.0（任务判据）
    zero_memory = {
        "id": 1,
        "content": "无关内容",
        "importance_score": 1.0,
        "created_at": NOW,
    }
    final_zero, comp_zero = calc.calculate_final_score(
        zero_memory, weights=(0, 0, 0.4), query="苹果"
    )
    assert final_zero == 0.0
    assert comp_zero["relevance_source"] == RELEVANCE_SOURCE_KEYWORD

    # relevance = 1（no_query）→ inner 归零后 final == relevance × w_r == 0.4
    no_query_memory = {
        "id": 2,
        "content": "任意内容",
        "importance_score": 1.0,
        "created_at": NOW,
    }
    final_nq, comp_nq = calc.calculate_final_score(
        no_query_memory, weights=(0, 0, 0.4), query=None
    )
    assert comp_nq["relevance"] == 1.0
    assert comp_nq["relevance_source"] == RELEVANCE_SOURCE_NO_QUERY
    assert final_nq == pytest.approx(0.4), "inner 归零后仅剩残差分量 w_r"


# --------------------------------------------------------------------------- #
# 5. resolve_relevance 来源枚举
# --------------------------------------------------------------------------- #


def test_resolve_relevance_source_enum_and_precedence():
    """resolve_relevance 四枚举来源各自命中条件正确、取值与来源自洽。"""
    calc = DecayCalculator()

    # 枚举常量互异
    sources = {
        RELEVANCE_SOURCE_SEARCH,
        RELEVANCE_SOURCE_KEYWORD,
        RELEVANCE_SOURCE_NO_QUERY,
        RELEVANCE_SOURCE_UNRESOLVED,
    }
    assert len(sources) == 4

    # 1) search_score 优先，且夹取到 [0, 1]
    rel, src = calc.resolve_relevance({"content": "苹果", "score": 0.7}, "苹果")
    assert (rel, src) == (0.7, RELEVANCE_SOURCE_SEARCH)
    rel, src = calc.resolve_relevance({"content": "苹果", "score": 1.5}, "苹果")
    assert (rel, src) == (1.0, RELEVANCE_SOURCE_SEARCH)
    rel, src = calc.resolve_relevance({"content": "苹果", "score": -0.5}, "苹果")
    assert (rel, src) == (0.0, RELEVANCE_SOURCE_SEARCH)

    # 2) keyword_realtime：命中 > 0，未命中 = 0
    rel, src = calc.resolve_relevance({"content": "苹果很好吃"}, "苹果")
    assert src == RELEVANCE_SOURCE_KEYWORD and rel > 0
    rel, src = calc.resolve_relevance({"content": "今天天气很好"}, "苹果")
    assert (rel, src) == (0.0, RELEVANCE_SOURCE_KEYWORD)

    # 3) no_query：query 为 None / 空串 → 1.0
    rel, src = calc.resolve_relevance({"content": "任意"}, None)
    assert (rel, src) == (1.0, RELEVANCE_SOURCE_NO_QUERY)
    rel, src = calc.resolve_relevance({"content": "任意"}, "")
    assert (rel, src) == (1.0, RELEVANCE_SOURCE_NO_QUERY)

    # 4) unresolved 不由 resolve_relevance 产生（由 router 异常分支赋值）


# --------------------------------------------------------------------------- #
# 6. 评分异常 fail-closed
# --------------------------------------------------------------------------- #


def test_score_exception_is_fail_closed_and_filtered():
    """单条记忆评分抛异常 → final_score=0.0 + unresolved，且被 _apply_filters 淘汰。"""
    router = _make_router()

    # 形态一：importance_score 为不可运算对象 → 乘法 / 比较抛 TypeError
    bad_type = {
        "id": 9,
        "content": "评分异常记忆-非数值importance",
        "importance_score": object(),
        "created_at": NOW,
        "permanent": False,
    }
    scored = router._score_memories([bad_type], "苹果", CHAT_WEIGHTS, {})
    assert bad_type["final_score"] == 0.0
    assert bad_type["component_scores"]["relevance"] == 0.0
    assert bad_type["component_scores"]["relevance_source"] == RELEVANCE_SOURCE_UNRESOLVED
    assert bad_type not in router._apply_filters(scored)

    # 形态二：weights 缺 relevance 键 → KeyError（同一 except 分支）
    missing_key = {
        "id": 10,
        "content": "评分异常记忆-缺权重组",
        "importance_score": 1.0,
        "created_at": NOW,
        "permanent": False,
    }
    scored2 = router._score_memories(
        [missing_key], "苹果", {"importance": 0.45, "time": 0.20}, {}
    )
    assert missing_key["final_score"] == 0.0
    assert missing_key["component_scores"]["relevance_source"] == RELEVANCE_SOURCE_UNRESOLVED
    assert missing_key not in router._apply_filters(scored2)


# --------------------------------------------------------------------------- #
# 7. calculate_keyword_relevance 语义
# --------------------------------------------------------------------------- #


def test_calculate_keyword_relevance_semantics():
    """未命中返 0.0；命中且在开头返 1.0；None / 空串返 0.0；委托方法同口径。"""
    # 未命中 → 0.0（原实现返 0.1，属行为变更）
    assert calculate_keyword_relevance("完全无关内容", "量子纠缠") == 0.0
    # 命中且在开头 → 1.0
    assert calculate_keyword_relevance("量子纠缠记录", "量子纠缠") == 1.0
    # 命中但靠后 → (0, 1)
    mid = calculate_keyword_relevance("记录量子纠缠", "量子纠缠")
    assert 0.0 < mid < 1.0
    # 空值 / None → 0.0
    assert calculate_keyword_relevance(None, "量子纠缠") == 0.0
    assert calculate_keyword_relevance("量子纠缠记录", None) == 0.0
    assert calculate_keyword_relevance("", "量子纠缠") == 0.0
    assert calculate_keyword_relevance("量子纠缠记录", "") == 0.0

    # HybridSearch._calculate_keyword_score 委托同一实现
    assert HybridSearch._calculate_keyword_score(None, "完全无关内容", "量子纠缠") == 0.0
    assert HybridSearch._calculate_keyword_score(None, "量子纠缠记录", "量子纠缠") == 1.0


# --------------------------------------------------------------------------- #
# 8. _apply_filters：permanent 受门控，显式通道保留
# --------------------------------------------------------------------------- #


def test_apply_filters_gates_permanent_and_keeps_explicit_mention():
    """permanent=True 但分数低于阈值被淘汰；explicitly_mentioned=True 仍保留。"""
    router = _make_router()

    permanent_low = {
        "id": 1,
        "content": "permanent 低分记忆",
        "permanent": True,
        "final_score": 0.1,
        "component_scores": {"relevance_source": RELEVANCE_SOURCE_SEARCH},
    }
    explicit_low = {
        "id": 2,
        "content": "显式提及记忆",
        "explicitly_mentioned": True,
        "final_score": 0.1,
    }
    permanent_high = {
        "id": 3,
        "content": "permanent 高分记忆",
        "permanent": True,
        "final_score": 0.5,
    }

    kept_ids = [m["id"] for m in router._apply_filters([permanent_low, explicit_low, permanent_high])]
    assert 1 not in kept_ids, "permanent 不再无条件放行"
    assert 2 in kept_ids, "explicitly_mentioned 显式通道应保留"
    assert 3 in kept_ids


# --------------------------------------------------------------------------- #
# 9. _dedupe_memories 去重
# --------------------------------------------------------------------------- #


def test_dedupe_keeps_higher_score_search_source_and_first_order():
    """同 id 保留 final_score 高者；同分优先 search_score；缺 id 按 content；保持首现顺序。"""
    router = _make_router()

    # 同 id：一条 keyword_realtime 低分、一条 search_score 高分 → 保留高分那条
    low = {
        "id": 1,
        "content": "同一记忆",
        "final_score": 0.4,
        "component_scores": {"relevance_source": RELEVANCE_SOURCE_KEYWORD},
    }
    high = {
        "id": 1,
        "content": "同一记忆",
        "final_score": 0.7,
        "component_scores": {"relevance_source": RELEVANCE_SOURCE_SEARCH},
    }
    out = router._dedupe_memories([low, high])
    assert len(out) == 1
    assert out[0] is high

    # 同 id 同分 → 优先保留 search_score 来源
    tie_kw = {
        "id": 2,
        "content": "同分记忆",
        "final_score": 0.5,
        "component_scores": {"relevance_source": RELEVANCE_SOURCE_KEYWORD},
    }
    tie_search = {
        "id": 2,
        "content": "同分记忆",
        "final_score": 0.5,
        "component_scores": {"relevance_source": RELEVANCE_SOURCE_SEARCH},
    }
    out_tie = router._dedupe_memories([tie_kw, tie_search])
    assert len(out_tie) == 1
    assert out_tie[0] is tie_search

    # 缺 id → 按 content 去重，保留高分者
    no_id_low = {"content": "无 id 记忆", "final_score": 0.3, "component_scores": {}}
    no_id_high = {"content": "无 id 记忆", "final_score": 0.6, "component_scores": {}}
    out_content = router._dedupe_memories([no_id_low, no_id_high])
    assert len(out_content) == 1
    assert out_content[0] is no_id_high

    # 输出保持首次出现顺序
    first = {"id": 10, "content": "A", "final_score": 0.2}
    second = {"id": 11, "content": "B", "final_score": 0.9}
    out_order = router._dedupe_memories([first, second])
    assert [m["id"] for m in out_order] == [10, 11]


# --------------------------------------------------------------------------- #
# 10. route() 接线与标签
# --------------------------------------------------------------------------- #


def test_route_merges_recent_without_exemption_and_dedupes():
    """route()：最近记忆并入候选无豁免、无关最近记忆不注入、同 id 只出现一次。"""
    recent = [
        {"id": 1, "content": "关于苹果的记忆", "importance_score": 0.9, "created_at": NOW},
        {"id": 2, "content": "完全无关的记忆", "importance_score": 1.0, "created_at": NOW},
    ]
    search = [
        {
            "id": 1,
            "content": "关于苹果的记忆",
            "importance_score": 0.9,
            "created_at": NOW,
            "score": 0.9,
        },
        {
            "id": 3,
            "content": "苹果派做法",
            "importance_score": 0.6,
            "created_at": NOW,
            "score": 0.85,
        },
    ]

    router = MemoryRouter(
        memory_manager=_FakeMemoryManager(recent, search), config=RoutingConfig()
    )
    result = asyncio.run(
        router.route(query="苹果", session_id="sess-1", scene_type="chat")
    )

    # 标签：新标签存在，旧标签（与实现不符）不存在
    assert "同会话最近记忆纳入候选" in result.applied_rules
    assert "最近交互记忆优先" not in result.applied_rules

    ids = [m["id"] for m in result.memories]
    assert 2 not in ids, "与 query 无关的最近记忆不得注入"
    assert ids.count(1) == 1, "同一 id 只出现一次（去重生效）"
    assert set(ids) == {1, 3}

    # 保留的 id=1 来源应为 search_score（同 id 时保留 final_score 较高者）
    kept_one = next(m for m in result.memories if m["id"] == 1)
    assert kept_one["component_scores"]["relevance_source"] == RELEVANCE_SOURCE_SEARCH
