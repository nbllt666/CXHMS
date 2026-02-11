from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel
from backend.core.exceptions import ToolError
from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)

router = APIRouter()


class ToolRegisterRequest(BaseModel):
    """工具注册请求"""
    name: str
    description: str
    parameters: Dict
    enabled: bool = True
    version: str = "1.0.0"
    category: str = "general"
    tags: List[str] = []
    examples: List[str] = []


class ToolCallRequest(BaseModel):
    """工具调用请求"""
    name: str
    arguments: Dict = {}


class MCPServerAddRequest(BaseModel):
    """MCP服务器添加请求"""
    name: str
    command: str
    args: List[str] = []
    env: Dict = {}


class MCPServerStartRequest(BaseModel):
    """MCP服务器启动请求"""
    name: str


class MCPServerStopRequest(BaseModel):
    """MCP服务器停止请求"""
    name: str


class MCPToolCallRequest(BaseModel):
    """MCP工具调用请求"""
    server_name: str
    tool_name: str
    arguments: Dict = {}


@router.get("/tools")
async def list_tools(enabled_only: bool = True):
    """列出工具"""
    from backend.core.tools.registry import tool_registry

    try:
        tools = tool_registry.list_tools_dict(enabled_only)
        stats = tool_registry.get_tool_stats()
        return {
            "status": "success",
            "tools": tools,
            "statistics": stats
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"列出工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools")
async def register_tool(request: ToolRegisterRequest):
    from backend.core.tools.registry import tool_registry

    try:
        tool_registry.register(
            name=request.name,
            description=request.description,
            parameters=request.parameters,
            enabled=request.enabled,
            version=request.version,
            category=request.category,
            tags=request.tags,
            examples=request.examples
        )
        return {
            "status": "success",
            "message": f"工具 {request.name} 注册成功"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"注册工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/tools/{name}")
async def get_tool(name: str):
    from backend.core.tools.registry import tool_registry

    try:
        tool = tool_registry.get_tool(name)
        if not tool:
            raise HTTPException(status_code=404, detail="工具不存在")

        return {
            "status": "success",
            "tool": tool.to_dict()
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.delete("/tools/{name}")
async def delete_tool(name: str):
    from backend.core.tools.registry import tool_registry

    try:
        success = tool_registry.delete_tool(name)
        if not success:
            raise HTTPException(status_code=404, detail="工具不存在")

        return {
            "status": "success",
            "message": f"工具 {name} 已删除"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    """调用工具"""
    from backend.core.tools.registry import tool_registry

    try:
        result = tool_registry.call_tool(request.name, request.arguments)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"调用工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/tools/openai")
async def get_openai_functions(enabled_only: bool = True):
    """获取OpenAI格式的工具列表"""
    from backend.core.tools.registry import tool_registry

    try:
        functions = tool_registry.list_openai_functions(enabled_only)
        return {
            "status": "success",
            "functions": functions
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取OpenAI工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/tools/stats")
async def get_tool_stats():
    from backend.core.tools.registry import tool_registry

    try:
        stats = tool_registry.get_tool_stats()
        return {
            "status": "success",
            "statistics": stats
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取工具统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/export")
async def export_tools():
    from backend.core.tools.registry import tool_registry

    try:
        tools = tool_registry.export_tools()
        return {
            "status": "success",
            "tools": tools,
            "total": len(tools)
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导出工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/import")
async def import_tools(tools: List[Dict]):
    from backend.core.tools.registry import tool_registry

    try:
        count = tool_registry.import_tools(tools)
        return {
            "status": "success",
            "imported": count,
            "message": f"成功导入 {count} 个工具"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导入工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/tools/mcp/servers")
async def get_mcp_servers():
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        servers = await mcp_mgr.list_servers()
        stats = mcp_mgr.get_stats()
        return {
            "status": "success",
            "servers": servers,
            "statistics": stats
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取MCP服务器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/mcp/servers")
async def add_mcp_server(request: MCPServerAddRequest):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        server = await mcp_mgr.add_server(
            name=request.name,
            command=request.command,
            args=request.args,
            env=request.env
        )
        return {
            "status": "success",
            "server": server,
            "message": f"MCP服务器 {request.name} 已添加"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"添加MCP服务器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.delete("/tools/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        success = await mcp_mgr.remove_server(name)
        if not success:
            raise HTTPException(status_code=404, detail="MCP服务器不存在")
        return {
            "status": "success",
            "message": f"MCP服务器 {name} 已移除"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"移除MCP服务器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/mcp/servers/start")
async def start_mcp_server(request: MCPServerStartRequest):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        success = await mcp_mgr.start_server(request.name)
        return {
            "status": "success",
            "message": f"MCP服务器 {request.name} 已启动"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"启动MCP服务器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/mcp/servers/stop")
async def stop_mcp_server(request: MCPServerStopRequest):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        success = await mcp_mgr.stop_server(request.name)
        return {
            "status": "success",
            "message": f"MCP服务器 {request.name} 已停止"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"停止MCP服务器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/tools/mcp/servers/{name}/health")
async def check_mcp_server_health(name: str):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        health = await mcp_mgr.check_server_health(name)
        return {
            "status": "success",
            "health": health
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"检查MCP服务器健康状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/tools/mcp/servers/{name}/tools")
async def get_mcp_server_tools(name: str):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        tools = await mcp_mgr.get_tools(name)
        return {
            "status": "success",
            "tools": tools,
            "total": len(tools)
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取MCP工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/mcp/call")
async def call_mcp_tool(request: MCPToolCallRequest):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        result = await mcp_mgr.call_tool(
            server_name=request.server_name,
            tool_name=request.tool_name,
            arguments=request.arguments
        )
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"调用MCP工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/tools/mcp/sync")
async def sync_mcp_tools(name: str):
    from backend.api.app import get_mcp_manager

    try:
        mcp_mgr = get_mcp_manager()
        await mcp_mgr._sync_tools(name)
        return {
            "status": "success",
            "message": f"MCP工具已同步: {name}"
        }
    except ToolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"同步MCP工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/tools/plugins")
async def get_plugins():
    from backend.core.tools import tool_registry

    try:
        tools = tool_registry.list_tools_dict(enabled_only=False)
        return {
            "status": "success",
            "plugins": tools,
            "total": len(tools)
        }
    except Exception as e:
        return {
            "status": "success",
            "plugins": [],
            "total": 0,
            "message": f"插件功能暂不可用: {str(e)}"
        }
