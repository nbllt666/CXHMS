from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class AgentStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


class MessageType(str, Enum):
    CHAT = "chat"
    MEMORY_REQUEST = "memory_request"
    MEMORY_RESPONSE = "memory_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    BROADCAST = "broadcast"
    GROUP_MESSAGE = "group_message"
    SYNC = "sync"
    CONTROL = "control"


@dataclass
class ACPAgent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    host: str = ""
    port: int = 0
    status: AgentStatus = AgentStatus.OFFLINE
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "status": self.status.value if isinstance(self.status, AgentStatus) else self.status,
            "version": self.version,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPAgent":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            host=data.get("host", ""),
            port=data.get("port", 0),
            status=AgentStatus(data.get("status", "offline")),
            version=data.get("version", "1.0.0"),
            capabilities=data.get("capabilities", []),
            last_seen=data.get("last_seen", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


@dataclass
class ACPConnection:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
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
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPConnection":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            local_agent_id=data.get("local_agent_id", ""),
            remote_agent_id=data.get("remote_agent_id", ""),
            remote_agent_name=data.get("remote_agent_name", ""),
            host=data.get("host", ""),
            port=data.get("port", 0),
            status=data.get("status", "disconnected"),
            connected_at=data.get("connected_at"),
            last_activity=data.get("last_activity"),
            messages_sent=data.get("messages_sent", 0),
            messages_received=data.get("messages_received", 0),
            metadata=data.get("metadata", {})
        )


@dataclass
class ACPGroupMember:
    agent_id: str = ""
    agent_name: str = ""
    role: str = "member"
    joined_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "joined_at": self.joined_at,
            "last_active": self.last_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPGroupMember":
        return cls(
            agent_id=data.get("agent_id", ""),
            agent_name=data.get("agent_name", ""),
            role=data.get("role", "member"),
            joined_at=data.get("joined_at", datetime.now().isoformat()),
            last_active=data.get("last_active", datetime.now().isoformat())
        )


@dataclass
class ACPGroup:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    creator_id: str = ""
    creator_name: str = ""
    members: List[ACPGroupMember] = field(default_factory=list)
    max_members: int = 50
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "members": [m.to_dict() for m in self.members],
            "max_members": self.max_members,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPGroup":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            creator_id=data.get("creator_id", ""),
            creator_name=data.get("creator_name", ""),
            members=[ACPGroupMember.from_dict(m) for m in data.get("members", [])],
            max_members=data.get("max_members", 50),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


@dataclass
class ACPMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: MessageType = MessageType.CHAT
    from_agent_id: str = ""
    from_agent_name: str = ""
    to_agent_id: Optional[str] = None
    to_group_id: Optional[str] = None
    content: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_read: bool = False
    is_sent: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.msg_type.value if isinstance(self.msg_type, MessageType) else self.msg_type,
            "from_agent_id": self.from_agent_id,
            "from_agent_name": self.from_agent_name,
            "to_agent_id": self.to_agent_id,
            "to_group_id": self.to_group_id,
            "content": self.content,
            "timestamp": self.timestamp,
            "is_read": self.is_read,
            "is_sent": self.is_sent,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPMessage":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            msg_type=MessageType(data.get("type", "chat")),
            from_agent_id=data.get("from_agent_id", ""),
            from_agent_name=data.get("from_agent_name", ""),
            to_agent_id=data.get("to_agent_id"),
            to_group_id=data.get("to_group_id"),
            content=data.get("content", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            is_read=data.get("is_read", False),
            is_sent=data.get("is_sent", False),
            metadata=data.get("metadata", {})
        )


@dataclass
class ACPAgentResponse:
    status: str = "success"
    agent: Optional[Dict[str, Any]] = None
    message: str = ""


@dataclass
class ACPConnectionResponse:
    status: str = "success"
    connection: Optional[Dict[str, Any]] = None
    message: str = ""


@dataclass
class ACPGroupResponse:
    status: str = "success"
    group: Optional[Dict[str, Any]] = None
    message: str = ""


@dataclass
class ACPDiscoverResponse:
    status: str = "success"
    agents: List[Dict[str, Any]] = field(default_factory=list)
    scanned_count: int = 0
    message: str = ""


@dataclass
class ACPSendMessageRequest:
    to_agent_id: Optional[str] = None
    to_group_id: Optional[str] = None
    content: Dict[str, Any] = field(default_factory=dict)
    msg_type: str = "chat"


@dataclass
class ACPSendMessageResponse:
    status: str = "success"
    message_id: Optional[str] = None
    message: str = ""


@dataclass
class ACPStatistics:
    total_agents: int = 0
    online_agents: int = 0
    total_connections: int = 0
    active_connections: int = 0
    total_groups: int = 0
    total_messages: int = 0
    unread_messages: int = 0
