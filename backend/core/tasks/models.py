"""
任务数据模型 - 任务辅助工具使用的数据结构
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Task:
    """任务数据类"""

    id: str
    agent_id: str
    title: str
    description: str = ""
    priority: str = "medium"  # low / medium / high / urgent
    status: str = "pending"  # pending / in_progress / completed / cancelled
    due_date: Optional[str] = None  # ISO 格式字符串
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "agent_id": self.agent_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "due_date": self.due_date,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat()
        else:
            result["completed_at"] = None
        return result
