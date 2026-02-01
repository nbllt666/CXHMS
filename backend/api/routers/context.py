from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel

router = APIRouter()


class SessionCreateRequest(BaseModel):
    workspace_id: str = "default"
    title: str = ""
    metadata: Dict = {}


class MessageCreateRequest(BaseModel):
    session_id: str
    role: str
    content: str
    content_type: str = "text"
    metadata: Dict = {}


@router.get("/api/context/sessions")
async def list_sessions(
    workspace_id: str = "default",
    limit: int = 20,
    active_only: bool = True
):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        sessions = context_mgr.get_sessions(
            workspace_id=workspace_id,
            limit=limit,
            active_only=active_only
        )
        return {
            "status": "success",
            "sessions": sessions,
            "total": len(sessions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/context/sessions")
async def create_session(request: SessionCreateRequest):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        session_id = context_mgr.create_session(
            workspace_id=request.workspace_id,
            title=request.title,
            metadata=request.metadata
        )
        return {
            "status": "success",
            "session_id": session_id,
            "message": "会话创建成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/context/sessions/{session_id}")
async def get_session(session_id: str):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        session = context_mgr.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        return {
            "status": "success",
            "session": session
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/context/sessions/{session_id}")
async def delete_session(session_id: str):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        success = context_mgr.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")

        return {
            "status": "success",
            "message": "会话删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/context/messages/{session_id}")
async def get_messages(
    session_id: str,
    limit: int = 50,
    offset: int = 0
):
    from api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        messages = context_mgr.get_messages(
            session_id=session_id,
            limit=limit,
            offset=offset
        )
        return {
            "status": "success",
            "session_id": session_id,
            "messages": messages,
            "total": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/context/messages")
async def add_message(request: MessageCreateRequest):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        message_id = context_mgr.add_message(
            session_id=request.session_id,
            role=request.role,
            content=request.content,
            content_type=request.content_type,
            metadata=request.metadata
        )
        return {
            "status": "success",
            "message_id": message_id,
            "message": "消息添加成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/context/summary")
async def generate_summary(session_id: str, max_length: int = 500):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        messages = context_mgr.get_messages(session_id, limit=100)

        from backend.core.context.summarizer import ContextSummarizer
        summarizer = ContextSummarizer()
        result = await summarizer.summarize(messages, max_length=max_length)

        context_mgr.update_session(session_id, summary=result.get("summary", ""))

        return {
            "status": "success",
            "summary": result.get("summary", ""),
            "key_points": result.get("key_points", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/context/stats")
async def get_context_stats(workspace_id: str = "default"):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        stats = context_mgr.get_statistics(workspace_id)

        return {
            "status": "success",
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
