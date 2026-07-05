"""MemoryService 预生成 Mock。

实现 public/interface_stub/memory_service.pyi 的全部签名，
返回符合 public/schema/memory.json 契约的模拟值。

使用方式：
    from public.pre_generated_mock.memory_mock import MockMemoryService
    svc = MockMemoryService()
    mid = svc.write_memory(content="示例")
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


def _iso_now() -> str:
    return datetime.now().isoformat()


def _make_memory(
    memory_id: int,
    content: str,
    memory_type: str = "long_term",
    importance: int = 3,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    permanent: bool = False,
    emotion_score: float = 0.0,
    workspace_id: str = "default",
    agent_id: str = "default",
) -> Dict[str, Any]:
    """构造符合 memory.json 契约的记忆字典。"""
    return {
        "id": memory_id,
        "type": memory_type,
        "content": content,
        "vector_id": f"vec-{memory_id:08d}",
        "metadata": metadata or {},
        "importance": importance,
        "importance_score": round(importance / 5.0, 2),
        "decay_type": "exponential",
        "decay_params": {},
        "reactivation_count": 0,
        "emotion_score": emotion_score,
        "permanent": permanent,
        "psychological_age": 1.0,
        "tags": tags or [],
        "created_at": _iso_now(),
        "updated_at": None,
        "archived_at": None,
        "is_deleted": False,
        "source": "user",
        "workspace_id": workspace_id,
        "agent_id": agent_id,
    }


class MockMemoryService:
    """MemoryService 的 Mock 实现。内存态，无持久化。"""

    def __init__(self) -> None:
        self._store: Dict[int, Dict[str, Any]] = {}
        self._seq: int = 1
        self._vector_enabled: bool = True

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
        if not content:
            raise ValueError("content 不能为空")
        if not (1 <= importance <= 5):
            raise ValueError("importance 必须在 1-5 之间")
        mid = self._seq
        self._seq += 1
        self._store[mid] = _make_memory(
            mid, content, memory_type, importance, tags, metadata,
            permanent, emotion_score, workspace_id, agent_id,
        )
        return mid

    def get_memory(self, memory_id: int, include_deleted: bool = False, agent_id: str = "default") -> Optional[Dict[str, Any]]:
        m = self._store.get(memory_id)
        if m is None:
            return None
        if not include_deleted and m.get("is_deleted"):
            return None
        return dict(m)

    def update_memory(
        self,
        memory_id: int,
        new_content: Optional[str] = None,
        new_importance: Optional[int] = None,
        new_tags: Optional[List[str]] = None,
        new_metadata: Optional[Dict[str, Any]] = None,
        agent_id: str = "default",
    ) -> bool:
        m = self._store.get(memory_id)
        if m is None:
            return False
        if new_content is not None:
            m["content"] = new_content
        if new_importance is not None:
            m["importance"] = new_importance
            m["importance_score"] = round(new_importance / 5.0, 2)
        if new_tags is not None:
            m["tags"] = new_tags
        if new_metadata is not None:
            m["metadata"] = new_metadata
        m["updated_at"] = _iso_now()
        return True

    def delete_memory(self, memory_id: int, soft_delete: bool = True, agent_id: str = "default") -> bool:
        m = self._store.get(memory_id)
        if m is None:
            return False
        if soft_delete:
            m["is_deleted"] = True
        else:
            del self._store[memory_id]
        return True

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
        results = []
        for m in self._store.values():
            if not include_deleted and m.get("is_deleted"):
                continue
            if memory_type and m["type"] != memory_type:
                continue
            if tags and not set(tags).issubset(set(m["tags"])):
                continue
            if query and query.lower() not in m["content"].lower():
                continue
            results.append(dict(m))
        return results[offset: offset + limit]

    def recall_memory(
        self, memory_id: int, emotion_intensity: float = 0.0, agent_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        m = self._store.get(memory_id)
        if m is None or m.get("is_deleted"):
            return None
        m["reactivation_count"] += 1
        m["psychological_age"] += 0.1
        return dict(m)

    def get_statistics(self, workspace_id: str = "default") -> Dict[str, Any]:
        items = [m for m in self._store.values() if not m.get("is_deleted")]
        return {
            "total": len(items),
            "permanent": sum(1 for m in items if m["type"] == "permanent"),
            "long_term": sum(1 for m in items if m["type"] == "long_term"),
            "short_term": sum(1 for m in items if m["type"] == "short_term"),
            "soft_deleted": sum(1 for m in self._store.values() if m.get("is_deleted")),
            "by_importance": {},
            "by_tags": {},
        }

    def is_vector_search_enabled(self) -> bool:
        return self._vector_enabled

    async def hybrid_search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 5,
        workspace_id: Optional[str] = None,
        agent_id: str = "default",
    ) -> List[Dict[str, Any]]:
        return self.search_memories(
            query=query, memory_type=memory_type, tags=tags, limit=limit,
            workspace_id=workspace_id or "default", agent_id=agent_id,
        )

    async def semantic_search(
        self, query: str, memory_type: Optional[str] = None, limit: int = 10, agent_id: str = "default"
    ) -> List[Dict[str, Any]]:
        return self.search_memories(query=query, memory_type=memory_type, limit=limit, agent_id=agent_id)

    def batch_write_memories(
        self, memories: List[Dict[str, Any]], raise_on_error: bool = False
    ) -> Dict[str, Any]:
        success, failed = 0, 0
        errors: List[str] = []
        for item in memories:
            try:
                self.write_memory(content=item["content"])
                success += 1
            except Exception as exc:
                failed += 1
                errors.append(str(exc))
                if raise_on_error:
                    raise
        return {"success_count": success, "failed_count": failed, "errors": errors}

    def batch_update_memories(
        self, updates: List[Dict[str, Any]], raise_on_error: bool = False, agent_id: str = "default"
    ) -> Dict[str, Any]:
        success, failed = 0, 0
        errors: List[str] = []
        for u in updates:
            memory_id = u.get("memory_id")
            if not memory_id:
                errors.append("memory_id is required")
                failed += 1
                if raise_on_error:
                    raise ValueError("memory_id is required")
                continue
            ok = self.update_memory(u["memory_id"], new_content=u.get("content"), agent_id=agent_id)
            if ok:
                success += 1
            else:
                failed += 1
                errors.append(f"Memory {memory_id} not found")
                if raise_on_error:
                    raise RuntimeError(f"Memory {memory_id} not found")
        return {"success_count": success, "failed_count": failed, "errors": errors}

    def batch_delete_memories(
        self,
        memory_ids: List[int],
        soft_delete: bool = False,
        raise_on_error: bool = False,
        agent_id: str = "default",
    ) -> Dict[str, Any]:
        success, failed = 0, 0
        for mid in memory_ids:
            if self.delete_memory(mid, soft_delete=soft_delete, agent_id=agent_id):
                success += 1
            else:
                failed += 1
        return {"success_count": success, "failed_count": failed}

    def sync_decay_values(self, workspace_id: str = "default") -> Dict[str, Any]:
        return {"updated_count": 0, "workspace_id": workspace_id}
