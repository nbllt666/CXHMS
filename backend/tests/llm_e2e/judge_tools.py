"""评判代理辅助工具 - 定义 LLM Judge 可调用的验证工具及执行器"""

import json
from typing import Any, Dict

from .client import CXHMSClient

# OpenAI function calling 格式的工具定义
JUDGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_memories",
            "description": "搜索 CXHMS 记忆库，验证记忆是否被正确存储。用于交叉验证系统声称已存储的记忆是否确实存在。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chat_history",
            "description": "获取指定会话的聊天历史，验证上下文是否完整保留。用于检查多轮对话中系统是否正确保留了之前的对话内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "会话ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回消息数量",
                        "default": 20,
                    },
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tools",
            "description": "获取 CXHMS 系统中可用的工具列表，验证工具注册状态。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_health",
            "description": "检查 CXHMS 系统健康状态，验证各组件是否正常运行。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory_details",
            "description": "获取指定记忆的详细信息，验证记忆内容准确性。",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "integer",
                        "description": "记忆ID",
                    }
                },
                "required": ["memory_id"],
            },
        },
    },
]


class ToolExecutor:
    """执行评判工具调用的执行器，通过 CXHMS API 客户端与系统交互。"""

    def __init__(self, client: CXHMSClient) -> None:
        """初始化工具执行器。

        Args:
            client: CXHMSClient 实例
        """
        self.client = client
        self._handlers = {
            "search_memories": self._search_memories,
            "get_chat_history": self._get_chat_history,
            "list_tools": self._list_tools,
            "check_health": self._check_health,
            "get_memory_details": self._get_memory_details,
        }

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行指定工具并返回 JSON 字符串结果。

        Args:
            tool_name: 工具名称
            arguments: 工具参数字典

        Returns:
            工具执行结果的 JSON 字符串
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            return json.dumps(
                {"error": f"未知工具: {tool_name}"}, ensure_ascii=False
            )

        try:
            result = await handler(arguments)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps(
                {"error": f"工具执行失败: {tool_name}", "detail": str(e)},
                ensure_ascii=False,
            )

    async def _search_memories(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """搜索记忆库。"""
        query = args.get("query", "")
        limit = args.get("limit", 5)

        data = await self.client.search_memories(query=query, limit=limit)
        memories = data.get("memories", [])
        simplified = [
            {
                "id": m.get("id"),
                "content": m.get("content", "")[:200],
                "type": m.get("type"),
                "importance": m.get("importance"),
            }
            for m in memories
        ]
        return {"total": len(simplified), "memories": simplified}

    async def _get_chat_history(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取聊天历史。"""
        session_id = args.get("session_id", "")
        limit = args.get("limit", 20)

        data = await self.client.get_chat_history(session_id=session_id, limit=limit)
        messages = data.get("messages", [])
        simplified = [
            {
                "role": m.get("role"),
                "content": m.get("content", "")[:300],
            }
            for m in messages
        ]
        return {"session_id": session_id, "total": len(simplified), "messages": simplified}

    async def _list_tools(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取工具列表。"""
        data = await self.client.list_tools()
        tools = data.get("tools", {})
        tool_names = list(tools.keys()) if isinstance(tools, dict) else []
        return {"total": len(tool_names), "tools": tool_names}

    async def _check_health(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """检查系统健康状态。"""
        data = await self.client.check_health()
        return {
            "status": data.get("status"),
            "version": data.get("version"),
            "components": data.get("components", {}),
        }

    async def _get_memory_details(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """获取记忆详情。"""
        memory_id = args.get("memory_id")
        if memory_id is None:
            return {"error": "缺少 memory_id 参数"}

        data = await self.client.get_memory(memory_id=memory_id)
        memory = data.get("memory", {})
        return {
            "id": memory.get("id"),
            "content": memory.get("content", "")[:500],
            "type": memory.get("type"),
            "importance": memory.get("importance"),
            "tags": memory.get("tags", []),
            "created_at": memory.get("created_at"),
            "metadata": memory.get("metadata", {}),
        }
