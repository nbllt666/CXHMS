from fastapi import APIRouter, HTTPException

from backend.core.logging_config import get_contextual_logger

router = APIRouter()
logger = get_contextual_logger(__name__)


@router.get("/stats")
async def get_system_stats():
    from backend.api.app import get_context_manager, get_memory_manager
    from backend.api.routers.agents import _load_agents

    try:
        memory_mgr = get_memory_manager()
        conn = memory_mgr._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = FALSE")
            total_memories = cursor.fetchone()[0]

            try:
                cursor.execute("SELECT COUNT(*) FROM memories WHERE archived_at IS NOT NULL AND is_deleted = FALSE")
                archived_memories = cursor.fetchone()[0]
            except Exception:
                archived_memories = 0
        finally:
            memory_mgr._release_connection(conn)

        # 实际配置的 Agent 数（排除内置的 memory-agent）
        try:
            agents = _load_agents()
            total_agents = sum(1 for a in agents if a.get("id") != "memory-agent")
        except Exception:
            total_agents = 0

        total_sessions = 0
        total_messages = 0
        try:
            context_mgr = get_context_manager()
            ctx_stats = context_mgr.get_statistics()
            total_sessions = ctx_stats.get("total_sessions", 0)
            total_messages = ctx_stats.get("total_messages", 0)
        except Exception:
            total_sessions = 0
            total_messages = 0

        return {
            "status": "success",
            "data": {
                "total_memories": total_memories,
                "total_sessions": total_sessions,
                "total_agents": total_agents,
                "archived_memories": archived_memories,
                "total_messages": total_messages,
            },
        }
    except Exception as e:
        logger.error(f"获取系统统计数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
