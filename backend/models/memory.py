from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid


class MemoryType(str, Enum):
    PERMANENT = "permanent"
    LONG_TERM = "long_term"
    SHORT_TERM = "short_term"


@dataclass
class Memory:
    id: int = 0
    type: MemoryType = MemoryType.LONG_TERM
    content: str = ""
    vector_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance: int = 3
    importance_score: float = 0.6
    decay_type: str = "exponential"
    decay_params: Dict[str, Any] = field(default_factory=dict)
    reactivation_count: int = 0
    emotion_score: float = 0.0
    permanent: bool = False
    psychological_age: float = 1.0
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    archived_at: Optional[str] = None
    is_deleted: bool = False
    source: str = "user"
    workspace_id: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, MemoryType) else self.type,
            "content": self.content,
            "vector_id": self.vector_id,
            "metadata": self.metadata,
            "importance": self.importance,
            "importance_score": self.importance_score,
            "decay_type": self.decay_type,
            "decay_params": self.decay_params,
            "reactivation_count": self.reactivation_count,
            "emotion_score": self.emotion_score,
            "permanent": self.permanent,
            "psychological_age": self.psychological_age,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived_at": self.archived_at,
            "is_deleted": self.is_deleted,
            "source": self.source,
            "workspace_id": self.workspace_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        return cls(
            id=data.get("id", 0),
            type=MemoryType(data.get("type", "long_term")),
            content=data.get("content", ""),
            vector_id=data.get("vector_id"),
            metadata=data.get("metadata", {}),
            importance=data.get("importance", 3),
            importance_score=data.get("importance_score", 0.6),
            decay_type=data.get("decay_type", "exponential"),
            decay_params=data.get("decay_params", {}),
            reactivation_count=data.get("reactivation_count", 0),
            emotion_score=data.get("emotion_score", 0.0),
            permanent=data.get("permanent", False),
            psychological_age=data.get("psychological_age", 1.0),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at"),
            archived_at=data.get("archived_at"),
            is_deleted=data.get("is_deleted", False),
            source=data.get("source", "user"),
            workspace_id=data.get("workspace_id", "default")
        )


@dataclass
class MemoryCreate:
    content: str
    type: MemoryType = MemoryType.LONG_TERM
    importance: int = 3
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    permanent: bool = False
    emotion_score: float = 0.0
    workspace_id: str = "default"


@dataclass
class MemoryUpdate:
    content: Optional[str] = None
    importance: Optional[int] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    permanent: Optional[bool] = None


@dataclass
class MemoryResponse:
    status: str = "success"
    memory: Optional[Dict[str, Any]] = None
    message: str = ""


@dataclass
class MemorySearch:
    query: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    tags: Optional[List[str]] = None
    time_range: Optional[str] = None
    limit: int = 10
    include_deleted: bool = False
    workspace_id: str = "default"


@dataclass
class MemoryStatistics:
    total: int = 0
    permanent: int = 0
    long_term: int = 0
    short_term: int = 0
    soft_deleted: int = 0
    by_importance: Dict[int, int] = field(default_factory=dict)
    by_tags: Dict[str, int] = field(default_factory=dict)


@dataclass
class RAGSearchResult:
    memory_id: int
    content: str
    score: float
    importance: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "vector"


@dataclass
class RAGSearchResponse:
    status: str = "success"
    query: str = ""
    results: List[RAGSearchResult] = field(default_factory=list)
    total_found: int = 0
    message: str = ""
