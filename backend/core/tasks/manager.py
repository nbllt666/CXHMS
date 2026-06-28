"""
任务管理器 - 基于 SQLite 的任务持久化存储
参照 backend/core/alarm/manager.py 的实现模式
"""

import logging
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from .models import Task

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器 - SQLite 持久化"""

    def __init__(self, db_path: str = "data/tasks.db"):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """确保数据库表已创建"""
        os.makedirs(
            os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".",
            exist_ok=True,
        )
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'pending',
                due_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
        """
        )
        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_task(
        self,
        agent_id: str,
        title: str,
        description: str = "",
        priority: str = "medium",
        due_date: Optional[str] = None,
    ) -> str:
        """创建任务，返回 task_id"""
        task_id = str(uuid.uuid4())
        now = datetime.now()

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks
                (id, agent_id, title, description, priority, status, due_date,
                 created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task_id,
                agent_id,
                title,
                description,
                priority,
                "pending",
                due_date,
                now.isoformat(),
                now.isoformat(),
                None,
            ),
        )
        conn.commit()
        conn.close()

        logger.info(
            f"创建任务: {task_id}, agent={agent_id}, title={title}, priority={priority}"
        )
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取单个任务"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def list_tasks(
        self,
        agent_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[Dict]:
        """列出任务，支持按 status / priority 过滤，按 created_at DESC 排序"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM tasks WHERE agent_id = ?"
        params: List = [agent_id]

        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> bool:
        """更新指定字段，刷新 updated_at"""
        fields = []
        params: List = []

        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if priority is not None:
            fields.append("priority = ?")
            params.append(priority)
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if due_date is not None:
            fields.append("due_date = ?")
            params.append(due_date)

        if not fields:
            return False

        fields.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(task_id)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f"更新任务: {task_id}")
            return True
        return False

    def complete_task(self, task_id: str) -> bool:
        """标记任务为已完成"""
        now = datetime.now()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'completed', completed_at = ?, updated_at = ?
            WHERE id = ?
        """,
            (now.isoformat(), now.isoformat(), task_id),
        )
        affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f"完成任务: {task_id}")
            return True
        return False

    def delete_task(self, task_id: str) -> bool:
        """物理删除任务"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f"删除任务: {task_id}")
            return True
        return False


_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取全局 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


def reset_task_manager():
    """重置全局 TaskManager 实例（用于测试）"""
    global _task_manager
    _task_manager = None
