import threading
from typing import Optional, Any, Dict

from fastapi import HTTPException, Request
from fastapi import Depends


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
