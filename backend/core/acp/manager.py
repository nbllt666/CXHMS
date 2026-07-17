import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from backend.core.exceptions import ACPError
from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


# ACP 自动回复专用提示词——替换通用 MAIN_HIDDEN_SYSTEM_PROMPT，避免压制角色设定
# 强制要求使用 acp_send_message 工具回复，形成真正的 agent-to-agent 互动链路
ACP_REPLY_HINT_PROMPT = """<acp_context>
你收到了来自其他 Agent 的 ACP（Agent Communication Protocol）消息。请严格保持你的角色设定和语气风格。

<reply_rule>
**通常应使用 acp_send_message 工具回复对方 Agent，禁止直接在文本中写出回复内容。**

工具调用方式：
- 工具名：acp_send_message
- 参数：
  - agent_id：对方 Agent 的 ID（即消息发送方 from_agent_id）
  - message：你的回复内容（以你的角色身份和语气风格撰写）

示例：若收到来自 agent-xxx 的消息，应调用 acp_send_message(agent_id="agent-xxx", message="你的回复")

调用工具后，可以附加简短的内心独白或动作描写（如角色卡风格），但主要对话内容必须通过工具发送。

**允许不回复的情况**：如果对话已自然结束（如对方说了告别语、对话已无实质内容可回应、继续回复只会形成无意义的循环），你可以选择不调用工具，仅输出一句简短的内心独白即可，不需要强制回复。判断标准：这条消息是否真正需要你的回应？如果不需要，沉默也是一种回答。
</reply_rule>

<behavior>
1. 以你的角色身份回应对方 Agent，保持角色的语言习惯、性格特征
2. 不要以"通用 AI 助手"或"智能助手"自居——你是你，不是万能助手
3. 若需要查询其他 Agent，可调用 acp_list_agents 工具
4. 其他工具（如记忆、搜索）按需调用，但不要主动执行无关操作
5. 回复应自然、有对话感，避免机械的"我随时准备协助您"式套话
6. 避免无意义的循环回复——如果对话已经结束，不要为了回复而回复
</behavior>
</acp_context>"""


@dataclass
class ACPAgentInfo:
    id: str = ""
    name: str = ""
    host: str = ""
    port: int = 0
    status: str = "offline"
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    last_seen: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "status": self.status,
            "version": self.version,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
        }


@dataclass
class ACPConnectionInfo:
    id: str = ""
    local_agent_id: str = ""
    remote_agent_id: str = ""
    remote_agent_name: str = ""
    host: str = ""
    port: int = 0
    status: str = "disconnected"
    connected_at: Optional[str] = None
    last_activity: Optional[str] = None
    messages_sent: int = 0
    messages_received: int = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "local_agent_id": self.local_agent_id,
            "remote_agent_id": self.remote_agent_id,
            "remote_agent_name": self.remote_agent_name,
            "host": self.host,
            "port": self.port,
            "status": self.status,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "metadata": self.metadata,
        }


@dataclass
class ACPGroupInfo:
    id: str = ""
    name: str = ""
    description: str = ""
    creator_id: str = ""
    creator_name: str = ""
    members: List[Dict] = field(default_factory=list)
    max_members: int = 50
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "members": self.members,
            "max_members": self.max_members,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class ACPMessageInfo:
    id: str = ""
    msg_type: str = "chat"
    from_agent_id: str = ""
    from_agent_name: str = ""
    to_agent_id: Optional[str] = None
    to_group_id: Optional[str] = None
    content: Dict = field(default_factory=dict)
    timestamp: str = ""
    is_read: bool = False
    is_sent: bool = False
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.msg_type,
            "from_agent_id": self.from_agent_id,
            "from_agent_name": self.from_agent_name,
            "to_agent_id": self.to_agent_id,
            "to_group_id": self.to_group_id,
            "content": self.content,
            "timestamp": self.timestamp,
            "is_read": self.is_read,
            "is_sent": self.is_sent,
            "metadata": self.metadata,
        }


class ACPManager:
    """ACP管理器

    负责管理Agents、连接、群组和消息

    Attributes:
        data_dir: 数据目录路径
        agents: Agent字典
        connections: 连接字典
        groups: 群组字典
        messages: 消息字典
        _local_agent_id: 本地Agent ID
        _local_agent_name: 本地Agent名称
    """

    def __init__(self, data_dir: str = "data/acp") -> None:
        """初始化ACP管理器

        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.agents: Dict[str, ACPAgentInfo] = {}
        self.connections: Dict[str, ACPConnectionInfo] = {}
        self.groups: Dict[str, ACPGroupInfo] = {}
        self.messages: Dict[str, List[ACPMessageInfo]] = {}

        self._lock = asyncio.Lock()

        self._local_agent_id = ""
        self._local_agent_name = ""

        self._discovery_task = None
        self._broadcast_task = None
        self._heartbeat_task = None
        self._discovery = None

        # 本地 HTTP 端口（供 BEACON 暴露给其他节点，由 start() 从 settings 注入）
        self._local_http_port: int = 8001

        self._load_data()

    @property
    def local_http_port(self) -> int:
        """本地 HTTP 端口，供 BEACON 暴露给其他节点用于回送 HTTP 消息"""
        return self._local_http_port

    def initialize(self, agent_id: str, agent_name: str) -> None:
        """初始化本地Agent信息

        Args:
            agent_id: Agent ID
            agent_name: Agent名称
        """
        self._local_agent_id = agent_id
        self._local_agent_name = agent_name
        logger.info(f"ACP管理器初始化: agent_id={agent_id}, agent_name={agent_name}")

    async def start(self) -> None:
        """启动ACP管理器"""
        self._load_data()
        self._register_local_cxhms_agents()

        from backend.core.acp.discover import ACPLanDiscovery
        from config.settings import settings

        # 注入本地 HTTP 端口，供 BEACON 暴露给其他节点
        try:
            self._local_http_port = int(settings.config.server.port)
        except Exception:
            self._local_http_port = 8001

        if settings.config.acp.discovery.enabled:
            self._discovery = ACPLanDiscovery(
                acp_manager=self,
                broadcast_port=settings.config.acp.discovery.broadcast_port,
                discovery_port=settings.config.acp.discovery.discovery_port,
                broadcast_address=settings.config.acp.discovery.broadcast_address,
                interval=settings.config.acp.discovery.interval,
            )
            await self._discovery.start()
            logger.info("ACP Discovery服务已启动")

        logger.info("ACP管理器已启动")

    async def stop(self) -> None:
        """停止ACP管理器"""
        if self._discovery:
            await self._discovery.stop()
            logger.info("ACP Discovery服务已停止")

        await self._save_data()
        logger.info("ACP管理器已停止")

    def _register_local_cxhms_agents(self):
        """将 CXHMS 本地 agent 注册到 ACP 网络，实现同实例 agent 互通。

        从 data/agents.json 加载 CXHMS agent，注册到 self.agents 字典。
        本地 agent 标记为 host="127.0.0.1", port=0，不通过 HTTP 投递消息，
        消息只存储在本地 self.messages 字典中。
        """
        import json
        import os

        # 1. 注册主系统 agent（_local_agent_id）到 ACP 网络
        #    主系统 agent 在 ACP 网络中的身份是 _local_agent_id（如 cxhms-agent-001），
        #    与前端默认助手 agent_id（"default"）不同。注册后 send_message 能找到 target，
        #    _deliver_to_local_agent 会将其映射到 "agent-default" session。
        if self._local_agent_id and self._local_agent_id not in self.agents:
            self.agents[self._local_agent_id] = ACPAgentInfo(
                id=self._local_agent_id,
                name=self._local_agent_name or self._local_agent_id,
                host="127.0.0.1",
                port=0,
                status="online",
                version="1.0.0",
                capabilities=["chat"],
                last_seen=datetime.now().isoformat(),
                metadata={"source": "cxhms_main"},
            )
            logger.info(
                f"已注册主系统 Agent 到 ACP 网络: {self._local_agent_id} ({self._local_agent_name})"
            )

        # 2. 从 data/agents.json 加载用户创建的角色卡 agent
        agents_file = os.path.join("data", "agents.json")
        if not os.path.exists(agents_file):
            return

        try:
            with open(agents_file, "r", encoding="utf-8") as f:
                cxhms_agents = json.load(f)

            count = 0
            for agent_data in cxhms_agents:
                agent_id = agent_data.get("id", "")
                if not agent_id:
                    continue
                # 跳过已存在的外部 agent（不覆盖外部发现的 agent）
                if agent_id in self.agents:
                    existing = self.agents[agent_id]
                    if existing.metadata.get("source") != "cxhms_local":
                        continue

                self.agents[agent_id] = ACPAgentInfo(
                    id=agent_id,
                    name=agent_data.get("name", agent_id),
                    host="127.0.0.1",
                    port=0,
                    status="online",
                    version="1.0.0",
                    capabilities=["chat"],
                    last_seen=datetime.now().isoformat(),
                    metadata={"source": "cxhms_local"},
                )
                count += 1

            if count:
                logger.info(f"已注册 {count} 个 CXHMS 本地 Agent 到 ACP 网络")
        except Exception as e:
            logger.warning(f"注册 CXHMS 本地 Agent 失败: {e}")

    def _load_data(self):
        agents_file = self.data_dir / "agents.yaml"
        connections_file = self.data_dir / "connections.yaml"
        groups_file = self.data_dir / "groups.yaml"

        if agents_file.exists():
            try:
                import yaml

                with open(agents_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    for agent_data in data.get("agents", []):
                        agent = ACPAgentInfo(**agent_data)
                        self.agents[agent.id] = agent
            except Exception as e:
                logger.warning(f"加载Agents失败: {e}")

        if connections_file.exists():
            try:
                import yaml

                with open(connections_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    for conn_data in data.get("connections", []):
                        conn = ACPConnectionInfo(**conn_data)
                        self.connections[conn.id] = conn
            except Exception as e:
                logger.warning(f"加载Connections失败: {e}")

        if groups_file.exists():
            try:
                import yaml

                with open(groups_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    for group_data in data.get("groups", []):
                        group = ACPGroupInfo(**group_data)
                        self.groups[group.id] = group
            except Exception as e:
                logger.warning(f"加载Groups失败: {e}")

        logger.info(
            f"ACP数据加载完成: agents={len(self.agents)}, connections={len(self.connections)}, groups={len(self.groups)}"
        )

    def _save_data_sync(self):
        import yaml

        agents_file = self.data_dir / "agents.yaml"
        connections_file = self.data_dir / "connections.yaml"
        groups_file = self.data_dir / "groups.yaml"

        with open(agents_file, "w", encoding="utf-8") as f:
            # 排除 CXHMS 本地 agent（由 _register_local_cxhms_agents 动态注册，不持久化）
            external_agents = [
                a.to_dict()
                for a in self.agents.values()
                if a.metadata.get("source") != "cxhms_local"
            ]
            yaml.dump({"agents": external_agents}, f, allow_unicode=True)

        with open(connections_file, "w", encoding="utf-8") as f:
            yaml.dump(
                {"connections": [c.to_dict() for c in self.connections.values()]},
                f,
                allow_unicode=True,
            )

        with open(groups_file, "w", encoding="utf-8") as f:
            yaml.dump(
                {"groups": [g.to_dict() for g in self.groups.values()]}, f, allow_unicode=True
            )

        logger.info("ACP数据已保存")

    async def _save_data(self):
        await asyncio.to_thread(self._save_data_sync)

    async def register_agent(self, agent: ACPAgentInfo) -> ACPAgentInfo:
        async with self._lock:
            agent.last_seen = datetime.now().isoformat()
            self.agents[agent.id] = agent
            await self._save_data()
            return agent

    async def update_agent_status(self, agent_id: str, status: str) -> bool:
        async with self._lock:
            if agent_id in self.agents:
                self.agents[agent_id].status = status
                self.agents[agent_id].last_seen = datetime.now().isoformat()
                await self._save_data()
                return True
            return False

    async def get_agent(self, agent_id: str) -> Optional[ACPAgentInfo]:
        return self.agents.get(agent_id)

    async def list_agents(self, online_only: bool = False) -> List[Dict]:
        async with self._lock:
            agents = list(self.agents.values())
            if online_only:
                agents = [a for a in agents if a.status == "online"]
            return [a.to_dict() for a in agents]

    async def remove_agent(self, agent_id: str) -> bool:
        async with self._lock:
            if agent_id in self.agents:
                del self.agents[agent_id]
                await self._save_data()
                return True
            return False

    async def create_connection(self, connection: ACPConnectionInfo) -> ACPConnectionInfo:
        async with self._lock:
            self.connections[connection.id] = connection
            await self._save_data()
            return connection

    async def get_connection(self, connection_id: str) -> Optional[ACPConnectionInfo]:
        return self.connections.get(connection_id)

    async def list_connections(self, local_only: bool = True) -> List[Dict]:
        async with self._lock:
            connections = list(self.connections.values())
            if local_only:
                connections = [c for c in connections if c.local_agent_id == self._local_agent_id]
            return [c.to_dict() for c in connections]

    async def update_connection(self, connection_id: str, **kwargs) -> bool:
        async with self._lock:
            if connection_id in self.connections:
                conn = self.connections[connection_id]
                for key, value in kwargs.items():
                    if hasattr(conn, key):
                        setattr(conn, key, value)
                await self._save_data()
                return True
            return False

    async def delete_connection(self, connection_id: str) -> bool:
        async with self._lock:
            if connection_id in self.connections:
                del self.connections[connection_id]
                await self._save_data()
                return True
            return False

    async def create_group(self, group: ACPGroupInfo) -> ACPGroupInfo:
        async with self._lock:
            self.groups[group.id] = group
            self.messages[group.id] = []
            await self._save_data()
            return group

    async def get_group(self, group_id: str) -> Optional[ACPGroupInfo]:
        return self.groups.get(group_id)

    async def list_groups(self) -> List[Dict]:
        async with self._lock:
            return [g.to_dict() for g in self.groups.values()]

    async def update_group(self, group_id: str, **kwargs) -> bool:
        async with self._lock:
            if group_id in self.groups:
                group = self.groups[group_id]
                for key, value in kwargs.items():
                    if hasattr(group, key):
                        setattr(group, key, value)
                group.updated_at = datetime.now().isoformat()
                await self._save_data()
                return True
            return False

    async def delete_group(self, group_id: str) -> bool:
        async with self._lock:
            if group_id in self.groups:
                del self.groups[group_id]
                if group_id in self.messages:
                    del self.messages[group_id]
                await self._save_data()
                return True
            return False

    async def add_group_member(self, group_id: str, member: Dict) -> bool:
        async with self._lock:
            if group_id in self.groups:
                group = self.groups[group_id]
                group.members.append(member)
                group.updated_at = datetime.now().isoformat()
                await self._save_data()
                return True
            return False

    async def remove_group_member(self, group_id: str, agent_id: str) -> bool:
        async with self._lock:
            if group_id in self.groups:
                group = self.groups[group_id]
                group.members = [m for m in group.members if m.get("agent_id") != agent_id]
                group.updated_at = datetime.now().isoformat()
                await self._save_data()
                return True
            return False

    async def send_message(self, message: ACPMessageInfo) -> ACPMessageInfo:
        async with self._lock:
            if message.to_group_id:
                if message.to_group_id not in self.messages:
                    self.messages[message.to_group_id] = []
                self.messages[message.to_group_id].append(message)
            elif message.to_agent_id:
                agent_id = message.to_agent_id
                if agent_id not in self.messages:
                    self.messages[agent_id] = []
                self.messages[agent_id].append(message)

            await self._save_data()

        # 若目标 Agent 是外部 Agent（有 host:port 且 port 不是发现端口 9999），通过 HTTP 投递
        if message.to_agent_id and not message.to_group_id:
            target = self.agents.get(message.to_agent_id)
            if target and target.host and target.port and target.port != 9999:
                try:
                    await self._deliver_to_external_agent(target, message)
                except Exception as e:
                    logger.warning(
                        f"向外部 Agent {message.to_agent_id} 投递消息失败: {e}"
                    )
            elif (
                target
                and target.port == 0
                and target.metadata.get("source") in ("cxhms_local", "cxhms_main")
            ):
                # 本地 CXHMS agent：注入到目标 agent session 并触发自动回复
                try:
                    await self._deliver_to_local_agent(target, message)
                except Exception as e:
                    logger.warning(
                        f"向本地 Agent {message.to_agent_id} 投递消息失败: {e}"
                    )

        return message

    async def _deliver_to_local_agent(
        self, target: ACPAgentInfo, message: ACPMessageInfo
    ) -> None:
        """向本地 CXHMS agent 投递消息

        将 ACP 消息注入到目标 agent 的聊天 session（作为 user 消息），
        然后通过目标 agent 的配置和工具触发 LLM 自动回复。

        与 _deliver_to_external_agent 对称：外部 agent 走 HTTP，本地 agent 走内存。
        """
        # 主系统 agent 映射到前端 default session
        # 主系统在 ACP 网络中的身份是 _local_agent_id（如 cxhms-agent-001），
        # 但前端默认助手聊天用的是 agent_id="default"（session_id="agent-default"）。
        # 当 target 是主系统 agent 时，映射到 "default" 让消息注入和回复走默认助手配置。
        if target.id == self._local_agent_id:
            target_agent_id = "default"
        else:
            target_agent_id = target.id

        # 1. 将消息注入到目标 agent 的 session
        await self._inject_into_chat_context(message, target_agent_id=target_agent_id)

        # 2. 触发目标 agent 的自动回复（后台执行，不阻塞 send_message 返回）
        asyncio.create_task(
            self._trigger_auto_reply(message, target_agent_id=target_agent_id)
        )

        logger.info(
            f"消息已投递到本地 Agent: to={target_agent_id}, "
            f"from={message.from_agent_id}"
        )

    async def _deliver_to_external_agent(self, target: ACPAgentInfo, message: ACPMessageInfo) -> None:
        """通过 HTTP 向外部 Agent 投递消息"""
        import httpx

        url = f"http://{target.host}:{target.port}/acp/message"
        payload = {
            "id": message.id,
            "msg_type": message.msg_type,
            "from_agent_id": message.from_agent_id,
            "from_agent_name": message.from_agent_name,
            "to_agent_id": message.to_agent_id,
            "to_group_id": message.to_group_id,
            "content": message.content,
            "timestamp": message.timestamp,
            "metadata": message.metadata,
        }

        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 200 and resp.status_code < 300:
                logger.info(f"消息已投递到外部 Agent {target.id}@{target.host}:{target.port}")
            else:
                logger.warning(
                    f"外部 Agent {target.id} 返回非 2xx: {resp.status_code} {resp.text[:200]}"
                )

    async def receive_external_message(self, message: ACPMessageInfo) -> ACPMessageInfo:
        """接收外部 ACP Agent 发来的消息

        此方法供 /acp/receive 端点调用，将外部 Agent 通过 HTTP 投递的消息存入本地历史，
        并作为 system 消息注入到本地 Agent 的聊天上下文（session_id = agent-{local_agent_id}），
        让主系统前端以系统消息形式显示，LLM 在下次对话时也能看到。
        """
        async with self._lock:
            if message.from_agent_id and message.from_agent_id not in self.messages:
                self.messages[message.from_agent_id] = []
            self.messages[message.from_agent_id].append(message)
            await self._save_data()

        # 注入 system 消息到本地 Agent 聊天上下文
        try:
            await self._inject_into_chat_context(message)
        except Exception as e:
            logger.warning(f"注入 ACP 消息到聊天上下文失败: {e}")

        # 立即触发 LLM 自动回复（后台任务，不阻塞接收端点返回）
        asyncio.create_task(self._trigger_auto_reply(message))

        logger.info(
            f"接收外部消息: from={message.from_agent_id}, type={message.msg_type}"
        )
        return message

    async def _trigger_auto_reply(
        self, message: ACPMessageInfo, target_agent_id: str = None
    ) -> None:
        """通过正常聊天管线处理 ACP 消息，agent 可使用工具回复

        在 _inject_into_chat_context 之后调用。ACP 消息已作为 user 消息注入
        session，本方法通过 generate_chat_stream 走正常聊天管线（含工具调用循环），
        agent 可自行决定是否调用 acp_send_message 工具回复。

        前端可通过 session 历史看到完整过程（user 消息、assistant 回复、tool calls）。
        所有失败静默记录 warning，不影响主流程。

        Args:
            message: ACP 消息
            target_agent_id: 目标 agent ID。若提供（本地 agent 互通场景），
                使用该 agent 的配置和工具，session_id = agent-{target_agent_id}；
                否则保持原有行为，使用 default agent 配置。
        """
        if not self._local_agent_id and not target_agent_id:
            return

        try:
            from backend.dependencies import get_context_manager, get_model_router
            from backend.core.chat.stream import generate_chat_stream, ChatStreamState

            context_mgr = get_context_manager()
            model_router = get_model_router()

            # 获取目标 agent 配置和工具（延迟导入避免循环依赖）
            from backend.api.routers.chat import (
                _get_tools_for_agent,
                get_agent_config,
                get_llm_client_for_agent,
            )

            # 决定使用哪个 agent 的配置
            effective_agent_id = target_agent_id or "default"
            agent_config = get_agent_config(effective_agent_id) or {
                "system_prompt": "你是一个有帮助的AI助手。请用中文回答用户的问题，保持友好和专业。",
                "temperature": 0.7,
                "max_tokens": 4096,
                "enable_thinking": False,
            }

            # 根据 agent 配置获取 LLM 客户端
            llm = get_llm_client_for_agent(agent_config)
            if not llm:
                # 兜底：使用主模型客户端
                llm = model_router.get_client("main")

            if not llm:
                logger.warning(
                    f"ACP 自动回复失败: agent={effective_agent_id} 的 LLM 客户端不可用"
                )
                return

            tools = _get_tools_for_agent(effective_agent_id)

            # session_id：本地 agent 互通时用目标 agent 的 session；否则用 default session
            session_id = f"agent-{effective_agent_id}"

            # 构建消息列表：角色系统提示 + ACP 专用提示 + 历史（含 ACP user 消息）
            # 注意：不追加 MAIN_HIDDEN_SYSTEM_PROMPT（会压制角色设定），改用 ACP_REPLY_HINT_PROMPT
            messages: List[Dict[str, Any]] = []
            system_prompt = agent_config.get("system_prompt", "")
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "system", "content": ACP_REPLY_HINT_PROMPT})

            # 从 agent-default session 读取历史（使用 to_thread 避免同步阻塞）
            history = await asyncio.to_thread(
                context_mgr.get_messages, session_id, limit=50
            )
            for m in history:
                role = m.get("role")
                content = m.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

            if not messages:
                logger.warning("ACP 自动回复: 消息列表为空，跳过")
                return

            # 在消息列表末尾追加工具回复指令（LLM 最后看到的指令，最容易被遵循）
            # gemma4 使用文本格式 tool_call，需要明确指示生成工具调用标签
            # 注意：不再强制"必须"调用——允许 agent 在对话自然结束时选择不回复，避免循环
            messages.append({
                "role": "system",
                "content": (
                    f"<force_tool_reply>\n"
                    f"上面的消息来自其他 Agent（from_agent_id={message.from_agent_id}）。\n"
                    f"你应该调用 acp_send_message 工具回复对方，参数：\n"
                    f'- agent_id: "{message.from_agent_id}"\n'
                    f"- message: <你的回复内容，以你的角色身份和语气风格撰写>\n\n"
                    f"但如果对话已自然结束（对方说了告别语、继续回复只会形成无意义循环），"
                    f"你可以选择不调用工具，仅输出一句简短的内心独白即可。\n\n"
                    f"禁止直接在文本中写出回复内容——如需回复，必须通过 acp_send_message 工具发送。"
                    f"</force_tool_reply>"
                ),
            })

            logger.info(
                f"ACP 自动回复启动: from={message.from_agent_id}, "
                f"messages={len(messages)}, tools={len(tools)}, "
                f"tool_names={[t['function']['name'] for t in tools[:5]]}..."
            )

            # 设置当前工具调用上下文的 agent_id，让 acp_send_message 等工具
            # 能识别实际调用方 agent 身份（本地 agent 互通场景下使用目标 agent 身份）
            # 主系统默认助手（effective_agent_id == "default"）的 ACP 身份是 _local_agent_id，
            # 而非 "default"——这样 acp_send_message 工具中 current_agent_id == _local_agent_id，
            # 走 else 分支使用主系统身份作为 from_agent_id（保持原行为）
            from backend.core.tools.graph_tools import set_current_agent_id

            if effective_agent_id == "default":
                set_current_agent_id(self._local_agent_id)
            else:
                set_current_agent_id(effective_agent_id)

            # 通过 generate_chat_stream 走正常聊天管线（含工具调用循环）
            state = ChatStreamState()
            async for event in generate_chat_stream(
                llm=llm,
                messages=messages,
                agent_config=agent_config,
                tools=tools,
                session_id=session_id,
                state=state,
                is_background=True,
            ):
                # 消费事件（不 yield 到 SSE，仅等待完成）
                # 工具调用在 generate_chat_stream 内部处理
                pass

            reply_text = state.accumulated_response or "(无回复内容)"
            thinking = state.full_thinking or ""

            # 保存助手响应到目标 session
            reply_metadata = {
                "source": "acp_auto_reply",
                "acp_message_id": message.id,
                "from_agent_id": message.from_agent_id,
                "tool_calls": state.tool_calls if state.tool_calls else None,
            }
            await context_mgr.add_message_async(
                session_id=session_id,
                role="assistant",
                content=reply_text,
                content_type="acp_reply",
                metadata=reply_metadata,
            )

            # 外部消息场景：同时保存到本地系统 agent 的 ACP 协议级 session
            # 本地 agent 互通场景（target_agent_id 提供）：跳过此步骤
            if not target_agent_id and self._local_agent_id:
                acp_session_id = f"agent-{self._local_agent_id}"
                if context_mgr.get_session(acp_session_id) is None:
                    context_mgr.create_session(
                        workspace_id="agent-chats",
                        title=f"{self._local_agent_name} 的对话",
                        session_id=acp_session_id,
                        metadata={"agent_id": self._local_agent_id},
                    )
                await context_mgr.add_message_async(
                    session_id=acp_session_id,
                    role="assistant",
                    content=reply_text,
                    content_type="acp_reply",
                    metadata=reply_metadata,
                )

            tool_summary = ""
            if state.tool_calls:
                tool_names = [tc.get("name", "?") for tc in state.tool_calls]
                tool_summary = f", tools_called={tool_names}"

            logger.info(
                f"ACP 自动回复完成: from={message.from_agent_id}, "
                f"reply={reply_text[:100]}{tool_summary}"
            )

        except Exception as e:
            logger.warning(f"ACP 自动回复失败: {e}")

    async def _inject_into_chat_context(
        self, message: ACPMessageInfo, target_agent_id: str = None
    ) -> None:
        """将 ACP 消息作为 user 消息注入到本地 Agent 聊天上下文

        ACP 消息类似于用户消息——agent 收到后触发回复。因此注入为 user 角色，
        让 agent 通过正常聊天管线（含工具调用）处理。

        Args:
            message: ACP 消息
            target_agent_id: 目标 agent ID。若提供（本地 agent 互通场景），
                只注入到 agent-{target_agent_id} session；否则按原逻辑注入到
                agent-{local_agent_id} 和 agent-default 两个 session。

        若 session 不存在则先创建，确保前端能通过既有聊天接口拉到这条消息。
        """
        if not self._local_agent_id and not target_agent_id:
            return

        from backend.dependencies import get_context_manager

        context_mgr = get_context_manager()

        # 提取消息文本
        content_dict = message.content or {}
        if isinstance(content_dict, str):
            text = content_dict
        else:
            text = content_dict.get("text") or content_dict.get("message") or str(content_dict)

        from datetime import datetime as _dt

        user_content = (
            f"[ACP 消息] 来自 {message.from_agent_name or message.from_agent_id}: {text}"
        )

        msg_metadata = {
            "source": "acp_external" if not target_agent_id else "acp_local",
            "from_agent_id": message.from_agent_id,
            "from_agent_name": message.from_agent_name,
            "msg_type": message.msg_type,
            "acp_message_id": message.id,
            "timestamp": message.timestamp or _dt.now().isoformat(),
        }

        if target_agent_id:
            # 本地 agent 互通场景：只注入到目标 agent 的 session
            session_id = f"agent-{target_agent_id}"
            target_agent_name = target_agent_id
            # 查找 agent 名称
            target_info = self.agents.get(target_agent_id)
            if target_info:
                target_agent_name = target_info.name or target_agent_id
            if context_mgr.get_session(session_id) is None:
                context_mgr.create_session(
                    workspace_id="agent-chats",
                    title=f"{target_agent_name} 的对话",
                    session_id=session_id,
                    metadata={"agent_id": target_agent_id},
                )
            await context_mgr.add_message_async(
                session_id=session_id,
                role="user",
                content=user_content,
                content_type="acp_message",
                metadata=msg_metadata,
            )
            return

        # 外部消息场景：注入到 ACP 协议级 session
        session_id = f"agent-{self._local_agent_id}"
        if context_mgr.get_session(session_id) is None:
            context_mgr.create_session(
                workspace_id="agent-chats",
                title=f"{self._local_agent_name} 的对话",
                session_id=session_id,
                metadata={"agent_id": self._local_agent_id},
            )
        await context_mgr.add_message_async(
            session_id=session_id,
            role="user",
            content=user_content,
            content_type="acp_message",
            metadata=msg_metadata,
        )

        # 同时注入到前端默认助手 session（agent-default），确保前端可见
        default_session_id = "agent-default"
        if context_mgr.get_session(default_session_id) is None:
            context_mgr.create_session(
                workspace_id="agent-chats",
                title="默认助手的对话",
                session_id=default_session_id,
                metadata={"agent_id": "default"},
            )
        await context_mgr.add_message_async(
            session_id=default_session_id,
            role="user",
            content=user_content,
            content_type="acp_message",
            metadata=msg_metadata,
        )

    async def get_messages(
        self, target_id: str, group_id: str = None, limit: int = 50, unread_only: bool = False
    ) -> List[Dict]:
        async with self._lock:
            key = group_id or target_id
            messages = self.messages.get(key, [])

            if unread_only:
                messages = [m for m in messages if not m.is_read]

            return [m.to_dict() for m in messages[-limit:]]

    async def mark_messages_read(self, message_ids: List[str]) -> int:
        marked = 0
        async with self._lock:
            for messages in self.messages.values():
                for msg in messages:
                    if msg.id in message_ids and not msg.is_read:
                        msg.is_read = True
                        marked += 1
            if marked > 0:
                await self._save_data()
        return marked

    async def get_statistics(self) -> Dict:
        async with self._lock:
            online_agents = sum(1 for a in self.agents.values() if a.status == "online")
            active_connections = sum(
                1 for c in self.connections.values() if c.status == "connected"
            )
            total_unread = sum(
                len([m for m in msgs if not m.is_read]) for msgs in self.messages.values()
            )

            return {
                "total_agents": len(self.agents),
                "online_agents": online_agents,
                "total_connections": len(self.connections),
                "active_connections": active_connections,
                "total_groups": len(self.groups),
                "total_messages": sum(len(msgs) for msgs in self.messages.values()),
                "unread_messages": total_unread,
                "local_agent_id": self._local_agent_id,
                "local_agent_name": self._local_agent_name,
            }
