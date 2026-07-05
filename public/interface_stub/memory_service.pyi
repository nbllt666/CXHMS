"""MemoryService 接口契约存根。

对应 backend/core/memory/manager.py 的 MemoryManager 与 backend/api/routers/memory.py 的路由。
零实现逻辑，仅声明签名。模块实现必须严格匹配本存根的签名、参数类型、返回值类型与抛出异常。

@version 1.0.0
@see public/schema/memory.json
"""

from typing import Any, Dict, List, Optional, Tuple


class MemoryService:
    """记忆服务接口。

    提供记忆的写入、查询、搜索、召回、批量操作与衰减管理能力。
    所有记忆数据必须符合 public/schema/memory.json 契约。
    """

    def write_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        importance: int = 3,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        permanent: bool = False,
        emotion_score: float = 0.0,
        workspace_id: str = "default",
        agent_id: str = "default",
    ) -> int:
        """写入一条记忆，返回新记忆 ID。

        Raises:
            MemoryOperationError: 写入失败（数据库错误/向量索引失败）
            ValueError: content 为空或 importance 越界
        """
        ...

    def get_memory(self, memory_id: int, include_deleted: bool = False, agent_id: str = "default") -> Optional[Dict[str, Any]]:
        """按 ID 获取单条记忆；不存在返回 None。

        Args:
            include_deleted: 是否包含已软删除的记忆，默认 False（不包含）

        Raises:
            MemoryOperationError: 查询失败
        """
        ...

    def update_memory(
        self,
        memory_id: int,
        new_content: Optional[str] = None,
        new_importance: Optional[int] = None,
        new_tags: Optional[List[str]] = None,
        new_metadata: Optional[Dict[str, Any]] = None,
        agent_id: str = "default",
    ) -> bool:
        """更新记忆字段；返回是否成功。不存在返回 False。

        Raises:
            MemoryOperationError: 更新失败
            ValueError: importance 越界
        """
        ...

    def delete_memory(
        self, memory_id: int, soft_delete: bool = True, agent_id: str = "default"
    ) -> bool:
        """删除记忆。soft_delete=True 软删除，False 硬删除。返回是否成功。

        Raises:
            MemoryOperationError: 删除失败
        """
        ...

    def search_memories(
        self,
        query: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        include_deleted: bool = False,
        workspace_id: str = "default",
        agent_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """多条件搜索记忆，返回记忆字典列表。

        Raises:
            MemoryOperationError: 搜索失败
        """
        ...

    def recall_memory(
        self, memory_id: int, emotion_intensity: float = 0.0, agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """召回记忆并更新 reactivation_count 与心理年龄。

        Raises:
            MemoryOperationError: 召回失败
        """
        ...

    def get_statistics(self, workspace_id: str = "default") -> Dict[str, Any]:
        """返回记忆统计信息。

        Raises:
            MemoryOperationError: 统计失败
        """
        ...

    def is_vector_search_enabled(self) -> bool:
        """返回向量搜索是否启用。纯查询，不抛异常。"""
        ...

    async def hybrid_search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 5,
        workspace_id: Optional[str] = None,
        agent_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """混合（向量+关键词）搜索记忆。

        Raises:
            VectorStoreError: 向量库不可用或查询失败
        """
        ...

    async def semantic_search(
        self, query: str, memory_type: Optional[str] = None, limit: int = 10, agent_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """纯向量语义搜索。

        Args:
            memory_type: 记忆类型过滤，None 表示不过滤

        Raises:
            VectorStoreError: 向量库未启用或查询失败
        """
        ...

    def batch_write_memories(
        self, memories: List[Dict[str, Any]], raise_on_error: bool = False
    ) -> Dict[str, Any]:
        """批量写入记忆，返回 {success_count, failed_count, errors}。

        Raises:
            MemoryOperationError: raise_on_error=True 时首个失败即抛出
        """
        ...

    def batch_update_memories(
        self, updates: List[Dict[str, Any]], raise_on_error: bool = False, agent_id: str = "default"
    ) -> Dict[str, Any]:
        """批量更新记忆。

        Args:
            updates: 更新列表，每个包含 memory_id 和要更新的字段
            raise_on_error: 遇到错误是否抛出异常
            agent_id: Agent ID
        """
        ...

    def batch_delete_memories(
        self,
        memory_ids: List[int],
        soft_delete: bool = True,
        raise_on_error: bool = False,
        agent_id: str = "default",
    ) -> Dict[str, Any]:
        """批量删除记忆。"""
        ...

    def sync_decay_values(self, workspace_id: str = "default") -> Dict[str, Any]:
        """同步衰减分数。"""
        ...
