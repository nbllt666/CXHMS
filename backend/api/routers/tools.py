from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel

router = APIRouter()


class ToolRegisterRequest(BaseModel):
    name: str
    description: str
    parameters: Dict
    enabled: bool = True
    version: str = "1.0.0"
    category: str = "general"
    tags: List[str] = []
    examples: List[str] = []


class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict = {}


@router.get("/api/tools")
async def list_tools(enabled_only: bool = True):
    from core.tools.registry import tool_registry

    tools = tool_registry.list_tools_dict(enabled_only)
    stats = tool_registry.get_tool_stats()

    return {
        "status": "success",
        "tools": tools,
        "statistics": stats
    }


@router.post("/api/tools")
async def register_tool(request: ToolRegisterRequest):
    from core.tools.registry import tool_registry

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tools/{name}")
async def get_tool(name: str):
    from core.tools.registry import tool_registry

    tool = tool_registry.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")

    return {
        "status": "success",
        "tool": tool.to_dict()
    }


@router.delete("/api/tools/{name}")
async def delete_tool(name: str):
    from core.tools.registry import tool_registry

    success = tool_registry.delete_tool(name)
    if not success:
        raise HTTPException(status_code=404, detail="工具不存在")

    return {
        "status": "success",
        "message": f"工具 {name} 已删除"
    }


@router.post("/api/tools/call")
async def call_tool(request: ToolCallRequest):
    from core.tools.registry import tool_registry

    result = tool_registry.call_tool(request.name, request.arguments)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/api/tools/openai")
async def get_openai_functions(enabled_only: bool = True):
    from core.tools.registry import tool_registry

    functions = tool_registry.list_openai_functions(enabled_only)
    return {
        "status": "success",
        "functions": functions
    }


@router.get("/api/tools/stats")
async def get_tool_stats():
    from core.tools.registry import tool_registry

    stats = tool_registry.get_tool_stats()
    return {
        "status": "success",
        "statistics": stats
    }


@router.post("/api/tools/export")
async def export_tools():
    from core.tools.registry import tool_registry

    tools = tool_registry.export_tools()
    return {
        "status": "success",
        "tools": tools,
        "total": len(tools)
    }


@router.post("/api/tools/import")
async def import_tools(tools: List[Dict]):
    from core.tools.registry import tool_registry

    count = tool_registry.import_tools(tools)
    return {
        "status": "success",
        "imported": count,
        "message": f"成功导入 {count} 个工具"
    }


@router.get("/api/tools/mcp/servers")
async def get_mcp_servers():
    from core.tools.mcp import mcp_manager

    try:
        servers = mcp_manager.list_servers()
        return {
            "status": "success",
            "servers": servers,
            "total": len(servers)
        }
    except Exception as e:
        return {
            "status": "success",
            "servers": [],
            "total": 0,
            "message": f"MCP功能暂不可用: {str(e)}"
        }


@router.get("/api/tools/plugins")
async def get_plugins():
    from core.tools.plugin import plugin_manager

    try:
        plugins = plugin_manager.get_plugins()
        return {
            "status": "success",
            "plugins": plugins,
            "total": len(plugins)
        }
    except Exception as e:
        return {
            "status": "success",
            "plugins": [],
            "total": 0,
            "message": f"插件功能暂不可用: {str(e)}"
        }
