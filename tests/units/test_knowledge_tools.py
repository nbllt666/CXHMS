"""模块11 知识库工具单元测试（不依赖真实服务状态）。"""

import pytest

from backend.core.tools import knowledge_tools
from backend.core.tools.registry import tool_registry


class _FakeManager:
    """最小知识库管理器替身。"""

    def __init__(self) -> None:
        self.last_search_fallback = True
        self.calls = []

    async def add_experience(self, title=None, content="", tags=(), importance=3):
        self.calls.append(("add", title, content, list(tags), importance))
        if self.raise_on_add:
            raise RuntimeError("boom")
        return {
            "item_id": "item-1",
            "agent_id": "agent_x",
            "item_type": "experience",
            "deduplicated": False,
        }

    async def search(self, query, top_k=8, tags=None, item_type=None):
        self.calls.append(("search", query, top_k, tags, item_type))
        return [
            {
                "item_id": "item-1",
                "title": "标题",
                "content": "x" * 500,
                "item_type": "experience",
                "document_id": None,
                "tags": ["t"],
                "score": 0.5,
            }
        ]

    raise_on_add = False


@pytest.fixture()
def fake_manager(monkeypatch):
    manager = _FakeManager()
    monkeypatch.setattr(knowledge_tools, "_resolve_manager", lambda agent_id=None: manager)
    return manager


@pytest.mark.asyncio
async def test_write_experience_success(fake_manager):
    result = await knowledge_tools.write_knowledge_experience(
        content="知识库经验内容", title="标题", tags=["a"], importance=4
    )
    assert result["status"] == "success"
    assert result["item_id"] == "item-1"
    assert result["deduplicated"] is False
    assert fake_manager.calls == [("add", "标题", "知识库经验内容", ["a"], 4)]


@pytest.mark.asyncio
async def test_write_experience_rejects_empty_content(fake_manager):
    result = await knowledge_tools.write_knowledge_experience(content="   ")
    assert "error" in result
    assert fake_manager.calls == []


@pytest.mark.asyncio
async def test_write_experience_reports_failure(fake_manager):
    fake_manager.raise_on_add = True
    result = await knowledge_tools.write_knowledge_experience(content="内容")
    assert "error" in result


@pytest.mark.asyncio
async def test_write_experience_without_manager(monkeypatch):
    monkeypatch.setattr(knowledge_tools, "_resolve_manager", lambda agent_id=None: None)
    result = await knowledge_tools.write_knowledge_experience(content="内容")
    assert result == {"error": "知识库服务不可用"}


@pytest.mark.asyncio
async def test_search_knowledge_truncates_preview(fake_manager):
    result = await knowledge_tools.search_knowledge(query="检索", top_k=3, tags=["t"])
    assert result["status"] == "success"
    assert result["count"] == 1
    assert result["fallback"] is True
    assert len(result["results"][0]["content"]) == knowledge_tools._CONTENT_PREVIEW_CHARS


@pytest.mark.asyncio
async def test_search_knowledge_rejects_empty_query(fake_manager):
    result = await knowledge_tools.search_knowledge(query="  ")
    assert "error" in result
    assert fake_manager.calls == []


def test_register_knowledge_tools_registers_both():
    knowledge_tools.register_knowledge_tools()
    assert tool_registry.get_tool("write_knowledge_experience") is not None
    assert tool_registry.get_tool("search_knowledge") is not None
