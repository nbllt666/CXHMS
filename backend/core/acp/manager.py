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
            yaml.dump(
                {"agents": [a.to_dict() for a in self.agents.values()]}, f, allow_unicode=True
            )

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

        return message

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

    async def _trigger_auto_reply(self, message: ACPMessageInfo) -> None:
        """通过正常聊天管线处理 ACP 消息，agent 可使用工具回复

        在 _inject_into_chat_context 之后调用。ACP 消息已作为 user 消息注入
        session，本方法通过 generate_chat_stream 走正常聊天管线（含工具调用循环），
        agent 可自行决定是否调用 acp_send_message 工具回复。

        前端可通过 session 历史看到完整过程（user 消息、assistant 回复、tool calls）。
        所有失败静默记录 warning，不影响主流程。
        """
        if not self._local_agent_id:
            return

        try:
            from backend.dependencies import get_context_manager, get_model_router
            from backend.core.chat.stream import generate_chat_stream, ChatStreamState

            context_mgr = get_context_manager()
            model_router = get_model_router()
            llm = model_router.get_client("main")

            if not llm:
                logger.warning("ACP 自动回复失败: 主模型客户端不可用")
                return

            # 获取 default agent 配置和工具（延迟导入避免循环依赖）
            from backend.api.routers.chat import (
                _get_tools_for_agent,
                get_agent_config,
                MAIN_HIDDEN_SYSTEM_PROMPT,
            )

            agent_config = get_agent_config("default") or {
                "system_prompt": "你是一个有帮助的AI助手。请用中文回答用户的问题，保持友好和专业。",
                "temperature": 0.7,
                "max_tokens": 4096,
                "enable_thinking": False,
            }

            tools = _get_tools_for_agent("default")

            session_id = "agent-default"

            # 构建消息列表：系统提示 + 隐藏提示 + 历史（含 ACP user 消息）
            messages: List[Dict[str, Any]] = []
            system_prompt = agent_config.get("system_prompt", "")
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "system", "content": MAIN_HIDDEN_SYSTEM_PROMPT})

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

            logger.info(
                f"ACP 自动回复启动: from={message.from_agent_id}, "
                f"messages={len(messages)}, tools={len(tools)}, "
                f"tool_names={[t['function']['name'] for t in tools[:5]]}..."
            )

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

            # 保存助手响应到 agent-default session
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

            # 同时保存到 ACP 协议级 session
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

    async def _inject_into_chat_context(self, message: ACPMessageInfo) -> None:
        """将 ACP 消息作为 user 消息注入到本地 Agent 聊天上下文

        ACP 消息类似于用户消息——agent 收到后触发回复。因此注入为 user 角色，
        让 agent 通过正常聊天管线（含工具调用）处理。

        同时注入到两个 session：
        1. agent-{local_agent_id}：ACP 协议级 session，与 chat.py 路由的会话模式对齐
        2. agent-default：前端默认助手使用的 session，确保用户能在前端看到 ACP 消息

        若 session 不存在则先创建，确保前端能通过既有聊天接口拉到这条消息。
        """
        if not self._local_agent_id:
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
            "source": "acp_external",
            "from_agent_id": message.from_agent_id,
            "from_agent_name": message.from_agent_name,
            "msg_type": message.msg_type,
            "acp_message_id": message.id,
            "timestamp": message.timestamp or _dt.now().isoformat(),
        }

        # 注入到 ACP 协议级 session
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
