from fastapi import APIRouter, HTTPException

from backend.core.logging_config import get_contextual_logger

router = APIRouter()
logger = get_contextual_logger(__name__)


@router.get("/stats")
async def get_system_stats():
    from backend.api.app import get_context_manager, get_memory_manager

    try:
        memory_mgr = get_memory_manager()
        conn = memory_mgr._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = FALSE")
        total_memories = cursor.fetchone()[0]

        try:
            cursor.execute("SELECT COUNT(*) FROM agent_memory_tables")
            total_agents = cursor.fetchone()[0]
        except Exception:
            total_agents = 0

        try:
            cursor.execute("SELECT COUNT(*) FROM memories WHERE archived_at IS NOT NULL AND is_deleted = FALSE")
            archived_memories = cursor.fetchone()[0]
        except Exception:
            archived_memories = 0

        memory_mgr._release_connection(conn)

        total_sessions = 0
        try:
            context_mgr = get_context_manager()
            ctx_conn = context_mgr._get_connection()
            ctx_cursor = ctx_conn.cursor()
            ctx_cursor.execute("SELECT COUNT(*) FROM sessions")
            total_sessions = ctx_cursor.fetchone()[0]
            context_mgr.close_connection()
        except Exception:
            total_sessions = 0

        return {
            "status": "success",
            "data": {
                "total_memories": total_memories,
                "total_sessions": total_sessions,
                "total_agents": total_agents,
                "archived_memories": archived_memories,
            },
        }
    except Exception as e:
        logger.error(f"获取系统统计数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
