"""
Agent 管理路由
提供 Agent 的 CRUD 操作
"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json
import os

router = APIRouter()

# Agent 配置文件路径
AGENTS_CONFIG_PATH = "data/agents.json"


class AgentConfig(BaseModel):
    """Agent 配置模型"""
    id: str
    name: str
    description: str = ""
    system_prompt: str = "你是一个有帮助的AI助手。"
    model: str = "main"  # main/summary/memory 或具体模型名
    temperature: float = 0.7
    max_tokens: int = 4096
    use_memory: bool = True
    use_tools: bool = True
    memory_scene: str = "chat"  # chat/task/first_interaction
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
    max_tokens: int = 4096
    use_memory: bool = True
    use_tools: bool = True
    memory_scene: str = "chat"


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


def _ensure_data_dir():
    """确保数据目录存在"""
    os.makedirs(os.path.dirname(AGENTS_CONFIG_PATH), exist_ok=True)


def _load_agents() -> List[dict]:
    """加载所有 Agent 配置"""
    _ensure_data_dir()
    if not os.path.exists(AGENTS_CONFIG_PATH):
        # 创建默认 Agent
        default_agent = {
            "id": "default",
            "name": "默认助手",
            "description": "通用AI助手",
            "system_prompt": "你是一个有帮助的AI助手。请用中文回答用户的问题。",
            "model": "main",
            "temperature": 0.7,
            "max_tokens": 4096,
            "use_memory": True,
            "use_tools": True,
            "memory_scene": "chat",
            "is_default": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        _save_agents([default_agent])
        return [default_agent]
    
    try:
        with open(AGENTS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_agents(agents: List[dict]):
    """保存所有 Agent 配置"""
    _ensure_data_dir()
    with open(AGENTS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)


def _generate_agent_id() -> str:
    """生成 Agent ID"""
    import uuid
    return f"agent-{uuid.uuid4().hex[:8]}"


@router.get("/agents", response_model=List[AgentConfig])
async def get_agents():
    """获取所有 Agent"""
    agents = _load_agents()
    return agents


@router.post("/agents", response_model=AgentConfig)
async def create_agent(request: AgentCreateRequest):
    """创建新 Agent"""
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
        "is_default": False,
        "created_at": now,
        "updated_at": now
    }
    
    agents.append(new_agent)
    _save_agents(agents)
    
    return new_agent


@router.get("/agents/{agent_id}", response_model=AgentConfig)
async def get_agent(agent_id: str):
    """获取单个 Agent"""
    agents = _load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")
    
    return agent


@router.put("/agents/{agent_id}", response_model=AgentConfig)
async def update_agent(agent_id: str, request: AgentUpdateRequest):
    """更新 Agent"""
    agents = _load_agents()
    agent_index = next((i for i, a in enumerate(agents) if a["id"] == agent_id), None)
    
    if agent_index is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")
    
    agent = agents[agent_index]
    
    # 更新字段
    update_data = request.dict(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            # 处理空模型字符串 - 空字符串表示使用默认模型
            if key == "model" and value and isinstance(value, str) and not value.strip():
                value = "main"
            agent[key] = value
    
    agent["updated_at"] = datetime.now().isoformat()
    _save_agents(agents)
    
    return agent


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除 Agent"""
    agents = _load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")
    
    if agent.get("is_default", False):
        raise HTTPException(status_code=400, detail="不能删除默认 Agent")
    
    agents = [a for a in agents if a["id"] != agent_id]
    _save_agents(agents)
    
    return {"status": "success", "message": f"Agent '{agent_id}' 已删除"}


@router.post("/agents/{agent_id}/clone", response_model=AgentConfig)
async def clone_agent(agent_id: str):
    """克隆 Agent"""
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
        "updated_at": now
    }
    
    agents.append(new_agent)
    _save_agents(agents)
    
    return new_agent


@router.get("/agents/{agent_id}/stats")
async def get_agent_stats(agent_id: str):
    """获取 Agent 统计信息"""
    from backend.api.app import get_context_manager
    
    agents = _load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")
    
    try:
        context_mgr = get_context_manager()
        # 获取使用该 Agent 的会话数量
        sessions = context_mgr.list_sessions()
        agent_sessions = [s for s in sessions if s.get("agent_id") == agent_id]
        
        return {
            "agent_id": agent_id,
            "session_count": len(agent_sessions),
            "total_messages": sum(s.get("message_count", 0) for s in agent_sessions)
        }
    except Exception as e:
        return {
            "agent_id": agent_id,
            "session_count": 0,
            "total_messages": 0,
            "error": str(e)
        }
