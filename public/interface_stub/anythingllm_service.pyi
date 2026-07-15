"""AnythingLLMService 接口契约存根。

对应 backend/api/routers/anythingllm.py 的 11 个端点（Phase 1）。
零实现逻辑，仅声明签名。模块实现必须严格匹配本存根。

端点清单（11个）：
  1. GET  /v1/auth
  2. GET  /v1/openai/models
  3. POST /v1/openai/chat/completions
  4. GET  /v1/workspaces
  5. POST /v1/workspace/new
  6. GET  /v1/workspace/{slug}
  7. POST /v1/workspace/{slug}/update
  8. DELETE /v1/workspace/{slug}
  9. POST /v1/workspace/{slug}/chat
 10. POST /v1/workspace/{slug}/stream-chat
 11. GET  /v1/workspace/{slug}/chats

@version 1.1.0
@see public/schema/anythingllm_workspace.json
@see public/schema/openai_chat_completion.json
"""

from typing import Any, Dict, List, Optional

from fastapi import Header
from fastapi.responses import StreamingResponse


class AnythingLLMService:
    """AnythingLLM 兼容 API 服务接口。

    提供 AnythingLLM Developer API 兼容端点，将 CXHMS agents 映射为 workspaces。
    数据必须符合 public/schema/anythingllm_workspace.json 和 openai_chat_completion.json。
    """

    async def verify_api_key(self, authorization: Optional[str] = Header(None)) -> None:
        """验证 Bearer token。

        当 security.api_key_enabled=false 时直接放行。
        当 security.api_key_enabled=true 时校验 Authorization: Bearer <token>。

        Raises:
            HTTPException(403): token 不匹配或缺失（当 api_key_enabled=true 时）
        """
        ...

    async def auth(self) -> Dict[str, Any]:
        """GET /v1/auth — 验证 API token。

        Returns:
            {"authenticated": true}

        Raises:
            HTTPException(403): 未授权（由 verify_api_key 抛出）
        """
        ...

    async def list_models(self) -> Dict[str, Any]:
        """GET /v1/openai/models — 列出可用模型。

        Returns:
            {"object": "list", "data": [{"id": ..., "object": "model", "owned_by": "cxhms"}, ...]}
            包含 model_router 配置的模型 + agent:* 格式的 agent 列表
        """
        ...

    async def chat_completions(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """POST /v1/openai/chat/completions — OpenAI 兼容聊天补全。

        Args:
            request: {model, messages, stream, temperature, max_tokens}
            model 支持 "agent:<id>" 格式

        Returns:
            非流式: 标准 OpenAI ChatCompletion 响应（见 openai_chat_completion.json）
            流式: StreamingResponse (SSE)

        Raises:
            HTTPException(404): model="agent:<id>" 但 agent 不存在
            HTTPException(500): LLM 调用失败
        """
        ...

    async def list_workspaces(self) -> Dict[str, Any]:
        """GET /v1/workspaces — 列出所有 workspace。

        Returns:
            {"workspaces": [{"id", "name", "slug", "createdAt"}, ...]}
            slug = agent_id
        """
        ...

    async def create_workspace(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """POST /v1/workspace/new — 创建 workspace。

        Args:
            request: {"name": <workspace_name>}

        Returns:
            {"workspace": {"id", "name", "slug", "createdAt"}, "message": "..."}

        Raises:
            HTTPException(400): 名称重复
        """
        ...

    async def get_workspace(self, slug: str) -> Dict[str, Any]:
        """GET /v1/workspace/{slug} — 获取 workspace 详情。

        Args:
            slug: workspace slug（= agent_id）

        Returns:
            {"workspace": {"id", "name", "slug", "createdAt", "settings", "embedCount": 0}}

        Raises:
            HTTPException(404): slug 不存在
        """
        ...

    async def update_workspace(self, slug: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """POST /v1/workspace/{slug}/update — 更新 workspace 设置。

        Args:
            slug: workspace slug
            request: {"name": ..., "settings": ...}

        Returns:
            {"workspace": {...}, "message": "..."}

        Raises:
            HTTPException(404): slug 不存在
        """
        ...

    async def delete_workspace(self, slug: str) -> Dict[str, Any]:
        """DELETE /v1/workspace/{slug} — 删除 workspace。

        Args:
            slug: workspace slug

        Returns:
            {"success": true, "error": null}

        Raises:
            HTTPException(404): slug 不存在
            HTTPException(400): 试图删除默认 workspace
        """
        ...

    async def workspace_chat(self, slug: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """POST /v1/workspace/{slug}/chat — 非流式 workspace 聊天。

        Args:
            slug: workspace slug
            request: {"message": ..., "mode": "chat", "sessionId": ...}

        Returns:
            {"id": ..., "textResponse": ..., "sources": []}

        Raises:
            HTTPException(404): slug 不存在
            HTTPException(500): LLM 调用失败
        """
        ...

    async def workspace_stream_chat(self, slug: str, request: Dict[str, Any]) -> StreamingResponse:
        """POST /v1/workspace/{slug}/stream-chat — 流式 workspace 聊天。

        Args:
            slug: workspace slug
            request: {"message": ..., "mode": "chat", "sessionId": ...}

        Returns:
            StreamingResponse (SSE)，每个 chunk 为文本片段

        Raises:
            HTTPException(404): slug 不存在
        """
        ...

    async def workspace_chats(self, slug: str) -> Dict[str, Any]:
        """GET /v1/workspace/{slug}/chats — 获取聊天历史。

        Args:
            slug: workspace slug

        Returns:
            {"history": [{"id", "role", "content", "createdAt"}, ...]}

        Raises:
            HTTPException(404): slug 不存在
        """
        ...
