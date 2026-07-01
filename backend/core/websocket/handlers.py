import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core.logging_config import get_contextual_logger

from .manager import get_websocket_manager

from backend.core.chat.stream import ChatStreamState, generate_chat_stream

logger = get_contextual_logger(__name__)

# 内置工具名称集合，用于区分内置工具和注册工具
from backend.core.tools.builtin import BUILTIN_TOOL_NAMES


class ChatWebSocketHandler:
    """聊天 WebSocket 处理器

    处理通过 WebSocket 的实时聊天消息
    """

    def __init__(self):
        self.ws_manager = get_websocket_manager()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._cancel_flags: Dict[str, bool] = {}
        self._register_handlers()

    def _register_handlers(self):
        """注册消息处理器"""
        self.ws_manager.register_handler("chat", self._handle_chat)
        self.ws_manager.register_handler("chat_stream", self._handle_chat_stream)
        self.ws_manager.register_handler("subscribe", self._handle_subscribe)
        self.ws_manager.register_handler("unsubscribe", self._handle_unsubscribe)
        self.ws_manager.register_handler("ping", self._handle_ping)
        self.ws_manager.register_handler("cancel", self._handle_cancel)
        self.ws_manager.register_handler("config", self._handle_config)

    async def _prepare_chat(
        self, client_id: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """准备聊天所需的上下文，返回准备结果或 None（出错时已发送错误消息）"""
        from backend.api.app import get_context_manager, get_memory_manager
        from backend.api.routers.chat import (
            build_messages,
            get_agent_config,
            get_llm_client_for_agent,
        )

        agent_id = message.get("agent_id", "default")
        session_id = message.get("session_id")
        user_message = message.get("message", "")

        if not user_message:
            await self.ws_manager.send_to_client(
                client_id, {"type": "error", "error": "消息不能为空"}
            )
            return None

        # 获取配置
        agent_config = get_agent_config(agent_id)
        if not agent_config:
            await self.ws_manager.send_to_client(
                client_id, {"type": "error", "error": f"Agent '{agent_id}' 不存在"}
            )
            return None

        # 获取管理器
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()
        llm = get_llm_client_for_agent(agent_config)

        # 获取/创建 Agent 专属会话（每个 Agent 只有一个会话，与 HTTP 端点一致）
        session_id = session_id or f"agent-{agent_id}"
        existing_session = context_mgr.get_session(session_id)
        if not existing_session:
            context_mgr.create_session(
                workspace_id="default",
                title=f"与 {agent_config['name']} 的对话",
                session_id=session_id,
                metadata={"agent_id": agent_id},
            )

        # 检索记忆
        memory_context = None
        if agent_config.get("use_memory", True) and memory_mgr:
            from backend.core.memory.router import MemoryRouter

            router = MemoryRouter(memory_manager=memory_mgr)
            routing_result = await router.route(
                query=user_message,
                session_id=session_id,
                scene_type=agent_config.get("memory_scene", "chat"),
            )
            if routing_result.memories:
                memory_context = "\n".join(
                    [f"- {m['content']}" for m in routing_result.memories[:agent_config.get("memory_context_limit", 5)]]
                )

        # 构建消息列表（在 add_message 之前，避免当前用户消息重复）
        messages = build_messages(
            agent_config=agent_config,
            context_mgr=context_mgr,
            session_id=session_id,
            user_message=user_message,
            memory_context=memory_context,
        )

        # 添加用户消息到上下文（在构建消息之后，避免历史中重复）
        await context_mgr.add_message_async(session_id=session_id, role="user", content=user_message)

        # 获取工具（只过滤 summary 类别）
        from backend.core.tools import tool_registry
        from backend.core.tools.builtin import get_builtin_tools

        builtin_tools = get_builtin_tools()

        EXCLUDED_CATEGORIES = {"summary"}
        main_tool_names = {
            "write_long_term_memory",
            "search_all_memories",
            "call_assistant",
            "set_alarm",
            "mono",
            "write_permanent_memory",
            "acp_list_agents",
            "acp_connect",
            "acp_disconnect",
            "acp_send_message",
            "acp_create_group",
            "acp_join_group",
            "acp_leave_group",
        }
        main_tools = []
        for tool_name in main_tool_names:
            tool = tool_registry.get_tool(tool_name)
            if tool and tool.enabled and tool.category not in EXCLUDED_CATEGORIES:
                main_tools.append(tool.to_openai_function())

        tools = builtin_tools + main_tools

        logger.info(
            f"为 Agent '{agent_config.get('name')}' 配置了 {len(tools)} 个工具: {[t['function']['name'] for t in tools]}"
        )

        return {
            "agent_config": agent_config,
            "session_id": session_id,
            "context_mgr": context_mgr,
            "llm": llm,
            "messages": messages,
            "tools": tools,
        }

    async def _stream_chat_to_client(
        self,
        client_id: str,
        llm,
        messages: List[Dict],
        agent_config: Dict,
        tools: List[Dict],
        context_mgr,
        session_id: str,
    ):
        """核心流式聊天逻辑：消费共享聊天流生成器，通过 WebSocket 发送事件"""
        state = ChatStreamState()

        def is_cancelled():
            return self._cancel_flags.get(client_id, False)

        try:
            async for event in generate_chat_stream(
                llm=llm,
                messages=messages,
                agent_config=agent_config,
                tools=tools,
                session_id=session_id,
                state=state,
                is_cancelled=is_cancelled,
            ):
                if event.get("type") == "session":
                    continue  # already sent early in _handle_chat
                await self.ws_manager.send_to_client(client_id, event)

                # 取消事件后保存部分响应并退出
                if event.get("type") == "cancelled":
                    await self._save_assistant_message(
                        context_mgr,
                        session_id,
                        state.accumulated_response,
                        state.full_thinking,
                        state.tool_calls,
                    )
                    return

        except Exception as e:
            logger.error(f"流式聊天错误: {e}", exc_info=True)
            # 保存已生成的部分响应（避免刷新或断连时丢失）
            await self._save_assistant_message(
                context_mgr,
                session_id,
                state.accumulated_response,
                state.full_thinking,
                state.tool_calls,
            )
            try:
                await self.ws_manager.send_to_client(
                    client_id, {"type": "error", "error": str(e)}
                )
            except Exception:
                pass
            return

        # 正常结束后保存完整响应
        await self._save_assistant_message(
            context_mgr,
            session_id,
            state.accumulated_response,
            state.full_thinking,
            state.tool_calls,
        )

    async def _save_assistant_message(
        self, context_mgr, session_id: str, content: str, thinking: str, tool_calls: List[Dict]
    ):
        """保存助手消息到上下文（包括 thinking 和工具调用信息）"""
        if not content and not tool_calls:
            return
        metadata = {}
        if thinking:
            metadata["thinking"] = thinking
        if tool_calls:
            metadata["tool_calls"] = tool_calls
        try:
            await context_mgr.add_message_async(
                session_id=session_id,
                role="assistant",
                content=content,
                metadata=metadata,
            )
        except Exception as e:
            logger.warning(f"保存助手消息失败: {e}")

    async def _handle_chat(self, client_id: str, message: Dict[str, Any]):
        """处理普通聊天消息（使用流式响应）"""
        try:
            self._cancel_flags[client_id] = False
            # Send session event immediately (before slow prep) so frontend shows "thinking"
            agent_id = message.get("agent_id", "default")
            early_session_id = message.get("session_id") or f"agent-{agent_id}"
            await self.ws_manager.send_to_client(
                client_id, {"type": "session", "session_id": early_session_id}
            )
            prep = await self._prepare_chat(client_id, message)
            if prep is None:
                return
            await self._stream_chat_to_client(
                client_id=client_id,
                llm=prep["llm"],
                messages=prep["messages"],
                agent_config=prep["agent_config"],
                tools=prep["tools"],
                context_mgr=prep["context_mgr"],
                session_id=prep["session_id"],
            )
        except Exception as e:
            logger.error(f"处理聊天消息失败: {e}")
            await self.ws_manager.send_to_client(client_id, {"type": "error", "error": str(e)})

    async def _handle_chat_stream(self, client_id: str, message: Dict[str, Any]):
        """处理流式聊天消息"""
        try:
            self._cancel_flags[client_id] = False
            # Send session event immediately (before slow prep) so frontend shows "thinking"
            agent_id = message.get("agent_id", "default")
            early_session_id = message.get("session_id") or f"agent-{agent_id}"
            await self.ws_manager.send_to_client(
                client_id, {"type": "session", "session_id": early_session_id}
            )
            prep = await self._prepare_chat(client_id, message)
            if prep is None:
                return
            await self._stream_chat_to_client(
                client_id=client_id,
                llm=prep["llm"],
                messages=prep["messages"],
                agent_config=prep["agent_config"],
                tools=prep["tools"],
                context_mgr=prep["context_mgr"],
                session_id=prep["session_id"],
            )
        except Exception as e:
            logger.error(f"处理流式聊天消息失败: {e}")
            await self.ws_manager.send_to_client(client_id, {"type": "error", "error": str(e)})

    async def _handle_subscribe(self, client_id: str, message: Dict[str, Any]):
        """处理订阅请求"""
        channel = message.get("channel", "")
        if channel:
            self.ws_manager.subscribe_to_channel(client_id, channel)
            await self.ws_manager.send_to_client(
                client_id, {"type": "subscribed", "channel": channel}
            )

    async def _handle_unsubscribe(self, client_id: str, message: Dict[str, Any]):
        """处理取消订阅请求"""
        channel = message.get("channel", "")
        if channel:
            self.ws_manager.unsubscribe_from_channel(client_id, channel)
            await self.ws_manager.send_to_client(
                client_id, {"type": "unsubscribed", "channel": channel}
            )

    async def _handle_ping(self, client_id: str, message: Dict[str, Any]):
        """处理心跳"""
        await self.ws_manager.send_to_client(
            client_id, {"type": "pong", "timestamp": datetime.now().isoformat()}
        )

    async def _handle_cancel(self, client_id: str, message: Dict[str, Any]):
        """处理取消响应请求"""
        logger.info(f"客户端 {client_id} 请求取消响应")
        self._cancel_flags[client_id] = True
        await self.ws_manager.send_to_client(
            client_id, {"type": "cancelled", "timestamp": datetime.now().isoformat()}
        )

    async def _handle_config(self, client_id: str, message: Dict[str, Any]):
        """处理配置更新"""
        if "timeout" in message:
            timeout = message["timeout"]
            if client_id in self.ws_manager.connections:
                self.ws_manager.connections[client_id].metadata["timeout"] = timeout
            await self.ws_manager.send_to_client(
                client_id, {"type": "config_updated", "timeout": timeout}
            )


async def push_alarm_to_agent(agent_id: str, alarm_message: str):
    """向指定 Agent 推送提醒消息"""
    from .manager import get_websocket_manager

    ws_manager = get_websocket_manager()

    await ws_manager.broadcast_to_channel(
        f"agent:{agent_id}",
        {"type": "alarm", "message": alarm_message, "triggered_at": datetime.now().isoformat()},
    )
    logger.info(f"已向 Agent {agent_id} 推送提醒: {alarm_message}")


# 全局处理器实例
_chat_handler: Optional[ChatWebSocketHandler] = None


def get_chat_handler() -> ChatWebSocketHandler:
    """获取全局聊天处理器实例"""
    global _chat_handler
    if _chat_handler is None:
        _chat_handler = ChatWebSocketHandler()
    return _chat_handler
