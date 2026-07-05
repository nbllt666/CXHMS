"""AgentService 接口契约存根。

对应 backend/api/routers/agents.py 的路由与 data/agents.json 持久化。
零实现逻辑，仅声明签名。模块实现必须严格匹配本存根。

@version 1.0.0
@see public/schema/agent.json
"""

from typing import Any, Dict, List, Optional


class AgentService:
    """Agent 服务接口。

    提供 Agent 配置的 CRUD 与查询能力。Agent 数据必须符合 public/schema/agent.json。
    """

    async def list_agents(self) -> List[Dict[str, Any]]:
        """列出全部 Agent 配置。

        Raises:
            DatabaseError: 读取配置文件失败
        """
        ...

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """获取单个 Agent 配置。

        Raises:
            AgentNotFoundError: agent_id 不存在
            DatabaseError: 读取失败
        """
        ...

    async def create_agent(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """创建 Agent，返回 {status, agent, message}。

        Raises:
            ValidationError: 名称重复或字段非法
            DatabaseError: 持久化失败
        """
        ...

    async def update_agent(self, agent_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """更新 Agent 配置，返回 {status, agent, message}。

        Raises:
            AgentNotFoundError: agent_id 不存在
            ValidationError: 字段非法
            DatabaseError: 持久化失败
        """
        ...

    async def delete_agent(self, agent_id: str) -> Dict[str, Any]:
        """删除 Agent。默认 Agent 不可删除。

        Raises:
            AgentNotFoundError: agent_id 不存在
            ValidationError: 试图删除默认 Agent
            DatabaseError: 持久化失败
        """
        ...

    async def get_default_agent(self) -> Dict[str, Any]:
        """获取默认 Agent 配置。

        Raises:
            DatabaseError: 无默认 Agent
        """
        ...
