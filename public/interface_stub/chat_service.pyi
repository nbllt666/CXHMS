"""ChatService 接口契约存根。

对应 backend/api/routers/chat.py 的路由与 backend/core/chat/stream.py。
零实现逻辑，仅声明签名。模块实现必须严格匹配本存根。

@version 1.0.0
@see public/schema/message.json
"""

from typing import Any, AsyncIterator, Dict, List, Optional


class ChatService:
    """聊天服务接口。

    提供非流式/流式聊天、历史查询能力。支持 Agent 路由与上下文注入。
    """

    async def chat(
        self,
        message: str,
        agent_id: str = "default",
        stream: bool = True,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """非流式聊天，返回 {status, response, session_id, tokens_used}。

        Raises:
            LLMError: 模型调用失败
            AgentNotFoundError: agent_id 不存在
        """
        ...

    async def stream_chat(
        self,
        message: str,
        agent_id: str = "default",
        images: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """流式聊天，逐块 yield SSE 文本块。

        Raises:
            LLMError: 模型调用失败
            AgentNotFoundError: agent_id 不存在
        """
        ...

    async def get_chat_history(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取会话历史消息列表。

        Raises:
            SessionNotFoundError: session_id 不存在
        """
        ...

    async def memory_agent_stream_chat(
        self,
        message: str,
        agent_id: str = "memory-agent",
        images: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """记忆管理 Agent 流式聊天（带上下文持久化）。

        Raises:
            LLMError: 模型调用失败
        """
        ...

    async def summary_agent_stream_chat(
        self,
        message: str,
        agent_id: str = "summary-agent",
        images: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """摘要 Agent 流式聊天，自动调用 save_diary_entry 工具。

        Raises:
            LLMError: 模型调用失败
        """
        ...
