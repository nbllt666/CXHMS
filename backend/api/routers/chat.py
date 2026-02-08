"""
聊天路由 - 支持 Agent 的聊天 API
前端只发送最新一条消息，后端根据 Agent 配置构建完整上下文
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, List, Optional
from pydantic import BaseModel
import json

from backend.api.routers.agents import _load_agents

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求 - 前端只发送最新一条消息"""
    message: str              # 用户最新消息
    agent_id: str = "default" # 使用哪个 Agent
    session_id: Optional[str] = None  # 会话ID，不传则创建新会话
    stream: bool = True       # 是否流式响应


class ChatResponse(BaseModel):
    """聊天响应"""
    status: str
    response: str
    session_id: str
    tokens_used: int = 0


def get_agent_config(agent_id: str) -> Optional[dict]:
    """获取 Agent 配置"""
    agents = _load_agents()
    return next((a for a in agents if a["id"] == agent_id), None)


def get_llm_client_for_agent(agent_config: dict):
    """根据 Agent 配置获取 LLM 客户端"""
    from backend.api.app import get_model_router, get_llm_client

    model = agent_config.get("model", "main")

    try:
        model_router = get_model_router()

        # 如果是模型类型 (main/summary/memory)，从 router 获取
        if model.lower() in ['main', 'summary', 'memory']:
            client = model_router.get_client(model.lower())
            if client:
                return client
        else:
            # 具体模型名，创建新客户端
            main_client = model_router.get_client('main')
            if main_client:
                from backend.core.llm.client import OllamaClient
                return OllamaClient(
                    host=main_client.host,
                    model=model,
                    temperature=agent_config.get("temperature", 0.7),
                    max_tokens=agent_config.get("max_tokens", 4096)
                )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to create client for model {model}: {e}")

    # 默认使用全局 llm_client
    return get_llm_client()


def build_messages(
    agent_config: dict,
    context_mgr,
    session_id: str,
    user_message: str,
    memory_context: Optional[str] = None
) -> List[Dict[str, str]]:
    """构建消息列表"""
    messages = []

    # 1. 系统提示词
    system_prompt = agent_config.get("system_prompt", "")
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # 2. 记忆上下文（如果启用记忆且有相关记忆）
    if memory_context and agent_config.get("use_memory", True):
        messages.append({"role": "system", "content": f"相关记忆:\n{memory_context}"})

    # 3. 历史消息（最近10条）
    history = context_mgr.get_messages(session_id, limit=10)
    for msg in history:
        if msg.get("role") in ["user", "assistant"]:
            messages.append({
                "role": msg["role"],
                "content": msg.get("content", "")
            })

    # 4. 用户最新消息
    messages.append({"role": "user", "content": user_message})

    return messages


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    非流式聊天
    前端只发送最新消息，后端根据 Agent 配置构建完整上下文
    """
    from backend.api.app import get_memory_manager, get_context_manager

    try:
        # 1. 获取 Agent 配置
        agent_config = get_agent_config(request.agent_id)
        if not agent_config:
            raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' 不存在")

        # 2. 获取管理器
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()
        llm = get_llm_client_for_agent(agent_config)

        # 3. 获取/创建会话
        if request.session_id:
            session_id = request.session_id
            # 确保会话存在
            try:
                context_mgr.get_session(session_id)
            except:
                raise HTTPException(status_code=404, detail=f"会话 '{request.session_id}' 不存在")
        else:
            session_id = context_mgr.create_session(
                workspace_id="default",
                title=f"与 {agent_config['name']} 的对话"
            )

        # 4. 添加用户消息到上下文
        context_mgr.add_message(
            session_id=session_id,
            role="user",
            content=request.message
        )

        # 5. 检索记忆（如果启用）
        memory_context = None
        if agent_config.get("use_memory", True) and memory_mgr:
            from backend.core.memory.router import MemoryRouter
            router = MemoryRouter(memory_manager=memory_mgr)
            routing_result = await router.route(
                query=request.message,
                session_id=session_id,
                scene_type=agent_config.get("memory_scene", "chat")
            )
            if routing_result.memories:
                memory_context = "\n".join([
                    f"- {m['content']}"
                    for m in routing_result.memories[:5]
                ])

        # 6. 构建消息列表
        messages = build_messages(
            agent_config=agent_config,
            context_mgr=context_mgr,
            session_id=session_id,
            user_message=request.message,
            memory_context=memory_context
        )

        # 7. 调用 LLM
        response = await llm.chat(
            messages=messages,
            stream=False
        )

        # 8. 保存助手响应到上下文
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

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    流式聊天
    前端只发送最新消息，后端根据 Agent 配置构建完整上下文
    """
    from backend.api.app import get_memory_manager, get_context_manager

    try:
        # 1. 获取 Agent 配置
        agent_config = get_agent_config(request.agent_id)
        if not agent_config:
            raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' 不存在")

        # 2. 获取管理器
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()
        llm = get_llm_client_for_agent(agent_config)

        # 3. 获取/创建会话
        if request.session_id:
            session_id = request.session_id
            try:
                context_mgr.get_session(session_id)
            except:
                raise HTTPException(status_code=404, detail=f"会话 '{request.session_id}' 不存在")
        else:
            session_id = context_mgr.create_session(
                workspace_id="default",
                title=f"与 {agent_config['name']} 的对话"
            )

        # 4. 添加用户消息到上下文
        context_mgr.add_message(
            session_id=session_id,
            role="user",
            content=request.message
        )

        # 5. 检索记忆（如果启用）
        memory_context = None
        if agent_config.get("use_memory", True) and memory_mgr:
            from backend.core.memory.router import MemoryRouter
            router = MemoryRouter(memory_manager=memory_mgr)
            routing_result = await router.route(
                query=request.message,
                session_id=session_id,
                scene_type=agent_config.get("memory_scene", "chat")
            )
            if routing_result.memories:
                memory_context = "\n".join([
                    f"- {m['content']}"
                    for m in routing_result.memories[:5]
                ])

        # 6. 构建消息列表
        messages = build_messages(
            agent_config=agent_config,
            context_mgr=context_mgr,
            session_id=session_id,
            user_message=request.message,
            memory_context=memory_context
        )

        async def generate_stream():
            """生成流式响应"""
            full_response = ""

            # 发送会话ID作为第一个事件
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            try:
                # 调用LLM流式接口
                async for chunk in llm.stream_chat(
                    messages=messages,
                    temperature=agent_config.get("temperature", 0.7),
                    max_tokens=agent_config.get("max_tokens", 4096)
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

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, limit: int = 50):
    """获取聊天历史"""
    from backend.api.app import get_context_manager

    try:
        context_mgr = get_context_manager()
        messages = context_mgr.get_messages(session_id, limit=limit)
        session = context_mgr.get_session(session_id)

        return {
            "status": "success",
            "session_id": session_id,
            "session": session,
            "messages": messages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
