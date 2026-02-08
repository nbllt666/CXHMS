"""
WebSocket 路由 - 提供实时双向通信
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional

from backend.core.websocket import get_websocket_manager, get_chat_handler
from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = None,
    token: Optional[str] = None
):
    """
    WebSocket 连接端点
    
    支持实时聊天、消息订阅、心跳检测等功能
    
    Query 参数:
    - client_id: 客户端ID（可选，不传则自动生成）
    - token: 认证令牌（可选）
    """
    ws_manager = get_websocket_manager()
    chat_handler = get_chat_handler()
    
    # 建立连接
    connection = await ws_manager.connect(
        websocket=websocket,
        client_id=client_id,
        metadata={"token": token} if token else {}
    )
    
    client_id = connection.client_id
    
    try:
        # 保持连接并处理消息
        while True:
            # 接收消息
            message = await connection.receive()
            
            # 处理消息
            await ws_manager.handle_message(client_id, message)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket 客户端断开连接: {client_id}")
        await ws_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket 错误 {client_id}: {e}")
        await ws_manager.disconnect(client_id)


@router.websocket("/ws/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = "default"
):
    """
    WebSocket 聊天专用端点
    
    简化版聊天连接，自动订阅到指定会话
    
    Query 参数:
    - session_id: 会话ID（可选）
    - agent_id: Agent ID（可选，默认 default）
    """
    ws_manager = get_websocket_manager()
    chat_handler = get_chat_handler()
    
    # 建立连接
    connection = await ws_manager.connect(
        websocket=websocket,
        metadata={
            "session_id": session_id,
            "agent_id": agent_id
        }
    )
    
    client_id = connection.client_id
    
    # 如果有会话ID，订阅到该会话频道
    if session_id:
        ws_manager.subscribe_to_channel(client_id, f"session:{session_id}")
    
    try:
        while True:
            message = await connection.receive()
            
            # 自动添加会话和Agent信息
            if "session_id" not in message and session_id:
                message["session_id"] = session_id
            if "agent_id" not in message and agent_id:
                message["agent_id"] = agent_id
            
            await ws_manager.handle_message(client_id, message)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket 聊天客户端断开连接: {client_id}")
        await ws_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket 聊天错误 {client_id}: {e}")
        await ws_manager.disconnect(client_id)
