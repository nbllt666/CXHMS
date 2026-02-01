from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    workspace_id: str = "default"
    stream: bool = True
    use_memory: bool = True
    use_tools: bool = True


class ChatResponse(BaseModel):
    status: str
    response: str
    session_id: str
    tokens_used: int = 0


class MessageItem(BaseModel):
    role: str
    content: str


class StreamRequest(BaseModel):
    messages: List[MessageItem]
    workspace_id: str = "default"


@router.post("/chat")
async def chat(request: ChatRequest):
    from backend.api.app import get_memory_manager, get_context_manager, get_llm_client

    try:
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()
        llm = get_llm_client()

        session_id = request.session_id or context_mgr.create_session(
            workspace_id=request.workspace_id
        )

        context_mgr.add_message(
            session_id=session_id,
            role="user",
            content=request.message
        )

        messages = context_mgr.get_messages(session_id, limit=10)

        if request.use_memory:
            from backend.core.memory.router import MemoryRouter
            router = MemoryRouter(memory_manager=memory_mgr)
            routing_result = await router.route(
                query=request.message,
                session_id=session_id,
                scene_type="chat"
            )
            memory_context = "\n".join([
                f"[记忆] {m['content']}"
                for m in routing_result.memories[:5]
            ])
            messages = [{"role": "system", "content": f"相关记忆:\n{memory_context}"}] + messages

        response = await llm.chat(
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            stream=False
        )

        context_mgr.add_message(
            session_id=session_id,
            role="assistant",
            content=response.content
        )

        return {
            "status": "success",
            "response": response.content,
            "session_id": session_id,
            "tokens_used": response.usage.get("total_tokens", 0) if response.usage else 0
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    from backend.api.app import get_context_manager, get_llm_client

    try:
        context_mgr = get_context_manager()
        llm = get_llm_client()

        session_id = request.session_id or context_mgr.create_session(
            workspace_id=request.workspace_id
        )

        context_mgr.add_message(
            session_id=session_id,
            role="user",
            content=request.message
        )

        messages = context_mgr.get_messages(session_id, limit=10)

        return {"status": "success", "session_id": session_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, limit: int = 50):
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        messages = context_mgr.get_messages(session_id, limit=limit)
        return {
            "status": "success",
            "session_id": session_id,
            "messages": messages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
