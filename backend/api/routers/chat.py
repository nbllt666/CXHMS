from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, List, Optional
from pydantic import BaseModel
import json

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
    """流式聊天响应"""
    from backend.api.app import get_context_manager, get_llm_client, get_memory_manager

    try:
        context_mgr = get_context_manager()
        llm = get_llm_client()
        memory_mgr = get_memory_manager()

        session_id = request.session_id or context_mgr.create_session(
            workspace_id=request.workspace_id
        )

        # 添加用户消息到上下文
        context_mgr.add_message(
            session_id=session_id,
            role="user",
            content=request.message
        )

        # 获取历史消息
        messages = context_mgr.get_messages(session_id, limit=10)
        formatted_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

        # 如果启用记忆，添加记忆上下文
        if request.use_memory and memory_mgr:
            from backend.core.memory.router import MemoryRouter
            memory_router = MemoryRouter(memory_manager=memory_mgr)
            routing_result = await memory_router.route(
                query=request.message,
                session_id=session_id,
                scene_type="chat"
            )
            if routing_result.memories:
                memory_context = "\n".join([
                    f"[记忆] {m['content']}"
                    for m in routing_result.memories[:5]
                ])
                formatted_messages = [
                    {"role": "system", "content": f"相关记忆:\n{memory_context}"}
                ] + formatted_messages

        async def generate_stream():
            """生成流式响应"""
            full_response = ""

            # 发送会话ID作为第一个事件
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            try:
                # 调用LLM流式接口
                async for chunk in llm.stream_chat(
                    messages=formatted_messages,
                    temperature=0.7,
                    max_tokens=4096
                ):
                    if chunk:
                        full_response += chunk
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                # 流结束，保存完整响应到上下文
                if full_response:
                    context_mgr.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=full_response
                    )

                # 发送完成事件
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

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
