"""ChatService 预生成 Mock。

实现 public/interface_stub/chat_service.pyi 的全部签名，
返回符合 public/schema/message.json 契约的模拟值。
"""

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional


class MockChatService:
    """ChatService 的 Mock 实现。模拟流式与非流式响应。"""

    def __init__(self) -> None:
        self._histories: Dict[str, List[Dict]] = {}

    async def chat(
        self,
        message: str,
        agent_id: str = "default",
        stream: bool = True,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        session_id = "mock-session-001"
        response_text = f"[mock] 已收到你的消息：{message}"
        self._histories.setdefault(session_id, []).append(
            {
                "id": f"msg-{len(self._histories.get(session_id, []))}",
                "session_id": session_id,
                "role": "user",
                "content": message,
                "content_type": "text",
                "thinking": None,
                "tool_calls": None,
                "metadata": {},
                "tokens": len(message),
                "timestamp": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
                "is_deleted": False,
            }
        )
        return {
            "status": "success",
            "response": response_text,
            "session_id": session_id,
            "tokens_used": len(message) + len(response_text),
        }

    async def stream_chat(
        self,
        message: str,
        agent_id: str = "default",
        images: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        chunks = [f"[mock] ", "已", "收", "到", "：", message]
        for ch in chunks:
            await asyncio.sleep(0.01)
            yield ch

    async def get_chat_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._histories.get(session_id, []))[:limit]

    async def memory_agent_stream_chat(
        self,
        message: str,
        agent_id: str = "memory-agent",
        images: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        async for ch in self.stream_chat(message, agent_id=agent_id, images=images):
            yield ch

    async def summary_agent_stream_chat(
        self,
        message: str,
        agent_id: str = "summary-agent",
        images: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        async for ch in self.stream_chat(message, agent_id=agent_id, images=images):
            yield ch
