"""
Agent上下文管理器 - 转发层
所有功能已合并到 ContextManager（文件+内存双存储方案），
本模块仅作为兼容层，将调用转发到全局 ContextManager 单例。
"""

from typing import Any, Dict, List, Optional

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


class AgentContextManager:
    """Agent上下文管理器 - 转发层

    实例化时获取全局 ContextManager 单例，所有方法调用转发到 ContextManager。
    """

    def __init__(self, db_path: str = "data/memories.db") -> None:
        """初始化 - 获取全局 ContextManager 单例

        Args:
            db_path: 兼容参数，已忽略
        """
        from backend.api.app import get_context_manager

        self._ctx = get_context_manager()
        logger.debug("AgentContextManager 转发层已初始化，指向全局 ContextManager")

    def save_context(
        self,
        agent_id: str,
        messages: List[Dict[str, Any]],
        memory_state: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ):
        """保存Agent上下文 - 通过 ContextManager API 实现

        先确保 session 存在，再清空旧消息并逐条写入新消息。
        """
        ctx = self._ctx
        # 确保 session 存在
        if ctx.get_session(agent_id) is None:
            ctx.create_session(session_id=agent_id, title=agent_id)
        # 清空旧消息
        ctx.clear_session_messages(agent_id)
        # 逐条写入新消息
        for msg in messages:
            ctx.append_message(
                agent_id=agent_id,
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                metadata=msg.get("metadata"),
            )

    def load_context(self, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """加载Agent上下文 - 转发到 ContextManager.get_messages"""
        return self._ctx.get_messages(session_id=agent_id, limit=limit, offset=0, include_deleted=False)

    def append_message(
        self, agent_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ):
        """追加消息到上下文历史 - 转发到 ContextManager.append_message"""
        self._ctx.append_message(agent_id, role, content, metadata)

    def get_message_history(self, agent_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取消息历史 - 转发到 ContextManager.get_message_history"""
        return self._ctx.get_message_history(agent_id, limit)

    def clear_context(self, agent_id: str):
        """清空Agent上下文 - 转发到 ContextManager.clear_context"""
        self._ctx.clear_context(agent_id)

    def get_context_summary(self, agent_id: str) -> Dict[str, Any]:
        """获取上下文摘要 - 转发到 ContextManager.get_context_summary"""
        return self._ctx.get_context_summary(agent_id)

    def update_last_active(self, agent_id: str):
        """更新最后活跃时间 - 转发到 ContextManager.update_last_active"""
        self._ctx.update_last_active(agent_id)

    def cleanup_old_messages(self, agent_id: str, keep_count: int = 1000):
        """清理旧消息 - 转发到 ContextManager.cleanup_old_messages"""
        self._ctx.cleanup_old_messages(agent_id, keep_count)

    def close_all_connections(self):
        """关闭所有连接 - 无操作（ContextManager 无需手动关闭连接）"""
        pass
