import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.cache import agent_config_cache
from backend.core.logging_config import get_contextual_logger

router = APIRouter()
logger = get_contextual_logger(__name__)

# Agent 配置文件路径
AGENTS_CONFIG_PATH = "data/agents.json"


class AgentConfig(BaseModel):
    """Agent 配置模型"""

    id: str
    name: str
    description: str = ""
    system_prompt: str = "你是一个有帮助的AI助手。请用中文回答用户的问题，保持友好和专业。"
    model: str = "main"  # main/summary/memory 或具体模型名
    temperature: float = 0.7
    max_tokens: int = 0  # 0 表示不限制
    use_memory: bool = True
    use_tools: bool = True
    memory_scene: str = "chat"  # chat/task/first_interaction
    decay_model: str = "exponential"  # exponential/ebbinghaus
    vision_enabled: bool = False
    is_default: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentCreateRequest(BaseModel):
    """创建 Agent 请求"""

    name: str
    description: str = ""
    system_prompt: str = "你是一个有帮助的AI助手。"
    model: str = "main"
    temperature: float = 0.7
    max_tokens: int = 0  # 0 表示不限制
    use_memory: bool = True
    use_tools: bool = True
    memory_scene: str = "chat"
    decay_model: str = "exponential"
    vision_enabled: bool = False


class AgentUpdateRequest(BaseModel):
    """更新 Agent 请求"""

    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    use_memory: Optional[bool] = None
    use_tools: Optional[bool] = None
    memory_scene: Optional[str] = None
    decay_model: Optional[str] = None
    vision_enabled: Optional[bool] = None


def _ensure_data_dir():
    """确保数据目录存在"""
    os.makedirs(os.path.dirname(AGENTS_CONFIG_PATH), exist_ok=True)


def _load_agents() -> List[dict]:
    """加载所有 Agent 配置（带缓存）"""
    cached = agent_config_cache.get("all_agents")
    if cached is not None:
        return cached
    
    _ensure_data_dir()
    if not os.path.exists(AGENTS_CONFIG_PATH):
        now = datetime.now().isoformat()

        default_agent = {
            "id": "default",
            "name": "默认助手",
            "description": "通用AI助手，支持数学计算、记忆管理、提醒设置等多种工具（128k上下文）",
            "system_prompt": "你是一个有帮助的AI助手。请用中文回答用户的问题，保持友好和专业。当用户分享重要信息时，主动记住；当用户询问之前的内容时，主动搜索回忆。",
            "model": "main",
            "temperature": 0.7,
            "max_tokens": 4096,
            "use_memory": True,
            "use_tools": True,
            "memory_scene": "chat",
            "decay_model": "exponential",
            "vision_enabled": False,
            "is_default": True,
            "created_at": now,
            "updated_at": now,
        }

        memory_agent = {
            "id": "memory-agent",
            "name": "记忆管理助手",
            "description": "专业的记忆管理助手，可以通过自然语言管理记忆库（128k上下文）",
            "system_prompt": "你是记忆管理助手，专门负责帮助用户管理和维护记忆库。请用中文回答用户的问题，主动使用工具完成记忆管理操作。执行删除、合并等不可逆操作前，先向用户确认。",
            "model": "memory",
            "temperature": 0.3,
            "max_tokens": 4096,
            "use_memory": False,
            "use_tools": True,
            "memory_scene": "task",
            "decay_model": "exponential",
            "vision_enabled": False,
            "is_default": False,
            "created_at": now,
            "updated_at": now,
        }

        _save_agents([default_agent, memory_agent])
        agent_config_cache.set("all_agents", [default_agent, memory_agent])
        return [default_agent, memory_agent]

    try:
        with open(AGENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
            agents = json.load(f)
            agent_config_cache.set("all_agents", agents)
            return agents
    except Exception as e:
        logger.error(f"加载Agent配置失败: {e}", exc_info=True)
        return []


def _save_agents(agents: List[dict]):
    """保存所有 Agent 配置"""
    _ensure_data_dir()
    with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)
    agent_config_cache.delete("all_agents")


def _generate_agent_id() -> str:
    """生成 Agent ID"""
    import uuid

    return f"agent-{uuid.uuid4().hex[:8]}"


@router.get(
    "/agents",
    summary="获取所有 Agent",
    description="获取系统中所有 Agent 的配置列表，包括默认 Agent 和自定义 Agent。",
    response_description="返回 Agent 列表和总数",
)
async def list_agents():
    """获取所有 Agent
    
    Returns:
        dict: 包含 status, agents 列表和 total 总数
    """
    try:
        agents = _load_agents()
        return {"status": "success", "agents": agents, "total": len(agents)}
    except Exception as e:
        logger.error(f"获取Agent列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post(
    "/agents",
    summary="创建新 Agent",
    description="创建一个新的自定义 Agent，可以配置模型、系统提示、记忆和工具使用等参数。",
    response_description="返回创建的 Agent 配置",
)
async def create_agent(request: AgentCreateRequest):
    """创建新 Agent
    
    Args:
        request: Agent 创建请求，包含名称、描述、系统提示等配置
        
    Returns:
        dict: 包含 status 和新创建的 agent 配置
    """
    try:
        agents = _load_agents()

        # 检查名称是否重复
        if any(a["name"] == request.name for a in agents):
            raise HTTPException(status_code=400, detail=f"Agent 名称 '{request.name}' 已存在")

        now = datetime.now().isoformat()

        # 处理空模型字符串 - 空字符串表示使用默认模型
        model = request.model if request.model and request.model.strip() else "main"

        new_agent = {
            "id": _generate_agent_id(),
            "name": request.name,
            "description": request.description,
            "system_prompt": request.system_prompt,
            "model": model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "use_memory": request.use_memory,
            "use_tools": request.use_tools,
            "memory_scene": request.memory_scene,
            "decay_model": request.decay_model,
            "vision_enabled": request.vision_enabled if hasattr(request, 'vision_enabled') else False,
            "is_default": False,
            "created_at": now,
            "updated_at": now,
        }

        agents.append(new_agent)
        _save_agents(agents)

        return {"status": "success", "agent": new_agent, "message": "Agent 创建成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建Agent失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get(
    "/agents/default",
    summary="获取默认 Agent",
    description="获取系统中标记为 is_default 的 Agent 配置。",
)
async def get_default_agent():
    """获取默认 Agent 配置。

    对齐 public/interface_stub/agent_service.pyi 的 get_default_agent() 契约。
    优先返回 is_default=True 的 Agent；若无则回退到 id="default"；
    均无则抛 404。

    Returns:
        dict: 包含 status 和 default agent 配置
    """
    try:
        agents = _load_agents()
        # 优先 is_default=True
        default_agent = next((a for a in agents if a.get("is_default", False)), None)
        # 回退到 id="default"
        if default_agent is None:
            default_agent = next((a for a in agents if a.get("id") == "default"), None)

        if not default_agent:
            raise HTTPException(status_code=404, detail="未配置默认 Agent")

        return {"status": "success", "agent": default_agent}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取默认Agent失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """获取单个 Agent"""
    try:
        agents = _load_agents()
        agent = next((a for a in agents if a["id"] == agent_id), None)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

        return {"status": "success", "agent": agent}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取Agent失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, request: AgentUpdateRequest):
    """更新 Agent"""
    try:
        agents = _load_agents()
        agent_index = next((i for i, a in enumerate(agents) if a["id"] == agent_id), None)

        if agent_index is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

        agent = agents[agent_index]

        # 更新字段
        update_data = request.dict(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                # B4: 空模型字符串（含纯空白）回退到默认模型 "main"
                # 旧逻辑 `value and not value.strip()` 在 value="" 时短路为 False，导致空字符串不回退
                if key == "model" and isinstance(value, str) and not value.strip():
                    value = "main"
                agent[key] = value

        agent["updated_at"] = datetime.now().isoformat()
        _save_agents(agents)

        return {"status": "success", "agent": agent, "message": "Agent 更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新Agent失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


def _cleanup_agent_graph_db(agent_id: str) -> None:
    """清理指定助手的图数据库实例及 db 文件。"""
    # 从注册表移除并关闭实例
    try:
        from backend.dependencies import remove_graph_database
        remove_graph_database(agent_id)
    except Exception as e:
        logger.warning(f"清理图数据库实例失败 (agent_id={agent_id}): {e}")

    # 删除 per-agent db 文件
    try:
        from backend.core.graph.config import get_graph_config
        db_path = get_graph_config(agent_id=agent_id).database_path
        if db_path and os.path.exists(db_path):
            os.remove(db_path)
            logger.info(f"已删除图数据库文件: {db_path}")
    except Exception as e:
        logger.warning(f"删除图数据库文件失败 (agent_id={agent_id}): {e}")


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除 Agent"""
    try:
        agents = _load_agents()
        agent = next((a for a in agents if a["id"] == agent_id), None)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

        if agent.get("is_default", False):
            raise HTTPException(status_code=400, detail="不能删除默认 Agent")

        agents = [a for a in agents if a["id"] != agent_id]
        _save_agents(agents)

        # 清理该助手的图数据库实例及文件
        _cleanup_agent_graph_db(agent_id)

        return {"status": "success", "message": f"Agent '{agent_id}' 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除Agent失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/agents/{agent_id}/clone")
async def clone_agent(agent_id: str):
    """克隆 Agent"""
    try:
        agents = _load_agents()
        source_agent = next((a for a in agents if a["id"] == agent_id), None)

        if not source_agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

        now = datetime.now().isoformat()
        new_agent = {
            **source_agent,
            "id": _generate_agent_id(),
            "name": f"{source_agent['name']} (副本)",
            "is_default": False,
            "created_at": now,
            "updated_at": now,
        }

        agents.append(new_agent)
        _save_agents(agents)

        return {"status": "success", "agent": new_agent, "message": "Agent 克隆成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"克隆Agent失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/agents/{agent_id}/stats")
async def get_agent_stats(agent_id: str):
    """获取 Agent 统计信息"""
    from backend.dependencies import get_context_manager

    try:
        agents = _load_agents()
        agent = next((a for a in agents if a["id"] == agent_id), None)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

        context_mgr = get_context_manager()
        # 获取使用该 Agent 的会话数量
        sessions = context_mgr.list_sessions()
        agent_sessions = [s for s in sessions if s.get("id", "").startswith(f"agent-{agent_id}")]

        return {
            "status": "success",
            "agent_id": agent_id,
            "session_count": len(agent_sessions),
            "total_messages": sum(s.get("message_count", 0) for s in agent_sessions),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取Agent统计失败: {str(e)}")


@router.get("/agents/{agent_id}/context")
async def get_agent_context(agent_id: str, limit: int = 20):
    """获取Agent上下文

    Args:
        agent_id: Agent唯一标识
        limit: 返回的最大消息数量
    """
    from backend.dependencies import get_context_manager

    try:
        agents = _load_agents()
        agent = next((a for a in agents if a["id"] == agent_id), None)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

        context_mgr = get_context_manager()
        summary = context_mgr.get_context_summary(agent_id)
        messages = context_mgr.get_message_history(agent_id, limit=limit)

        return {
            "status": "success",
            "agent_id": agent_id,
            "has_context": summary.get("has_context", False),
            "session_id": summary.get("session_id"),
            "last_active": summary.get("last_active"),
            "created_at": summary.get("created_at"),
            "updated_at": summary.get("updated_at"),
            "total_messages": summary.get("total_messages", 0),
            "role_counts": summary.get("role_counts", {}),
            "recent_messages": messages,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取Agent上下文失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取Agent上下文失败: {str(e)}")


@router.delete("/agents/{agent_id}/context")
async def clear_agent_context(agent_id: str):
    """清空Agent上下文

    Args:
        agent_id: Agent唯一标识
    """
    from backend.dependencies import get_context_manager

    try:
        agents = _load_agents()
        agent = next((a for a in agents if a["id"] == agent_id), None)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

        context_mgr = get_context_manager()
        context_mgr.clear_context(agent_id)

        return {"status": "success", "message": f"Agent '{agent_id}' 的上下文已清空"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清空Agent上下文失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"清空Agent上下文失败: {str(e)}")
