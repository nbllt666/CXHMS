"""ToolService 预生成 Mock。

实现 public/interface_stub/tool_service.pyi 的全部签名，
返回符合 public/schema/tool.json 契约的模拟值。
"""

from typing import Any, Dict, List, Optional


def _builtin_tool(name: str, description: str) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": {}},
        "category": "builtin",
        "type": "builtin",
        "enabled": True,
        "version": "1.0.0",
        "tags": [],
        "examples": [],
        "icon": None,
        "config": None,
        "status": "active",
    }


class MockToolService:
    """ToolService 的 Mock 实现。"""

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {
            "calculator": _builtin_tool("calculator", "数学计算器"),
            "datetime": _builtin_tool("datetime", "获取当前时间"),
            "weather": _builtin_tool("weather", "天气查询"),
        }

    async def list_tools(
        self,
        enabled_only: bool = True,
        include_builtin: bool = False,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        tools = {}
        for name, t in self._tools.items():
            if enabled_only and not t.get("enabled", True):
                continue
            if category and t.get("category") != category:
                continue
            tools[name] = dict(t)
        return {
            "status": "success",
            "tools": tools,
            "statistics": {"total": len(tools), "enabled": len(tools)},
        }

    async def register_tool(self, request: Dict[str, Any]) -> Dict[str, Any]:
        name = request["name"]
        if name in self._tools:
            raise ValueError(f"工具已存在: {name}")
        tool = {
            "name": name,
            "description": request["description"],
            "parameters": request["parameters"],
            "category": request.get("category", "general"),
            "type": request.get("type") or request.get("category", "general"),
            "enabled": request.get("enabled", True),
            "version": request.get("version", "1.0.0"),
            "tags": request.get("tags", []),
            "examples": request.get("examples", []),
            "icon": request.get("icon"),
            "config": request.get("config"),
            "status": "active" if request.get("enabled", True) else "inactive",
        }
        self._tools[name] = tool
        return {"status": "success", "tool": tool, "message": "工具注册成功"}

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"工具不存在: {name}")
        return {
            "status": "success",
            "result": {"mock": True, "name": name, "arguments": arguments},
            "message": "工具执行成功（mock）",
        }

    async def update_tool(self, name: str, request: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"工具不存在: {name}")
        for k, v in request.items():
            if v is not None:
                self._tools[name][k] = v
        self._tools[name]["status"] = "active" if self._tools[name].get("enabled", True) else "inactive"
        return {"status": "success", "tool": dict(self._tools[name]), "message": "工具更新成功"}

    async def delete_tool(self, name: str) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"工具不存在: {name}")
        if self._tools[name].get("category") == "builtin":
            raise ValueError("内置工具不可删除")
        del self._tools[name]
        return {"status": "success", "message": "工具删除成功"}

    async def get_tool_stats(self) -> Dict[str, Any]:
        return {
            "total": len(self._tools),
            "enabled": sum(1 for t in self._tools.values() if t.get("enabled", True)),
            "by_category": {},
        }
