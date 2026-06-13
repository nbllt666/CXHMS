"""CXHMS API client for end-to-end testing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx


@dataclass
class StreamResponse:
    """Accumulated result of a streaming chat request."""

    session_id: str = ""
    content: str = ""
    thinking: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    ttft_ms: float = 0.0
    total_time_ms: float = 0.0
    tokens_count: int = 0
    tps: float = 0.0


class CXHMSClient:
    """Async HTTP client wrapping the CXHMS API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            trust_env=False,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "CXHMSClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _parse_sse_stream(self, response: httpx.Response) -> StreamResponse:
        """Parse an SSE stream from a streaming response and return a StreamResponse."""
        result = StreamResponse()
        start_time = time.monotonic()
        first_content_time: float | None = None
        content_chunk_count = 0

        buffer = ""
        async for raw_chunk in response.aiter_text():
            buffer += raw_chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                for line in event_block.splitlines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    msg_type = data.get("type", "")

                    if msg_type == "session":
                        result.session_id = data.get("session_id", "")

                    elif msg_type == "thinking":
                        result.thinking += data.get("content", "")

                    elif msg_type == "content":
                        if first_content_time is None:
                            first_content_time = time.monotonic()
                        result.content += data.get("content", "")
                        content_chunk_count += 1

                    elif msg_type == "tool_call":
                        result.tool_calls.append(data.get("tool_call", {}))

                    elif msg_type == "tool_start":
                        # Record tool invocation start (informational)
                        pass

                    elif msg_type == "tool_result":
                        result.tool_results.append(
                            {
                                "tool_name": data.get("tool_name", ""),
                                "result": data.get("result"),
                            }
                        )

                    elif msg_type == "error":
                        # Surface error in content so callers can inspect it
                        result.content += f"\n[ERROR] {data.get('error', 'unknown')}"

                    elif msg_type == "done":
                        pass  # stream finished normally

        end_time = time.monotonic()
        result.total_time_ms = (end_time - start_time) * 1000

        if first_content_time is not None:
            result.ttft_ms = (first_content_time - start_time) * 1000

        result.tokens_count = content_chunk_count
        if result.total_time_ms > 0:
            result.tps = (content_chunk_count / result.total_time_ms) * 1000

        return result

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def check_health(self) -> dict:
        """GET /health — check service health."""
        resp = await self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    async def chat_stream(
        self,
        message: str,
        agent_id: str = "default",
    ) -> StreamResponse:
        """POST /api/chat/stream — streaming chat request."""
        resp = await self._client.post(
            "/api/chat/stream",
            json={"message": message, "agent_id": agent_id},
        )
        resp.raise_for_status()
        return await self._parse_sse_stream(resp)

    async def chat_with_fallback(
        self,
        message: str,
        agent_id: str = "default",
    ) -> StreamResponse:
        """POST /api/chat/stream with fallback to non-streaming if stream returns empty.

        Tries streaming first. If the stream returns empty content (which can happen
        when vLLM doesn't support tool calling in streaming mode), falls back to
        the non-streaming /api/chat endpoint.
        """
        resp = await self.chat_stream(message, agent_id=agent_id)

        # If stream returned meaningful content, return it
        if resp.content and resp.content.strip():
            return resp

        # If stream returned tool calls or tool results, return it
        if resp.tool_calls or resp.tool_results:
            return resp

        # Fallback to non-streaming chat
        try:
            data = await self.chat(message, agent_id=agent_id)
            content = data.get("response", "")
            session_id = data.get("session_id", resp.session_id)

            return StreamResponse(
                session_id=session_id,
                content=content,
                ttft_ms=0.0,
                total_time_ms=resp.total_time_ms,
                tokens_count=0,
                tps=0.0,
            )
        except Exception:
            # If fallback also fails, return the original (empty) response
            return resp

    async def chat(self, message: str, agent_id: str = "default") -> dict:
        """POST /api/chat — non-streaming chat request."""
        resp = await self._client.post(
            "/api/chat",
            json={"message": message, "agent_id": agent_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_chat_history(self, session_id: str, limit: int = 50) -> dict:
        """GET /api/chat/history/{session_id} — retrieve chat history."""
        resp = await self._client.get(
            f"/api/chat/history/{session_id}",
            params={"limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    async def search_memories(self, query: str, limit: int = 10) -> dict:
        """POST /api/memories/search — search memories."""
        resp = await self._client.post(
            "/api/memories/search",
            json={"query": query, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_memory(self, memory_id: str) -> dict:
        """GET /api/memories/{memory_id} — retrieve a single memory."""
        resp = await self._client.get(f"/api/memories/{memory_id}")
        resp.raise_for_status()
        return resp.json()

    async def list_memories(self, limit: int = 20) -> dict:
        """GET /api/memories — list memories."""
        resp = await self._client.get("/api/memories", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    async def list_tools(self) -> dict:
        """GET /api/tools — list available tools."""
        resp = await self._client.get("/api/tools")
        resp.raise_for_status()
        return resp.json()

    async def memory_agent_chat_stream(self, message: str) -> StreamResponse:
        """POST /api/memory-agent/chat/stream — streaming memory-agent chat."""
        resp = await self._client.post(
            "/api/memory-agent/chat/stream",
            json={"message": message},
        )
        resp.raise_for_status()
        return await self._parse_sse_stream(resp)

    async def memory_agent_chat_with_fallback(self, message: str) -> StreamResponse:
        """POST /api/memory-agent/chat/stream with fallback for empty content."""
        resp = await self.memory_agent_chat_stream(message)

        if resp.content and resp.content.strip():
            return resp
        if resp.tool_calls or resp.tool_results:
            return resp

        # No non-streaming fallback for memory-agent, return as-is
        return resp

    async def get_agents(self) -> dict:
        """GET /api/agents — list agents."""
        resp = await self._client.get("/api/agents")
        resp.raise_for_status()
        return resp.json()

    async def get_stats(self) -> dict:
        """GET /api/stats — get service statistics."""
        resp = await self._client.get("/api/stats")
        resp.raise_for_status()
        return resp.json()
