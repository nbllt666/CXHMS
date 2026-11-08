"""模块11 知识库工具（主模型自主沉淀经验 / 检索知识）。

两个工具：
- `write_knowledge_experience`：把可复用经验、结论或流程写入当前 agent 知识库
- `search_knowledge`：按自然语言检索当前 agent 知识库（向量 + FTS 混合）

agent 定位优先使用调用上下文（`get_current_agent_id()`），缺省回退 `default`。
"""

import logging
from typing import Any, Dict, List, Optional

from backend.core.tools.graph_tools import get_current_agent_id
from backend.core.tools.registry import tool_registry

logger = logging.getLogger(__name__)

_CONTENT_PREVIEW_CHARS = 200


def _resolve_manager(agent_id: Optional[str] = None):
    """从全局服务状态解析当前 agent 的知识库管理器。"""
    try:
        from backend.dependencies import _resolve_state

        state = _resolve_state()
    except Exception as exc:  # 未初始化时返回 None，由工具回传错误
        logger.warning(f"知识库工具无法获取服务状态: {exc}")
        return None

    registry = getattr(state, "knowledge_registry", None)
    if registry is None:
        return None
    target = agent_id or get_current_agent_id() or "default"
    return registry.get_manager(target)


async def write_knowledge_experience(
    content: str,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    importance: int = 3,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """把可复用经验写入当前 agent 的独立知识库。

    Args:
        content: 经验内容（非空）
        title: 可选标题（缺省由内容前 40 字生成）
        tags: 可选标签
        importance: 重要度 1..5，默认 3
        agent_id: 可选显式 agent（缺省取当前调用上下文）

    Returns:
        `{status, item_id, agent_id, deduplicated, message}` 或 `{error}`
    """
    text = str(content or "").strip()
    if not text:
        return {"error": "内容不能为空"}

    manager = _resolve_manager(agent_id)
    if manager is None:
        return {"error": "知识库服务不可用"}

    try:
        item = await manager.add_experience(
            title=title,
            content=text,
            tags=tags or [],
            importance=importance,
        )
    except Exception as exc:
        logger.error(f"写入知识库经验失败: {exc}")
        return {"error": f"写入知识库经验失败: {exc}"}

    deduplicated = bool(item.get("deduplicated"))
    return {
        "status": "success",
        "item_id": item.get("item_id"),
        "agent_id": item.get("agent_id"),
        "deduplicated": deduplicated,
        "message": "相同经验已存在" if deduplicated else "经验已写入知识库",
    }


async def search_knowledge(
    query: str,
    top_k: int = 8,
    tags: Optional[List[str]] = None,
    item_type: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """检索当前 agent 知识库（向量 + FTS 混合，RRF 融合）。

    Returns:
        `{status, query, count, fallback, results}` 或 `{error}`
    """
    text = str(query or "").strip()
    if not text:
        return {"error": "查询内容不能为空"}

    manager = _resolve_manager(agent_id)
    if manager is None:
        return {"error": "知识库服务不可用"}

    try:
        hits = await manager.search(
            query=text, top_k=top_k, tags=tags, item_type=item_type
        )
    except Exception as exc:
        logger.error(f"检索知识库失败: {exc}")
        return {"error": f"检索知识库失败: {exc}"}

    results = [
        {
            "item_id": hit.get("item_id"),
            "title": hit.get("title"),
            "content": str(hit.get("content") or "")[:_CONTENT_PREVIEW_CHARS],
            "item_type": hit.get("item_type"),
            "document_id": hit.get("document_id"),
            "tags": hit.get("tags") or [],
            "score": hit.get("score"),
        }
        for hit in hits
    ]
    return {
        "status": "success",
        "query": text,
        "count": len(results),
        "fallback": bool(getattr(manager, "last_search_fallback", False)),
        "results": results,
    }


def register_knowledge_tools() -> None:
    """注册知识库工具（由 `register_master_tools` 末尾安全调用）。"""
    tool_registry.register(
        name="write_knowledge_experience",
        description=(
            "将可复用的经验、结论或流程写入当前 Agent 的独立知识库，"
            "供后续会话检索复用。当用户要求记住某个结论/流程，或你判断某结论值得沉淀时调用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "要沉淀的经验内容（必填）"},
                "title": {"type": "string", "description": "可选标题，缺省由内容自动生成"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选标签，用于分类与过滤",
                },
                "importance": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "重要度 1..5，默认 3",
                },
            },
            "required": ["content"],
        },
        function=write_knowledge_experience,
        category="knowledge",
        tags=["knowledge", "experience", "memory"],
        examples=["记住这个结论：知识库检索优先向量，不可用时降级 FTS"],
    )

    tool_registry.register(
        name="search_knowledge",
        description=(
            "检索当前 Agent 的独立知识库（向量 + 全文混合检索）。"
            "当需要引用已沉淀的经验或用户上传的资料时调用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或自然语言问题（必填）"},
                "top_k": {"type": "integer", "description": "返回条数，默认 8"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选标签过滤",
                },
                "item_type": {
                    "type": "string",
                    "description": "可选条目类型过滤（experience / doc_chunk）",
                },
            },
            "required": ["query"],
        },
        function=search_knowledge,
        category="knowledge",
        tags=["knowledge", "search"],
        examples=["检索知识库里关于部署流程的经验"],
    )
