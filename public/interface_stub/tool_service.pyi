"""ToolService 接口契约存根。

对应 backend/api/routers/tools.py 的路由与 backend/core/tools/registry.py。
零实现逻辑，仅声明签名。模块实现必须严格匹配本存根。

@version 1.0.0
@see public/schema/tool.json
"""

from typing import Any, Dict, List, Optional


class ToolService:
    """工具服务接口。

    提供工具注册、列举、调用与 MCP 服务器管理能力。
    工具数据必须符合 public/schema/tool.json。
    """

    async def list_tools(
        self,
        enabled_only: bool = True,
        include_builtin: bool = False,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列举工具，返回 {status, tools, statistics}。

        Raises:
            ToolError: 注册表查询失败
        """
        ...

    async def register_tool(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """注册工具，返回 {status, tool, message}。

        Raises:
            ValidationError: 名称非法或参数 schema 无效
            ToolError: 注册失败
        """
        ...

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具，返回 {status, result, message}。

        Raises:
            ToolError: 工具不存在或执行失败
            ValidationError: 参数不匹配工具 schema
        """
        ...

    async def update_tool(self, name: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """更新工具配置（启用/禁用/描述等）。

        Raises:
            ToolError: 工具不存在
        """
        ...

    async def delete_tool(self, name: str) -> Dict[str, Any]:
        """注销工具。内置工具不可删除。

        Raises:
            ToolError: 工具不存在或为内置工具
        """
        ...

    async def get_tool_stats(self) -> Dict[str, Any]:
        """返回工具调用统计。"""
        ...
