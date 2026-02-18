import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = "default"
    title: str = ""
    user_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    message_count: int = 0
    summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "summary": self.summary,
            "metadata": self.metadata,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            workspace_id=data.get("workspace_id", "default"),
            title=data.get("title", ""),
            user_id=data.get("user_id"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            message_count=data.get("message_count", 0),
            summary=data.get("summary"),
            metadata=data.get("metadata", {}),
            is_active=data.get("is_active", True),
        )


@dataclass
class Message:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: str = "user"
    content: str = ""
    content_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_deleted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "content_type": self.content_type,
            "metadata": self.metadata,
            "tokens": self.tokens,
            "created_at": self.created_at,
            "is_deleted": self.is_deleted,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            session_id=data.get("session_id", ""),
            role=data.get("role", "user"),
            content=data.get("content", ""),
            content_type=data.get("content_type", "text"),
            metadata=data.get("metadata", {}),
            tokens=data.get("tokens", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            is_deleted=data.get("is_deleted", False),
        )


@dataclass
class SessionCreate:
    workspace_id: str = "default"
    title: str = ""
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageCreate:
    session_id: str
    role: str
    content: str
    content_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionResponse:
    status: str = "success"
    session: Optional[Dict[str, Any]] = None
    message: str = ""


@dataclass
class MessageResponse:
    status: str = "success"
    messages: List[Dict[str, Any]] = field(default_factory=list)
    total: int = 0
    message: str = ""


@dataclass
class ContextWindow:
    session_id: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    summary: Optional[str] = None
    truncated: bool = False


@dataclass
class SummaryRequest:
    session_id: str
    max_length: int = 500
    style: str = "concise"


@dataclass
class SummaryResponse:
    status: str = "success"
    summary: str = ""
    key_points: List[str] = field(default_factory=list)
    message: str = ""


@dataclass
class ContextStats:
    total_sessions: int = 0
    active_sessions: int = 0
    total_messages: int = 0
    avg_messages_per_session: float = 0.0
    oldest_session: Optional[str] = None
    newest_session: Optional[str] = None
