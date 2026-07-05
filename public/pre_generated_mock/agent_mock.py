"""AgentService 预生成 Mock。

实现 public/interface_stub/agent_service.pyi 的全部签名，
返回符合 public/schema/agent.json 契约的模拟值。
"""

from datetime import datetime
from typing import Any, Dict, List


def _iso_now() -> str:
    return datetime.now().isoformat()


def _default_agents() -> List[Dict[str, Any]]:
    return [
        {
            "id": "default",
            "name": "默认助手",
            "description": "通用AI助手",
            "system_prompt": "你是一个有帮助的AI助手。",
            "model": "main",
            "temperature": 0.7,
            "max_tokens": 0,
            "use_memory": True,
            "use_tools": True,
            "memory_scene": "chat",
            "decay_model": "exponential",
            "vision_enabled": False,
            "is_default": True,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
        }
    ]


class MockAgentService:
    """AgentService 的 Mock 实现。内存态。"""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {a["id"]: dict(a) for a in _default_agents()}

    async def list_agents(self) -> List[Dict[str, Any]]:
        return [dict(a) for a in self._store.values()]

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        if agent_id not in self._store:
            raise KeyError(f"Agent not found: {agent_id}")
        return dict(self._store[agent_id])

    async def create_agent(self, request: Dict[str, Any]) -> Dict[str, Any]:
        aid = request.get("id") or f"agent-{len(self._store)}"
        if aid in self._store:
            raise ValueError(f"Agent 已存在: {aid}")
        agent = {
            "id": aid,
            "name": request["name"],
            "description": request.get("description", ""),
            "system_prompt": request.get("system_prompt", "你是一个有帮助的AI助手。"),
            "model": request.get("model", "main"),
            "temperature": request.get("temperature", 0.7),
            "max_tokens": request.get("max_tokens", 0),
            "use_memory": request.get("use_memory", True),
            "use_tools": request.get("use_tools", True),
            "memory_scene": request.get("memory_scene", "chat"),
            "decay_model": request.get("decay_model", "exponential"),
            "vision_enabled": request.get("vision_enabled", False),
            "is_default": False,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
        }
        self._store[aid] = agent
        return {"status": "success", "agent": agent, "message": "Agent 创建成功"}

    async def update_agent(self, agent_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        if agent_id not in self._store:
            raise KeyError(f"Agent not found: {agent_id}")
        agent = self._store[agent_id]
        for k, v in request.items():
            if v is not None:
                agent[k] = v
        agent["updated_at"] = _iso_now()
        return {"status": "success", "agent": dict(agent), "message": "Agent 更新成功"}

    async def delete_agent(self, agent_id: str) -> Dict[str, Any]:
        if agent_id not in self._store:
            raise KeyError(f"Agent not found: {agent_id}")
        if self._store[agent_id].get("is_default"):
            raise ValueError("默认 Agent 不可删除")
        del self._store[agent_id]
        return {"status": "success", "message": "Agent 删除成功"}

    async def get_default_agent(self) -> Dict[str, Any]:
        for a in self._store.values():
            if a.get("is_default"):
                return dict(a)
        raise KeyError("无默认 Agent")
