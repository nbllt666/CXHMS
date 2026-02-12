from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import uuid
import asyncio
import inspect
from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)

# 内置工具名称集合
BUILTIN_TOOL_NAMES = {"calculator", "datetime", "random", "json_format"}


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict
    function: Callable = None
    enabled: bool = True
    version: str = "1.0.0"
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    call_count: int = 0
    last_called: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "enabled": self.enabled,
            "version": self.version,
            "category": self.category,
            "tags": self.tags,
            "examples": self.examples,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "call_count": self.call_count,
            "last_called": self.last_called
        }

    def to_openai_function(self) -> Dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ToolRegistry:
    _instance = None
    _tools: Dict[str, Tool] = {}
    _lock = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._lock = threading.Lock()
        return cls._instance

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict,
        function: Callable = None,
        enabled: bool = True,
        version: str = "1.0.0",
        category: str = "general",
        tags: List[str] = None,
        examples: List[str] = None
    ) -> Tool:
        with self._lock:
            if name in self._tools:
                tool = self._tools[name]
                tool.description = description
                tool.parameters = parameters
                tool.enabled = enabled
                tool.version = version
                tool.category = category
                tool.tags = tags or []
                tool.examples = examples or []
                tool.updated_at = datetime.now().isoformat()
            else:
                tool = Tool(
                    name=name,
                    description=description,
                    parameters=parameters,
                    function=function,
                    enabled=enabled,
                    version=version,
                    category=category,
                    tags=tags or [],
                    examples=examples or []
                )
                self._tools[name] = tool

            logger.info(f"工具已注册: {name}")
            return tool

    def get_tool(self, name: str) -> Optional[Tool]:
        with self._lock:
            return self._tools.get(name)

    def list_tools(self, enabled_only: bool = True) -> List[Tool]:
        with self._lock:
            tools = list(self._tools.values())
            if enabled_only:
                return [t for t in tools if t.enabled]
            return tools

    def list_tools_dict(self, enabled_only: bool = True) -> List[Dict]:
        return [t.to_dict() for t in self.list_tools(enabled_only)]

    def list_openai_functions(self, enabled_only: bool = True, include_builtin: bool = True, category: str = None) -> List[Dict]:
        """
        获取所有工具的 OpenAI 函数定义
        
        Args:
            enabled_only: 是否只返回启用的工具
            include_builtin: 是否包含内置工具（默认True，强制开启）
            category: 按类别过滤工具（main/summary/memory/general）
        """
        # 获取工具列表
        all_tools = self.list_tools(enabled_only)
        
        # 按类别过滤
        if category:
            filtered_tools = [t for t in all_tools if t.category == category]
        else:
            filtered_tools = all_tools
        
        tools = [t.to_openai_function() for t in filtered_tools if t.enabled]
        
        # 强制包含内置工具
        if include_builtin:
            from backend.core.tools.builtin import get_builtin_tools
            builtin_tools = get_builtin_tools()
            # 避免重复添加
            existing_names = {t["function"]["name"] for t in tools}
            for builtin in builtin_tools:
                if builtin["function"]["name"] not in existing_names:
                    tools.append(builtin)
        
        return tools

    def call_tool(self, name: str, arguments: Dict = None) -> Dict:
        if name in BUILTIN_TOOL_NAMES:
            from backend.core.tools.builtin import call_builtin_tool
            return call_builtin_tool(name, arguments or {})
        
        tool = self.get_tool(name)
        if tool is None:
            return {
                "success": False,
                "error": f"工具不存在: {name}"
            }

        if not tool.enabled:
            return {
                "success": False,
                "error": f"工具已禁用: {name}"
            }

        if tool.function is None:
            return {
                "success": False,
                "error": f"工具未实现: {name}"
            }

        try:
            if arguments:
                result = tool.function(**arguments)
            else:
                result = tool.function()

            if inspect.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, result)
                        result = future.result(timeout=60)
                except RuntimeError:
                    result = asyncio.run(result)

            with self._lock:
                tool.call_count += 1
                tool.last_called = datetime.now().isoformat()

            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error(f"工具调用失败: {name}, {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def call_tool_async(self, name: str, arguments: Dict = None) -> Dict:
        if name in BUILTIN_TOOL_NAMES:
            from backend.core.tools.builtin import call_builtin_tool
            return call_builtin_tool(name, arguments or {})
        
        tool = self.get_tool(name)
        if tool is None:
            return {
                "success": False,
                "error": f"工具不存在: {name}"
            }

        if not tool.enabled:
            return {
                "success": False,
                "error": f"工具已禁用: {name}"
            }

        if tool.function is None:
            return {
                "success": False,
                "error": f"工具未实现: {name}"
            }

        try:
            if arguments:
                result = tool.function(**arguments)
            else:
                result = tool.function()

            if inspect.iscoroutine(result):
                result = await result

            with self._lock:
                tool.call_count += 1
                tool.last_called = datetime.now().isoformat()

            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error(f"工具调用失败: {name}, {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_tool(self, name: str) -> bool:
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info(f"工具已删除: {name}")
                return True
            return False

    def enable_tool(self, name: str) -> bool:
        with self._lock:
            if name in self._tools:
                self._tools[name].enabled = True
                return True
            return False

    def disable_tool(self, name: str) -> bool:
        with self._lock:
            if name in self._tools:
                self._tools[name].enabled = False
                return True
            return False

    def get_tool_stats(self) -> Dict:
        with self._lock:
            tools = list(self._tools.values())
            total_calls = sum(t.call_count for t in tools)
            enabled_count = sum(1 for t in tools if t.enabled)
            by_category = {}
            for t in tools:
                if t.category not in by_category:
                    by_category[t.category] = []
                by_category[t.category].append(t.name)

            return {
                "total_tools": len(tools),
                "enabled_tools": enabled_count,
                "disabled_tools": len(tools) - enabled_count,
                "total_calls": total_calls,
                "by_category": by_category,
                "top_tools": sorted(
                    [(t.name, t.call_count) for t in tools],
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
            }

    def export_tools(self) -> List[Dict]:
        return [t.to_dict() for t in self._tools.values()]

    def import_tools(self, tools_data: List[Dict]) -> int:
        imported = 0
        for tool_data in tools_data:
            try:
                self.register(
                    name=tool_data["name"],
                    description=tool_data["description"],
                    parameters=tool_data.get("parameters", {}),
                    enabled=tool_data.get("enabled", True),
                    version=tool_data.get("version", "1.0.0"),
                    category=tool_data.get("category", "general"),
                    tags=tool_data.get("tags", []),
                    examples=tool_data.get("examples", [])
                )
                imported += 1
            except Exception as e:
                logger.warning(f"导入工具失败: {tool_data.get('name')}, {e}")

        return imported

    def clear(self):
        with self._lock:
            self._tools.clear()
            logger.info("工具注册表已清空")


tool_registry = ToolRegistry()


def tool(
    name: str = None,
    description: str = "",
    parameters: Dict = None,
    enabled: bool = True,
    version: str = "1.0.0",
    category: str = "general",
    tags: List[str] = None,
    examples: List[str] = None
):
    def decorator(func):
        tool_name = name or func.__name__
        tool_registry.register(
            name=tool_name,
            description=description or func.__doc__ or "",
            parameters=parameters or {"type": "object", "properties": {}},
            function=func,
            enabled=enabled,
            version=version,
            category=category,
            tags=tags,
            examples=examples
        )
        return func

    return decorator
