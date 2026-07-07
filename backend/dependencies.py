import inspect
import logging
import threading
from typing import Optional, Any, Dict

from fastapi import HTTPException, Request
from fastapi import Depends

logger = logging.getLogger(__name__)


class ServiceState:
    def __init__(self):
        self.memory_manager = None
        self.async_memory_manager = None
        self.context_manager = None
        self.acp_manager = None
        self.llm_client = None
        self.secondary_router = None
        self.mcp_manager = None
        self.model_router = None
        self.cxfc_manager: Optional[Any] = None
        # 组件原子替换锁：保护并发场景下的属性赋值
        self._lock = threading.Lock()

    def update_component(self, name: str, new_instance: Any) -> Optional[Any]:
        """原子替换某个组件实例，返回旧实例。

        线程安全：使用 _lock 保护属性赋值。
        不在锁内调用旧实例的 close()/shutdown()（避免死锁）。
        旧实例的安全关闭在锁外执行；若旧实例的 close 是 async 协程，
        则跳过同步关闭（应由调用方在事件循环中处理）。

        Args:
            name: ServiceState 属性名（如 "memory_manager"）。
            new_instance: 新的组件实例。

        Returns:
            被替换的旧实例（若无则返回 None）。
        """
        with self._lock:
            old = getattr(self, name, None)
            setattr(self, name, new_instance)
        # 锁外安全关闭旧实例，避免长 IO 拖累锁
        # 单例组件（如 model_router）old 与 new_instance 是同一对象，
        # reinit 方法已自行 close/reinitialize，此处跳过避免关闭刚初始化的实例
        if old is not None and old is not new_instance:
            self._safe_close(old)
        return old

    @staticmethod
    def _safe_close(instance: Any) -> None:
        """安全关闭实例，失败仅记录日志。

        优先调用 shutdown()；若不存在则尝试 close()。
        若 close() 是协程函数，则跳过（async 关闭应由调用方处理）。
        """
        try:
            if hasattr(instance, "shutdown"):
                instance.shutdown()
            elif hasattr(instance, "close"):
                if inspect.iscoroutinefunction(instance.close):
                    logger.debug(
                        f"{type(instance).__name__} 的 close() 是 async，"
                        "已在同步 update_component 中跳过，由调用方处理"
                    )
                else:
                    instance.close()
        except Exception as e:
            logger.warning(
                f"关闭旧实例失败 [{type(instance).__name__}/{type(e).__name__}]: {e}"
            )


_service_state: Optional[ServiceState] = None


def set_service_state(state: ServiceState):
    global _service_state
    _service_state = state


def get_service_state(request: Request) -> ServiceState:
    return request.app.state.services


def _resolve_state(state=None) -> ServiceState:
    if isinstance(state, ServiceState):
        return state
    if _service_state is not None:
        return _service_state
    raise RuntimeError("Service state not initialized. Call set_service_state() first.")


def get_memory_manager(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.memory_manager is None:
        raise HTTPException(status_code=503, detail="记忆服务不可用")
    return state.memory_manager


def get_async_memory_manager(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.async_memory_manager is None:
        raise HTTPException(status_code=503, detail="异步记忆服务不可用")
    return state.async_memory_manager


def get_context_manager(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.context_manager is None:
        raise HTTPException(status_code=503, detail="上下文服务不可用")
    return state.context_manager


def get_acp_manager(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.acp_manager is None:
        raise HTTPException(status_code=503, detail="ACP服务不可用")
    return state.acp_manager


def get_llm_client(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.llm_client is None:
        raise HTTPException(status_code=503, detail="LLM服务不可用")
    return state.llm_client


def get_secondary_router(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.secondary_router is None:
        raise HTTPException(status_code=503, detail="副模型路由器不可用")
    return state.secondary_router


def get_mcp_manager(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.mcp_manager is None:
        raise HTTPException(status_code=503, detail="MCP管理器不可用")
    return state.mcp_manager


def get_model_router(state: ServiceState = Depends(get_service_state)):
    state = _resolve_state(state)
    if state.model_router is None:
        raise HTTPException(status_code=503, detail="模型路由器不可用")
    return state.model_router


def get_graph_database(agent_id: str = "default", state: ServiceState = Depends(get_service_state)):
    """按 agent_id 获取图数据库实例（按需创建）。"""
    _resolve_state(state)
    return _get_or_create_graph_database(agent_id)


def get_graph_store(agent_id: str = "default", state: ServiceState = Depends(get_service_state)):
    """按 agent_id 获取图存储实例（按需创建）。"""
    _resolve_state(state)
    return _get_or_create_graph_store(agent_id)


# ---- 按助手的图数据库/图存储注册表 ----
_graph_databases: Dict[str, Any] = {}
_graph_stores: Dict[str, Any] = {}
_graph_registry_lock = threading.Lock()


def _get_or_create_graph_database(agent_id: str = "default"):
    """按 agent_id 获取或按需创建 GraphDatabase 实例。"""
    if agent_id not in _graph_databases:
        with _graph_registry_lock:
            if agent_id not in _graph_databases:
                from backend.core.graph import GraphDatabase
                gdb = GraphDatabase(agent_id=agent_id)
                gdb.initialize()
                _graph_databases[agent_id] = gdb
    return _graph_databases[agent_id]


def _get_or_create_graph_store(agent_id: str = "default"):
    """按 agent_id 获取或按需创建 GraphStore 实例。"""
    if agent_id not in _graph_stores:
        with _graph_registry_lock:
            if agent_id not in _graph_stores:
                from backend.core.memory.graph_store import SQLiteGraphStore
                gdb = _get_or_create_graph_database(agent_id)
                _graph_stores[agent_id] = SQLiteGraphStore(gdb)
    return _graph_stores[agent_id]


def get_graph_database_if_exists(agent_id: str = "default"):
    """返回已注册的 GraphDatabase 实例，不存在时返回 None（不创建）。"""
    return _graph_databases.get(agent_id)


def get_graph_store_if_exists(agent_id: str = "default"):
    """返回已注册的 GraphStore 实例，不存在时返回 None（不创建）。"""
    return _graph_stores.get(agent_id)


def remove_graph_database(agent_id: str) -> None:
    """从注册表移除并关闭对应 agent 的图数据库及图存储实例。"""
    with _graph_registry_lock:
        store = _graph_stores.pop(agent_id, None)
        gdb = _graph_databases.pop(agent_id, None)
    # 关闭 GraphDatabase（底层 Database 由 database.py 注册表管理）
    if gdb is not None:
        try:
            gdb.close()
        except Exception:
            pass
    # 同步移除底层 Database 注册表项
    try:
        from backend.core.graph.database import remove_database
        remove_database(agent_id)
    except Exception:
        pass


def get_cxfc_manager(state: ServiceState = Depends(get_service_state)) -> Optional[Any]:
    return _resolve_state(state).cxfc_manager
