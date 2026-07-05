"""MemoryRouter 单元测试。

覆盖修复点：
    - B8: ``_get_recent_memories`` 上界分页（``max_pages=10``）
    - D5: ``max_tool_rounds`` 统一（chat.py 与 stream.py 同口径）

设计原则：
    - B8：构造稀疏 session 标签场景（tags 匹配但 session_id 字段不匹配），
      验证 ``_get_recent_memories`` 最多翻 10 页即停止，不触发全表扫描
    - D5：静态扫描 chat.py 与 stream.py 源码，确认 ``max_tool_rounds`` 来自
      ``settings.config.llm.max_tool_rounds``（同口径）
"""

import inspect

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# B8: _get_recent_memories 上界分页
# --------------------------------------------------------------------------- #


def test_b8_get_recent_memories_has_max_pages_bound(memory_manager, fake_vector_store, fake_embedding):
    """B8: ``_get_recent_memories`` 有 ``max_pages=10`` 上界，最多翻 10 页。

    回归断言：修复前 ``while recent_count < 50`` 无最大 page 限制，稀疏 session
    标签下退化为线性全扫；修复后加 ``max_pages = 10``，循环条件
    ``while recent_count < 50 and page < max_pages``。
    """
    from backend.core.memory.router import MemoryRouter, RoutingConfig

    router = MemoryRouter(
        memory_manager=memory_manager,
        vector_store=fake_vector_store,
        embedding_model=fake_embedding,
        config=RoutingConfig(),
    )

    # 写入 300 条记忆（tags 含 "sparse-session"，但 session_id 字段不存在）
    # 让 search_memories 的 tags LIKE 匹配，但 _get_recent_memories 的
    # mem.get("session_id") == session_id 永远不匹配 → recent_count 不增长
    for i in range(300):
        memory_manager.write_memory(
            content=f"稀疏 session 测试记忆 {i}",
            memory_type="long_term",
            importance=3,
            tags=["sparse-session"],
            agent_id="default",
            workspace_id="default",
        )

    # 用 monkeypatch 计数 search_memories 调用次数
    call_count = {"count": 0}
    original_search = memory_manager.search_memories

    def counting_search(*args, **kwargs):
        call_count["count"] += 1
        return original_search(*args, **kwargs)

    memory_manager.search_memories = counting_search

    # 调用 _get_recent_memories（同步方法）
    result = router._get_recent_memories("sparse-session")

    # 最多翻 max_pages=10 页，不触发全表扫描（300 条 / 20 = 15 页）
    assert call_count["count"] <= 10, (
        f"B8 回归：_get_recent_memories 翻页 {call_count['count']} 次，超过 max_pages=10"
    )
    # recent_count 没增长到 50，因 session_id 字段不匹配
    assert len(result) < 50


def test_b8_get_recent_memories_returns_within_bound(memory_manager, fake_vector_store, fake_embedding):
    """B8: ``_get_recent_memories`` 返回的 memories 数量不超过 30（截断保护）。

    回归断言：``return memories[:30]`` 截断，即使 recent_count 增长也不超过 30 条。
    """
    from backend.core.memory.router import MemoryRouter, RoutingConfig

    router = MemoryRouter(
        memory_manager=memory_manager,
        vector_store=fake_vector_store,
        embedding_model=fake_embedding,
        config=RoutingConfig(),
    )

    # 写入少量记忆，tags 含 "matched-session"
    for i in range(5):
        memory_manager.write_memory(
            content=f"匹配 session 记忆 {i}",
            memory_type="long_term",
            importance=3,
            tags=["matched-session"],
            agent_id="default",
        )

    result = router._get_recent_memories("matched-session")
    # 截断保护：不超过 30 条
    assert len(result) <= 30


def test_b8_get_recent_memories_empty_session_returns_empty(memory_manager, fake_vector_store, fake_embedding):
    """B8: session_id 为空时返回空列表，不翻页。

    回归断言：``if not session_id: return []`` 提前退出，不触发任何 search_memories 调用。
    """
    from backend.core.memory.router import MemoryRouter, RoutingConfig

    router = MemoryRouter(
        memory_manager=memory_manager,
        vector_store=fake_vector_store,
        embedding_model=fake_embedding,
        config=RoutingConfig(),
    )

    result = router._get_recent_memories(None)
    assert result == []

    result2 = router._get_recent_memories("")
    assert result2 == []


# --------------------------------------------------------------------------- #
# D5: max_tool_rounds 统一（chat.py + stream.py 同口径）
# --------------------------------------------------------------------------- #


def test_d5_chat_py_uses_settings_config_max_tool_rounds():
    """D5: chat.py 的 ``max_tool_rounds`` 来自 ``settings.config.llm.max_tool_rounds``。

    回归断言：修复前 chat.py 与 stream.py 的 max_tool_rounds 不一致
    （chat.py 用 settings.config.llm.max_tool_rounds，stream.py 硬编码 50）；
    修复后两边都用 ``settings.config.llm.max_tool_rounds``。
    """
    from backend.api.routers import chat as chat_module

    source = inspect.getsource(chat_module)
    # 应包含 settings.config.llm.max_tool_rounds 的引用
    assert "settings.config.llm.max_tool_rounds" in source, (
        "chat.py 未使用 settings.config.llm.max_tool_rounds 统一配置"
    )
    # 不应硬编码 max_tool_rounds = 50 或 = 10
    import re

    hardcoded = re.findall(r"max_tool_rounds\s*=\s*\d+", source)
    assert hardcoded == [], f"chat.py 硬编码 max_tool_rounds: {hardcoded}"


def test_d5_stream_uses_settings_config_max_tool_rounds():
    """D5: stream.py 的 ``max_tool_rounds`` 来自 ``settings.config.llm.max_tool_rounds``。

    回归断言：修复前 stream.py 硬编码 50；修复后用 ``settings.config.llm.max_tool_rounds``。
    """
    from backend.core.chat import stream as stream_module

    source = inspect.getsource(stream_module)
    assert "settings.config.llm.max_tool_rounds" in source, (
        "stream.py 未使用 settings.config.llm.max_tool_rounds 统一配置"
    )
    # 不应硬编码 max_tool_rounds = 50 或 = 10
    import re

    hardcoded = re.findall(r"max_tool_rounds\s*=\s*\d+", source)
    assert hardcoded == [], f"stream.py 硬编码 max_tool_rounds: {hardcoded}"


def test_d5_chat_and_stream_same_config_source():
    """D5: chat.py 与 stream.py 的 max_tool_rounds 引用同一配置口径。

    回归断言：两边都用 ``settings.config.llm.max_tool_rounds``，无 50 vs 10 不一致。
    """
    from backend.api.routers import chat as chat_module
    from backend.core.chat import stream as stream_module

    chat_source = inspect.getsource(chat_module)
    stream_source = inspect.getsource(stream_module)

    config_ref = "settings.config.llm.max_tool_rounds"
    assert config_ref in chat_source
    assert config_ref in stream_source
