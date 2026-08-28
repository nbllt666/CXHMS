"""backend.core.config.diff 的单元测试。

覆盖 compute_diff 在以下场景下的行为：
    1. 顶层 models 段字段变化 → changed_sections={'models'}
    2. memory.vector_backend 变化 → changed_sections={'memory'}
    3. memory.dedup_threshold 变化 → changed_sections={'memory'}
    4. 无变化 → diff.is_empty() == True
    5. memory.weaviate.host 嵌套字段变化 → changed_sections={'memory'}
    6. 顶层 vector.host 变化 → changed_sections={'vector'}

构造 CXHMSConfig 实例时直接用 CXHMSConfig() 默认值，然后修改某个字段创建"新"实例。
"""

import pytest

from backend.core.config.diff import ConfigDiff, compute_diff
from config.settings import CXHMSConfig


# --------------------------------------------------------------------------- #
# 辅助：基于默认 CXHMSConfig 构造一份独立副本
# --------------------------------------------------------------------------- #


def _make_default_config() -> CXHMSConfig:
    """构造一份默认 CXHMSConfig 实例。

    CXHMSConfig 字段都用 field(default_factory=...) 声明，每次构造都会
    独立创建嵌套 dataclass，因此两份 CXHMSConfig() 互不影响。
    """
    return CXHMSConfig()


# --------------------------------------------------------------------------- #
# 测试用例
# --------------------------------------------------------------------------- #


def test_model_change_detected():
    """修改 models.main.model → changed_sections={'models'}，field_changes 含 'models.main.model'"""
    old = _make_default_config()
    new = _make_default_config()

    # 修改 models.main.model
    new.models.main.model = "qwen2.5:7b"

    diff = compute_diff(old, new)

    assert not diff.is_empty()
    assert diff.changed_sections == {"models"}
    assert "models.main.model" in diff.field_changes


def test_vector_backend_change():
    """修改 memory.vector_backend → changed_sections={'memory'}，field_changes 含 'memory.vector_backend'"""
    old = _make_default_config()
    new = _make_default_config()

    # 修改 memory.vector_backend（默认 "milvus_lite" → "weaviate"）
    new.memory.vector_backend = "weaviate"

    diff = compute_diff(old, new)

    assert not diff.is_empty()
    assert diff.changed_sections == {"memory"}
    assert "memory.vector_backend" in diff.field_changes


def test_pure_threshold_change():
    """仅修改 memory.dedup_threshold → changed_sections={'memory'}，field_changes 含 'memory.dedup_threshold'"""
    old = _make_default_config()
    new = _make_default_config()

    # 修改 memory.dedup_threshold（默认 0.85 → 0.92）
    new.memory.dedup_threshold = 0.92

    diff = compute_diff(old, new)

    assert not diff.is_empty()
    assert diff.changed_sections == {"memory"}
    assert "memory.dedup_threshold" in diff.field_changes
    # 不应有其他段被标记
    assert "vector" not in diff.changed_sections
    assert "models" not in diff.changed_sections


def test_no_change_returns_empty():
    """两个相同 config → diff.is_empty() == True"""
    old = _make_default_config()
    new = _make_default_config()

    diff = compute_diff(old, new)

    assert diff.is_empty()
    assert diff.changed_sections == set()
    assert diff.field_changes == []


def test_nested_field_change():
    """修改 memory.weaviate.host → changed_sections={'memory'}，field_changes 含 'memory.weaviate.host'"""
    old = _make_default_config()
    new = _make_default_config()

    # 修改 memory.weaviate.host（默认 "localhost" → "weaviate.local"）
    new.memory.weaviate.host = "weaviate.local"

    diff = compute_diff(old, new)

    assert not diff.is_empty()
    assert diff.changed_sections == {"memory"}
    assert "memory.weaviate.host" in diff.field_changes
    # 不应误报顶层 vector 段
    assert "vector" not in diff.changed_sections


def test_top_level_vector_change():
    """修改顶层 vector.host → changed_sections={'vector'}，field_changes 含 'vector.host'"""
    old = _make_default_config()
    new = _make_default_config()

    # 修改顶层 vector.host（默认 "localhost" → "qdrant.prod"）
    new.vector.host = "qdrant.prod"

    diff = compute_diff(old, new)

    assert not diff.is_empty()
    assert diff.changed_sections == {"vector"}
    assert "vector.host" in diff.field_changes
    # 不应误报 memory 段（vector 与 memory.vector_backend 是两个不同位置）
    assert "memory" not in diff.changed_sections


# --------------------------------------------------------------------------- #
# 边界用例：compute_diff 对 None / 首次加载的处理
# --------------------------------------------------------------------------- #


def test_old_none_returns_full_diff():
    """old 为 None（首次加载）→ 所有顶层段都被标记为变化"""
    new = _make_default_config()

    diff = compute_diff(None, new)

    assert not diff.is_empty()
    # 13 个顶层段全部标记（M-EX3：security 段已纳入 diff 范围）
    expected_sections = {
        "llm", "models", "vector", "acp", "database",
        "memory", "context", "rate_limit", "cors", "system",
        "graph", "cxfc", "security",
    }
    assert diff.changed_sections == expected_sections


def test_both_none_returns_empty():
    """old 与 new 都为 None → 返回空 diff"""
    diff = compute_diff(None, None)

    assert diff.is_empty()
