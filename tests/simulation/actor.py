"""无头用户演员：封装真实前端对后端 API 的调用模式。

``SimUserActor`` 在端到端测试中扮演"真实用户"，通过 FastAPI ``TestClient``
驱动后端真实路由（含流式 SSE、工具调用循环、上下文持久化等），
让测试可以以业务语义而非裸 HTTP 调用编写断言。

设计要点：
    - 所有路径与请求字段严格对齐真实路由 ``backend/api/routers/*.py``。
    - 流式接口聚合 SSE 事件为可断言的结构体（content 拼接、tool_calls 列表等）。
    - 错误时抛出带响应 body 的 ``RuntimeError``，便于测试定位失败原因。

核对到的真实 API 形态（``/api`` 前缀由 ``backend/api/app.py`` ``include_router`` 注入）：

    POST /api/chat
        body: {"message": str, "agent_id": str="default", "stream": bool=False, "images": list?}
        -> 200 {"status": str, "response": str, "session_id": str, "tokens_used": int}
        注：chat 路由内部使用 ``f"agent-{agent_id}"`` 作为会话 id，请求体里的
        session_id 不被消费——前端同样不发送，actor 也保持该行为。

    POST /api/chat/stream
        body: {"message": str, "agent_id": str="default"}
        -> SSE，每行 ``data: {json}\\n\\n``，json.type 取值：
           session(thinking/content/tool_call/tool_start/tool_result/done/error)

    POST /api/memory-agent/chat/stream
        body: {"message": str}
        -> SSE（同 /api/chat/stream 格式）

    GET  /api/chat/history/{session_id}?limit=N
        -> {"status":"success","session_id":str,"session":obj,"messages":[...]}

    POST /api/memories/search
        body: MemorySearchRequest{query, type?, memory_type?, tags?, time_range?:str,
              limit=10, offset=0, include_deleted=False, workspace_id, agent_id}
        -> {"status":"success","memories":[...],"total":int}

    GET  /api/agents            -> {"status":"success","agents":[...],"total":int}
    POST /api/agents            -> {"status":"success","agent":{...},"message":str}
    GET  /api/tools             -> {"status":"success","tools":{name:tool},"statistics":{}}
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional


class SimUserActor:
    """无头用户演员：封装前端对后端聊天/记忆/Agent/工具 API 的调用。

    Args:
        client: FastAPI ``TestClient`` 实例（通常由 ``sim_client`` fixture 提供）。
    """

    # 真实路由前缀（app.py 中 ``include_router(..., prefix="/api")``）
    _PREFIX = "/api"

    def __init__(self, client) -> None:
        self.client = client

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #

    @staticmethod
    def new_session_id(prefix: str = "sim-") -> str:
        """生成随机会话 id（uuid4 hex），便于测试隔离。

        注：当前 ``/api/chat`` 路由内部使用 ``f"agent-{agent_id}"`` 作为会话 id，
        该方法返回值不会直接影响聊天会话，但可用于记忆/上下文相关测试的标识。
        """
        return f"{prefix}{uuid.uuid4().hex}"

    @staticmethod
    def _raise(method: str, url: str, status_code: int, body: str) -> None:
        raise RuntimeError(
            f"{method} {url} 失败: status={status_code}, body={body!r}"
        )

    def _decode_line(self, line: Any) -> str:
        """把 iter_lines 返回的 bytes/str 统一为 str。"""
        if isinstance(line, bytes):
            return line.decode("utf-8", errors="replace")
        return line

    def _consume_sse_stream(
        self, method: str, url: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """消费 SSE 流并聚合为结构化结果。

        返回结构：
            {
                "session_id":   str,            # 来自 session/done 事件
                "content":      str,            # 所有 content 事件拼接
                "thinking":     str,            # 所有 thinking 事件拼接
                "tool_calls":   [tool_call, …], # 来自 tool_call 事件
                "tool_results": [{tool_name, result}, …],  # 来自 tool_result 事件
                "events":       [原始事件 dict, …],        # 所有解析到的事件
                "raw":          bool,           # 是否收到过任何事件
                "error":        Optional[str],  # 来自 error 事件
            }
        """
        result: Dict[str, Any] = {
            "session_id": "",
            "content": "",
            "thinking": "",
            "tool_calls": [],
            "tool_results": [],
            "events": [],
            "raw": False,
            "error": None,
        }

        with self.client.stream(method, url, json=body) as resp:
            if resp.status_code != 200:
                # 读取 body 以便在异常中带上详情
                try:
                    resp.read()
                except Exception:
                    pass
                self._raise(method, url, resp.status_code, resp.text)

            for raw_line in resp.iter_lines():
                line = self._decode_line(raw_line)
                if not line or not line.startswith("data: "):
                    # SSE 块之间会有空行；非 data 行忽略
                    continue
                payload = line[len("data: "):]
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    # 非 JSON 的 data 行（极少见），跳过
                    continue
                if not isinstance(event, dict):
                    continue

                result["events"].append(event)
                result["raw"] = True

                etype = event.get("type")
                if etype == "session":
                    if event.get("session_id"):
                        result["session_id"] = event["session_id"]
                elif etype == "thinking":
                    result["thinking"] += event.get("content", "") or ""
                elif etype == "content":
                    result["content"] += event.get("content", "") or ""
                elif etype == "tool_call":
                    result["tool_calls"].append(event.get("tool_call"))
                elif etype == "tool_start":
                    # tool_start 与 tool_result 配对出现；tool_name 已在 tool_result 中
                    pass
                elif etype == "tool_result":
                    result["tool_results"].append(
                        {
                            "tool_name": event.get("tool_name"),
                            "result": event.get("result"),
                        }
                    )
                elif etype == "done":
                    # done 事件携带 session_id，作为 session 事件的兜底
                    if event.get("session_id") and not result["session_id"]:
                        result["session_id"] = event["session_id"]
                elif etype == "error":
                    result["error"] = event.get("error")

        return result

    # ------------------------------------------------------------------ #
    # 聊天 API
    # ------------------------------------------------------------------ #

    def send_message(
        self,
        message: str,
        agent_id: str = "default",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """非流式聊天：POST /api/chat。

        Args:
            message: 用户消息文本。
            agent_id: 使用的 Agent id（决定后端 system prompt / 模型 / 工具集）。
            session_id: 当前路由不消费该字段（chat.py 内部使用 ``agent-{agent_id}``），
                保留参数以匹配前端 actor 契约与未来扩展。

        Returns:
            后端返回的 dict：``{"status","response","session_id","tokens_used"}``。
        """
        body: Dict[str, Any] = {
            "message": message,
            "agent_id": agent_id,
            "stream": False,
        }
        url = f"{self._PREFIX}/chat"
        resp = self.client.post(url, json=body)
        if resp.status_code != 200:
            self._raise("POST", url, resp.status_code, resp.text)
        return resp.json()

    def send_streaming_message(
        self,
        message: str,
        agent_id: str = "default",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """流式聊天：POST /api/chat/stream。

        Args:
            message: 用户消息文本。
            agent_id: 使用的 Agent id。
            session_id: 当前路由不消费该字段（chat.py 内部使用 ``agent-{agent_id}``），
                但同一 agent_id 的多次调用会共享后端 context_manager 历史，
                因此多轮上下文依然保持。

        Returns:
            聚合后的 SSE 结果（见 ``_consume_sse_stream``）。
        """
        body: Dict[str, Any] = {"message": message, "agent_id": agent_id}
        url = f"{self._PREFIX}/chat/stream"
        return self._consume_sse_stream("POST", url, body)

    def memory_agent_chat(self, message: str) -> Dict[str, Any]:
        """记忆管理模型流式聊天：POST /api/memory-agent/chat/stream。

        后端固定使用会话 ``memory-agent-default``，故无需 agent_id/session_id。

        Args:
            message: 用户消息文本。

        Returns:
            聚合后的 SSE 结果（见 ``_consume_sse_stream``）。
        """
        body: Dict[str, Any] = {"message": message}
        url = f"{self._PREFIX}/memory-agent/chat/stream"
        return self._consume_sse_stream("POST", url, body)

    # ------------------------------------------------------------------ #
    # 历史 API
    # ------------------------------------------------------------------ #

    def get_history(
        self, session_id: str, limit: int = 50
    ) -> Dict[str, Any]:
        """获取聊天历史：GET /api/chat/history/{session_id}?limit=N。

        Returns:
            后端返回的 dict：``{"status","session_id","session","messages"}``。
        """
        url = f"{self._PREFIX}/chat/history/{session_id}"
        resp = self.client.get(url, params={"limit": limit})
        if resp.status_code != 200:
            self._raise("GET", url, resp.status_code, resp.text)
        return resp.json()

    # ------------------------------------------------------------------ #
    # 记忆 API
    # ------------------------------------------------------------------ #

    def search_memory(
        self,
        query: str,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """搜索记忆：POST /api/memories/search。

        请求体对齐 ``MemorySearchRequest``（``memory.py``）：
        支持 ``query`` / ``memory_type`` / ``type`` / ``tags`` / ``time_range`` /
        ``limit`` / ``offset`` 等字段。这里只暴露最常用的子集。

        Returns:
            记忆列表（取响应 ``memories`` 字段；找不到时回退到 ``data``/``items``）。
        """
        body: Dict[str, Any] = {"query": query, "limit": limit}
        if memory_type is not None:
            body["memory_type"] = memory_type
        if tags is not None:
            body["tags"] = tags

        url = f"{self._PREFIX}/memories/search"
        resp = self.client.post(url, json=body)
        if resp.status_code != 200:
            self._raise("POST", url, resp.status_code, resp.text)
        data = resp.json()
        # memory.py 返回 {"status","memories","total"}；做字段兜底以应对变体
        if isinstance(data, list):
            return data
        for key in ("memories", "data", "items", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return []

    # ------------------------------------------------------------------ #
    # Agent API
    # ------------------------------------------------------------------ #

    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有 Agent：GET /api/agents。

        Returns:
            Agent 配置列表（取响应 ``agents`` 字段）。
        """
        url = f"{self._PREFIX}/agents"
        resp = self.client.get(url)
        if not (200 <= resp.status_code < 300):
            self._raise("GET", url, resp.status_code, resp.text)
        data = resp.json()
        agents = data.get("agents", [])
        return agents if isinstance(agents, list) else []

    def create_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """创建 Agent：POST /api/agents。

        请求体对齐 ``AgentCreateRequest``（``agents.py``）：
        ``{name, description?, system_prompt?, model?, temperature?, max_tokens?,
          use_memory?, use_tools?, memory_scene?, decay_model?, vision_enabled?}``。

        Returns:
            后端返回的 dict：``{"status","agent":{...},"message"}``。
        """
        url = f"{self._PREFIX}/agents"
        resp = self.client.post(url, json=payload)
        if not (200 <= resp.status_code < 300):
            self._raise("POST", url, resp.status_code, resp.text)
        return resp.json()

    # ------------------------------------------------------------------ #
    # 工具 API
    # ------------------------------------------------------------------ #

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出工具：GET /api/tools。

        后端 ``tools.py`` 返回 ``{"status","tools":{name:tool},"statistics":{}}``，
        其中 ``tools`` 是 dict。为方便断言统一返回 ``list(tools.values())``。

        Returns:
            工具配置列表（dict.values 形态）。
        """
        url = f"{self._PREFIX}/tools"
        resp = self.client.get(url)
        if not (200 <= resp.status_code < 300):
            self._raise("GET", url, resp.status_code, resp.text)
        data = resp.json()
        tools = data.get("tools", {})
        if isinstance(tools, dict):
            return list(tools.values())
        if isinstance(tools, list):
            return tools
        return []
