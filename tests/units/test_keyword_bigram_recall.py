"""2 字滑窗关键词召回单元测试（P1 修复）。

覆盖 spec 变更文档 ``20260925_模块1_修复向量写入与关键词召回.md`` 的 P1 口径：
    - ``extract_key_terms``：2 字滑窗 + 虚字剔除 + 去重保序 + 上限截断
    - ``calculate_keyword_relevance`` 三分支：整句命中（A）/ 2 字滑窗部分命中（B）/ 无重叠=0（C）
    - 分支 C 为相关度硬门控不变量：完全无重叠仍返回 ``0.0``，严禁放宽
    - ``MemoryManager.search_memories``：FTS5 trigram 命中为空时用 2 字词元 OR 兜底召回

设计原则：
    - 不做中文分词、不引入任何词典/第三方分词库
    - 检索类用例用 ``memory_manager`` fixture（tmp_path 临时库，不触碰真实数据/向量库）
"""

import pytest

from backend.core.memory.hybrid_search import (
    calculate_keyword_relevance,
    extract_key_terms,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# 1. extract_key_terms：基本提取与虚字剔除
# --------------------------------------------------------------------------- #


def test_extract_key_terms_basic_and_function_char_filter():
    """「我喜欢喝什么咖啡」应提取出实词对（喜欢/咖啡），并剔除含虚字的 2 字对。"""
    terms = extract_key_terms("我喜欢喝什么咖啡")
    print(f"[自测] extract_key_terms('我喜欢喝什么咖啡') = {terms}")

    assert "喜欢" in terms
    assert "咖啡" in terms
    # 含虚字（我/什/么）的 2 字对应被剔除
    assert "什么" not in terms
    assert "么咖" not in terms
    assert "我喜" not in terms


# --------------------------------------------------------------------------- #
# 2. extract_key_terms：空值 / 过短 / 上限截断
# --------------------------------------------------------------------------- #


def test_extract_key_terms_empty_and_short_and_max_terms():
    """None / 空串 / 单字 → ``[]``；``max_terms`` 截断生效。"""
    assert extract_key_terms(None) == []
    assert extract_key_terms("") == []
    assert extract_key_terms("咖") == []

    # 长查询：词元数受 max_terms 限制
    long_query = "量子纠缠退相干实验数据记录分析处理"
    full = extract_key_terms(long_query, max_terms=100)
    capped = extract_key_terms(long_query, max_terms=3)
    assert len(full) > 3
    assert len(capped) == 3
    # 截断保持前缀（保序）
    assert capped == full[:3]
    # 默认上限为 8
    assert len(extract_key_terms(long_query)) <= 8


# --------------------------------------------------------------------------- #
# 3. 关键对照：整句未命中但 2 字词元命中 → 分数 > 0
# --------------------------------------------------------------------------- #


def test_relevance_positive_for_related_content():
    """对照用例：修复前为 0.0，修复后应 > 0（命中「咖啡」词元）。"""
    score = calculate_keyword_relevance("用户偏好喝美式咖啡，不加糖", "我喜欢喝什么咖啡")
    print(
        "[自测] calculate_keyword_relevance('用户偏好喝美式咖啡，不加糖', '我喜欢喝什么咖啡') "
        f"= {score}"
    )
    assert score > 0.0


# --------------------------------------------------------------------------- #
# 4. 门控不变量：完全无重叠 → 严格 0.0
# --------------------------------------------------------------------------- #


def test_relevance_zero_invariant_for_unrelated_content():
    """完全无重叠 → 严格 ``0.0``（相关度硬门控不变量，严禁放宽）。"""
    score = calculate_keyword_relevance("今天天气很好适合散步", "我喜欢喝什么咖啡")
    print(
        "[自测] calculate_keyword_relevance('今天天气很好适合散步', '我喜欢喝什么咖啡') "
        f"= {score}"
    )
    assert score == 0.0


# --------------------------------------------------------------------------- #
# 5. 分支 A 未被破坏：整句命中仍按原位置衰减语义
# --------------------------------------------------------------------------- #


def test_branch_a_whole_query_hit_unchanged():
    """整句在开头命中 → ``1.0``；整句靠后命中 → 处于 (0, 1)。"""
    assert calculate_keyword_relevance("量子纠缠退相干实验数据记录", "量子纠缠") == 1.0
    mid = calculate_keyword_relevance("记录量子纠缠", "量子纠缠")
    assert 0.0 < mid < 1.0
    # 空值仍为 0.0
    assert calculate_keyword_relevance(None, "量子纠缠") == 0.0
    assert calculate_keyword_relevance("量子纠缠记录", None) == 0.0


# --------------------------------------------------------------------------- #
# 6. 分支 B 单调性：命中 2 个词元 > 命中 1 个词元
# --------------------------------------------------------------------------- #


def test_branch_b_monotonic_by_hit_count():
    """命中词元越多分数越高（本 query 词元集为 喜欢/欢喝/咖啡）。"""
    # 命中 1 个词元：仅含「咖啡」
    one_hit = calculate_keyword_relevance("这杯咖啡不错", "我喜欢喝什么咖啡")
    # 命中 2 个词元：含「喜欢」与「咖啡」（不含「欢喝」）
    two_hits = calculate_keyword_relevance("喜欢咖啡的味道", "我喜欢喝什么咖啡")
    print(f"[自测] 命中 1 个词元分数 = {one_hit}，命中 2 个词元分数 = {two_hits}")
    assert one_hit > 0.0
    assert two_hits > one_hit


# --------------------------------------------------------------------------- #
# 7. search_memories：FTS5 命中为空时的 2 字滑窗兜底召回
# --------------------------------------------------------------------------- #


def test_search_memories_bigram_fallback_recall(memory_manager):
    """写入含「咖啡」记忆，用自然语言问句检索应至少召回 1 条（修复前 0 条）。"""
    memory_manager.write_memory(
        content="用户偏好喝美式咖啡，不加糖",
        memory_type="long_term",
        importance=4,
        workspace_id="default",
        agent_id="default",
    )

    # 前置：确认走了 FTS5 分支（trigram 交集为空是本兜底的触发前提）
    print(f"[自测] FTS5 可用 = {getattr(memory_manager, '_fts5_available', False)}")

    results = memory_manager.search_memories(query="我喜欢喝什么咖啡", limit=10)
    print(f"[自测] search_memories('我喜欢喝什么咖啡') 召回 {len(results)} 条")
    assert len(results) >= 1
    assert any("咖啡" in r["content"] for r in results)