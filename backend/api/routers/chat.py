"""
聊天路由 - 支持 Agent 的聊天 API
前端只发送最新一条消息，后端根据 Agent 配置构建完整上下文
"""

import json
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.routers.agents import _load_agents
from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)

router = APIRouter()


# ========== 隐藏系统提示词（防呆：用户修改 Agent system_prompt 不会丢失核心工具引导） ==========

MAIN_HIDDEN_SYSTEM_PROMPT = """<role>
你是 CXHMS 智能助手系统的核心模型。你的职责是理解用户需求并提供准确、有帮助的回复。
</role>

<tools>
### 基础工具
- **calculator** - 数学计算，支持基本运算、三角函数、对数等
- **datetime** - 获取当前日期和时间
- **random** - 生成随机数
- **json_format** - 格式化 JSON 字符串

### 记忆工具
- **write_long_term_memory** - 将重要信息写入长期记忆
  - 参数：content (str) - 记忆内容, importance (int 1-5) - 重要性等级
  - 场景：用户分享个人信息、偏好、重要事件时主动保存
- **search_all_memories** - 语义搜索所有记忆
  - 参数：query (str) - 搜索词, limit (int) - 返回数量
  - 场景：需要回忆之前聊过的信息时使用
- **write_permanent_memory** - 写入永久记忆（永不被衰减或删除）
  - 参数：content (str) - 记忆内容, importance (int 1-5) - 重要性等级
  - 场景：用户明确要求永久记住的信息

### 助手调用
- **call_assistant** - 调用记忆管理模型处理复杂记忆操作
  - 参数：message (str) - 发送给助手的指令
  - 场景：需要批量管理、导出、合并、深度搜索记忆时

### 提醒工具
- **set_alarm** - 设置定时提醒
  - 参数：message (str) - 提醒内容, seconds (int) - 多少秒后提醒
- **get_alarms** - 获取当前提醒列表
- **cancel_alarm** - 取消提醒
  - 参数：alarm_id (str) - 提醒ID

### 上下文工具
- **mono** - 将信息保持在接下来的对话上下文中
  - 参数：content (str) - 要保持的信息, rounds (int) - 保持轮数
  - 场景：需要跨多轮对话记住关键信息时

### ACP 远程协作
- **acp_list_agents** - 列出可用的远程 Agent
- **acp_connect** - 连接远程 Agent
  - 参数：agent_id (str), host (str), port (int)
- **acp_disconnect** - 断开远程 Agent 连接
  - 参数：agent_id (str)
- **acp_send_message** - 向远程 Agent 发送消息
  - 参数：agent_id (str), message (str)
- **acp_create_group** - 创建 Agent 群组
- **acp_join_group** - 加入群组
- **acp_leave_group** - 离开群组
</tools>

<rules>
1. 用中文回答用户问题
2. 当用户分享个人信息时，主动使用 write_long_term_memory 保存
3. 当用户询问之前聊过的内容时，使用 search_all_memories 搜索
4. 当需要设置提醒时，使用 set_alarm，注意 seconds 参数单位是秒
5. 当记忆管理任务较复杂时，使用 call_assistant 委托给记忆管理模型
6. 不要编造不存在的工具或功能
</rules>"""

MEMORY_AGENT_HIDDEN_SYSTEM_PROMPT = """<role>
你是 CXHMS 记忆管理助手，专门负责帮助用户管理和维护记忆库。你可以通过自然语言理解用户的需求，并调用相应的工具来执行记忆管理操作。
</role>

<tools>
### 搜索与查询
- **search_memories** - 关键词搜索记忆
  - 参数：query (str) - 搜索关键词, limit (int) - 返回数量上限
  - 场景：用户想查找特定主题的记忆
- **search_by_time** - 按时间范围搜索记忆
  - 参数：start_time (str) - 起始时间, end_time (str) - 结束时间, limit (int) - 返回数量
  - 场景：用户想查找某段时间内的记忆
- **search_by_tag** - 按标签搜索记忆
  - 参数：tag (str) - 标签名, limit (int) - 返回数量
  - 场景：用户想按分类标签查找记忆
- **search_similar_memories** - 搜索与指定记忆相似的其他记忆
  - 参数：memory_id (int) - 参考记忆ID, limit (int) - 返回数量
  - 场景：查找与某条记忆内容相似的其他记忆
- **get_similar_memories** - 获取与给定内容相似的记忆
  - 参数：content (str) - 参考内容, limit (int) - 返回数量
  - 场景：根据内容描述查找相似记忆

### 修改与管理
- **update_memory_node** - 更新已存在的记忆节点内容
  - 参数：memory_id (int) - 记忆ID, content (str) - 新内容
  - 场景：用户想修正或补充某条记忆的信息
- **delete_memory** - 删除指定记忆（软删除，7天后自动清理，可恢复）
  - 参数：memory_id (int) - 要删除的记忆ID
  - 场景：用户想删除某条记忆
- **restore_memory** - 恢复软删除的记忆
  - 参数：memory_id (int) - 要恢复的记忆ID
  - 场景：用户想恢复之前删除的记忆
- **merge_memories** - 将多个相似记忆合并为一个
  - 参数：memory_ids (list[int]) - 要合并的记忆ID列表
  - 场景：发现多条重复或高度相似的记忆时合并
- **bulk_delete** - 批量删除记忆（软删除）
  - 参数：memory_ids (list[int]) - 要删除的记忆ID列表
  - 场景：用户想一次删除多条记忆

### 维护与清理
- **clean_expired** - 清理已软删除超过7天的记忆
  - 场景：用户想彻底清理已标记删除的过期记忆
- **export_memories** - 导出记忆数据为指定格式
  - 参数：format (str) - 导出格式（json/csv）, agent_id (str) - 可选，指定Agent
  - 场景：用户想导出记忆数据备份或分析

### 统计与日志
- **get_memory_stats** - 获取记忆库统计信息
  - 场景：用户想了解记忆库的整体情况（数量、类型分布等）
- **get_memory_logs** - 获取记忆管理操作日志
  - 参数：limit (int) - 返回条数
  - 场景：用户想查看最近的记忆操作记录
- **get_chat_history** - 读取指定会话的聊天历史
  - 参数：session_id (str) - 会话ID, limit (int) - 返回条数
  - 场景：需要查看某次对话的完整内容

### 辅助
- **get_available_commands** - 获取所有可用的记忆管理命令列表及描述
  - 场景：用户不确定可以执行什么操作时查看帮助
</tools>

<rules>
1. 用中文回答用户问题
2. 执行删除、合并等不可逆操作前，先向用户确认
3. 搜索记忆时优先使用语义搜索（search_memories），按需使用时间/标签搜索
4. 操作完成后简要报告结果，包括影响的记忆数量
5. 如果用户请求的操作超出你的能力范围，如实告知
6. 不要编造不存在的工具或功能
</rules>"""


# ========== 自动记忆提取（当 LLM 不支持 tools 时） ==========

# 匹配包含个人信息的用户消息模式
_MEMORY_PATTERNS = [
    # 名字/称呼 - 注意：排除疑问句中的"我叫"
    (r"^(?!.*还?记得).*(?:我(?:叫|是)([\w·]{2,10}))(?!.*[？?])", "name"),
    (r"我的(?:名字|称呼)(?:叫|是|为)([\w·]{2,10})", "name"),
    # 年龄 - 支持逗号分隔的句子如 "我叫小明，今年25岁"
    (r"(?:今年|年龄|岁数)(?:是|有|为)?\s*(\d{1,3})\s*岁", "age"),
    # 爱好/喜欢
    (r"我(?:喜欢|爱好|热爱|钟爱)(.+?)(?:[。，、；\n]|$)", "hobby"),
    (r"我的(?:爱好|兴趣|喜好)(?:是|有|包括)(.+?)(?:[。，、；\n]|$)", "hobby"),
    # 职业
    (r"我(?:是|在|从事)(?:一名|一位|个)?(.+?)(?:工作|职业|岗位)", "job"),
    (r"我的(?:职业|工作|岗位)(?:是|为)(.+?)(?:[。，；\n]|$)", "job"),
    # 位置
    (r"我(?:在|住|居住|来自)(.+?)(?:[。，；\n]|$)", "location"),
    # 宠物
    (r"我的(?:猫|狗|宠物)(?:叫|名字(?:叫|是|为))([\w·]{1,20})", "pet"),
]


def _auto_extract_memory(user_message: str, assistant_response: str) -> Optional[str]:
    """从对话中提取值得记忆的信息（当 LLM 不支持 tools 时使用）。

    使用正则模式匹配用户消息中的个人信息，返回格式化的记忆内容。
    如果没有检测到值得记忆的信息，返回 None。

    Args:
        user_message: 用户消息
        assistant_response: 助手回复

    Returns:
        提取的记忆内容字符串，或 None
    """
    # 跳过疑问句（以问号结尾的消息通常是提问而非陈述信息）
    stripped_msg = user_message.strip()
    if stripped_msg.endswith(("？", "?")):
        return None

    extracted_parts = []

    for pattern, info_type in _MEMORY_PATTERNS:
        match = re.search(pattern, user_message)
        if match:
            value = match.group(1).strip()
            if value:
                extracted_parts.append(f"{info_type}:{value}")

    if not extracted_parts:
        # 如果正则没匹配到，检查是否是"请记住"类消息
        remember_match = re.search(r"请(?:记住|记下|记得)(.+?)(?:[。，；\n]|$)", user_message)
        if remember_match:
            content = remember_match.group(1).strip()
            if content:
                return f"用户要求记住: {content}"
        return None

    return f"用户信息: {', '.join(extracted_parts)} (来源: {user_message[:100]})"


def _try_auto_store_memory(
    user_message: str,
    assistant_response: str,
    llm,
    session_id: str,
) -> None:
    """当 LLM 不支持 tools 时，自动提取并存储记忆。

    Args:
        user_message: 用户消息
        assistant_response: 助手回复
        llm: LLM 客户端实例
        session_id: 会话ID
    """
    # 只在不支持 tools 时执行
    if getattr(llm, "supports_tools", True):
        return

    try:
        memory_content = _auto_extract_memory(user_message, assistant_response)
        if memory_content:
            from backend.core.tools import tool_registry

            result = tool_registry.call_tool(
                "write_long_term_memory",
                {"content": memory_content, "importance": 3},
            )
            logger.info(f"自动记忆提取并存储: {memory_content[:80]}... -> {result}")
    except Exception as e:
        logger.warning(f"自动记忆提取失败: {e}")


class ChatRequest(BaseModel):
    """聊天请求 - 前端只发送最新一条消息"""

    message: str  # 用户最新消息
    agent_id: str = "default"  # 使用哪个 Agent
    stream: bool = True  # 是否流式响应
    images: Optional[List[str]] = None  # base64 encoded images


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
    from backend.api.app import get_llm_client, get_model_router

    model = agent_config.get("model", "main")

    try:
        model_router = get_model_router()

        # 如果是模型类型 (main/summary/memory)，从 router 获取
        if model.lower() in ["main", "summary", "memory"]:
            client = model_router.get_client(model.lower())
            if client:
                return client
        else:
            # 具体模型名，创建新客户端
            main_client = model_router.get_client("main")
            if main_client:
                from backend.core.llm.client import OllamaClient

                return OllamaClient(
                    host=main_client.host,
                    model=model,
                    temperature=agent_config.get("temperature", 0.7),
                    max_tokens=agent_config.get("max_tokens") or 4096,
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
    memory_context: Optional[str] = None,
    images: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """构建消息列表"""
    messages = []

    # 1. 系统提示词
    system_prompt = agent_config.get("system_prompt", "")
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # 2. 隐藏系统提示词（防呆：工具使用指南，用户不可修改）
    messages.append({"role": "system", "content": MAIN_HIDDEN_SYSTEM_PROMPT})

    # 3. 记忆上下文（如果启用记忆且有相关记忆）
    if memory_context and agent_config.get("use_memory", True):
        messages.append({"role": "system", "content": f"相关记忆:\n{memory_context}"})

    # 3. 历史消息（最近10条）
    history = context_mgr.get_messages(session_id, limit=10)
    for msg in history:
        if msg.get("role") in ["user", "assistant"]:
            messages.append({"role": msg["role"], "content": msg.get("content", "")})

    # 4. 用户最新消息（支持多模态）
    if images and agent_config.get("vision_enabled", False):
        # 构建多模态消息
        content = [{"type": "text", "text": user_message}]
        for img_base64 in images:
            # 提取 base64 数据部分（去掉 data:image/xxx;base64, 前缀）
            if img_base64.startswith("data:"):
                img_data = img_base64.split(",", 1)[1] if "," in img_base64 else img_base64
                mime_type = (
                    img_base64.split(";")[0].split(":")[1] if ":" in img_base64 else "image/jpeg"
                )
            else:
                img_data = img_base64
                mime_type = "image/jpeg"

            content.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_data}"}}
            )
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})

    return messages


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    非流式聊天
    前端只发送最新消息，后端根据 Agent 配置构建完整上下文
    每个 Agent 对应一个固定会话
    """
    from backend.api.app import get_context_manager, get_memory_manager

    try:
        # 1. 获取 Agent 配置
        agent_config = get_agent_config(request.agent_id)
        if not agent_config:
            raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' 不存在")

        # 2. 获取管理器
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()
        llm = get_llm_client_for_agent(agent_config)

        # 3. 获取/创建 Agent 专属会话（每个 Agent 只有一个会话）
        session_id = f"agent-{request.agent_id}"
        existing_session = context_mgr.get_session(session_id)
        if not existing_session:
            context_mgr.create_session(
                workspace_id="agent-chats",
                title=f"{agent_config['name']} 的对话",
                session_id=session_id,
                metadata={"agent_id": request.agent_id},
            )

        # 4. 添加用户消息到上下文
        context_mgr.add_message(session_id=session_id, role="user", content=request.message)

        # 5. 检索记忆（如果启用）
        memory_context = None
        if agent_config.get("use_memory", True) and memory_mgr:
            from backend.core.memory.router import MemoryRouter

            router = MemoryRouter(
                memory_manager=memory_mgr,
                vector_store=getattr(memory_mgr, "_vector_store", None),
                embedding_model=getattr(memory_mgr, "_embedding_model", None),
            )
            routing_result = await router.route(
                query=request.message,
                session_id=session_id,
                scene_type=agent_config.get("memory_scene", "chat"),
            )
            if routing_result.memories:
                memory_context = "\n".join(
                    [f"- {m['content']}" for m in routing_result.memories[:5]]
                )

        # 6. 构建消息列表
        messages = build_messages(
            agent_config=agent_config,
            context_mgr=context_mgr,
            session_id=session_id,
            user_message=request.message,
            memory_context=memory_context,
            images=request.images,
        )

        # 7. 获取工具（只过滤 summary 类别）
        from backend.core.tools import tool_registry

        all_tools = tool_registry.list_openai_functions(include_builtin=True)
        # 只过滤 summary 类别的工具
        EXCLUDED_CATEGORIES = {"summary"}
        tools = [
            t
            for t in all_tools
            if tool_registry.get_tool(t.get("function", {}).get("name", ""))
            and tool_registry.get_tool(t.get("function", {}).get("name", "")).category
            not in EXCLUDED_CATEGORIES
        ]
        if not tools:
            tools = None

        # 8. 调用 LLM
        response = await llm.chat(messages=messages, stream=False, tools=tools if tools else None)

        # 9. 循环处理工具调用（最多5轮）
        max_tool_rounds = 5
        for _ in range(max_tool_rounds):
            if not (hasattr(response, "tool_calls") and response.tool_calls):
                break

            from backend.core.tools import tool_registry
            from backend.core.tools.builtin import call_builtin_tool

            BUILTIN_TOOL_NAMES = {"calculator", "datetime", "random", "json_format"}

            for tool_call in response.tool_calls:
                tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
                tool_args = tool_call.get("arguments") or tool_call.get("function", {}).get(
                    "arguments", "{}"
                )

                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError as e:
                        logger.warning(f"工具参数 JSON 解析失败: {e}, 原始参数: {tool_args}")
                        try:
                            import ast

                            tool_args = ast.literal_eval(tool_args)
                            if not isinstance(tool_args, dict):
                                tool_args = {}
                        except Exception:
                            tool_args = {}

                # 执行工具（区分内置工具和注册工具）
                if tool_name in BUILTIN_TOOL_NAMES:
                    tool_result = call_builtin_tool(tool_name, tool_args or {})
                else:
                    tool_result = tool_registry.call_tool(tool_name, tool_args)

                # 添加工具调用结果到消息
                messages.append({"role": "assistant", "content": None, "tool_calls": [tool_call]})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "name": tool_name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

            # 再次调用 LLM（带 tools，支持链式调用）
            response = await llm.chat(messages=messages, stream=False, tools=tools if tools else None)

        final_response = response.content

        # 10. 保存助手响应到上下文
        context_mgr.add_message(session_id=session_id, role="assistant", content=final_response)

        # 11. 当 LLM 不支持 tools 时，自动提取并存储记忆
        _try_auto_store_memory(request.message, final_response, llm, session_id)

        return {
            "status": "success",
            "response": final_response,
            "session_id": session_id,
            "tokens_used": response.usage.get("total_tokens", 0) if response.usage else 0,
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
    每个 Agent 对应一个固定会话
    """
    from backend.api.app import get_context_manager, get_memory_manager

    try:
        # 1. 获取 Agent 配置
        agent_config = get_agent_config(request.agent_id)
        if not agent_config:
            raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' 不存在")

        # 2. 获取管理器
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()
        llm = get_llm_client_for_agent(agent_config)

        # 3. 获取/创建 Agent 专属会话（每个 Agent 只有一个会话）
        session_id = f"agent-{request.agent_id}"
        existing_session = context_mgr.get_session(session_id)
        if not existing_session:
            context_mgr.create_session(
                workspace_id="agent-chats",
                title=f"{agent_config['name']} 的对话",
                session_id=session_id,
                metadata={"agent_id": request.agent_id},
            )

        # 4. 添加用户消息到上下文
        context_mgr.add_message(session_id=session_id, role="user", content=request.message)

        # 5. 检索记忆（如果启用）
        memory_context = None
        if agent_config.get("use_memory", True) and memory_mgr:
            from backend.core.memory.router import MemoryRouter

            router = MemoryRouter(
                memory_manager=memory_mgr,
                vector_store=getattr(memory_mgr, "_vector_store", None),
                embedding_model=getattr(memory_mgr, "_embedding_model", None),
            )
            routing_result = await router.route(
                query=request.message,
                session_id=session_id,
                scene_type=agent_config.get("memory_scene", "chat"),
            )
            if routing_result.memories:
                memory_context = "\n".join(
                    [f"- {m['content']}" for m in routing_result.memories[:5]]
                )

        # 6. 构建消息列表
        messages = build_messages(
            agent_config=agent_config,
            context_mgr=context_mgr,
            session_id=session_id,
            user_message=request.message,
            memory_context=memory_context,
        )

        # 7. 获取工具（只过滤 summary 类别）
        from backend.core.tools import tool_registry
        from backend.core.tools.builtin import get_builtin_tools

        # 获取内置工具
        builtin_tools = get_builtin_tools()

        # 主模型专属工具列表
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

        async def generate_stream():
            """生成流式响应"""
            full_response = ""
            full_thinking = ""
            tool_calls_buffer = []
            stream_error = None

            # 发送会话ID作为第一个事件
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            try:
                logger.info(
                    f"开始流式聊天，消息数: {len(messages)}, 工具数: {len(tools) if tools else 0}"
                )
                # 调用LLM流式接口
                async for chunk in llm.stream_chat(
                    messages=messages,
                    temperature=agent_config.get("temperature", 0.7),
                    max_tokens=agent_config.get("max_tokens") or 4096,
                    tools=tools if tools else None,
                ):
                    if chunk:
                        logger.debug(f"收到 chunk: {type(chunk)}, 内容: {chunk}")
                        # 检查是否是字典类型（新的返回格式）
                        if isinstance(chunk, dict):
                            chunk_type = chunk.get("type")
                            if chunk_type == "thinking":
                                thinking_content = chunk.get("content", "")
                                full_thinking += thinking_content
                                yield f"data: {json.dumps({'type': 'thinking', 'content': thinking_content})}\n\n"
                            elif chunk_type == "content":
                                content = chunk.get("content", "")
                                full_response += content
                                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                            elif chunk_type == "tool_calls":
                                new_tool_calls = chunk.get("tool_calls", [])
                                logger.info(f"检测到工具调用: {new_tool_calls}")
                                tool_calls_buffer.extend(new_tool_calls)  # 累积工具调用
                                # 发送工具调用事件
                                for tool_call in new_tool_calls:
                                    yield f"data: {json.dumps({'type': 'tool_call', 'tool_call': tool_call})}\n\n"
                            elif chunk_type == "error":
                                stream_error = chunk.get("content", "")
                                logger.warning(f"流式聊天收到错误事件: {stream_error}")
                        # 兼容旧格式：字符串类型
                        elif isinstance(chunk, str):
                            full_response += chunk
                            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                # 如果流式调用失败（例如 vLLM 不支持工具的流式模式），回退到非流式聊天
                if not full_response and not tool_calls_buffer and stream_error:
                    logger.warning(f"流式聊天失败，回退到非流式模式: {stream_error}")
                    try:
                        response = await llm.chat(
                            messages=messages,
                            stream=False,
                            temperature=agent_config.get("temperature", 0.7),
                            max_tokens=agent_config.get("max_tokens") or 4096,
                            tools=tools if tools else None,
                        )
                        # 处理非流式回退中的工具调用
                        if hasattr(response, "tool_calls") and response.tool_calls:
                            tool_calls_buffer = response.tool_calls
                        elif response.content:
                            full_response = response.content
                            yield f"data: {json.dumps({'type': 'content', 'content': full_response})}\n\n"
                    except Exception as fallback_err:
                        logger.error(f"非流式回退也失败: {fallback_err}")

                # 处理工具调用
                if tool_calls_buffer:
                    from backend.core.tools import tool_registry
                    from backend.core.tools.builtin import call_builtin_tool

                    # 定义内置工具名称集合
                    BUILTIN_TOOL_NAMES = {"calculator", "datetime", "random", "json_format"}

                    for tool_call in tool_calls_buffer:
                        tool_name = tool_call.get("name") or tool_call.get("function", {}).get(
                            "name"
                        )
                        tool_args = tool_call.get("arguments") or tool_call.get("function", {}).get(
                            "arguments", "{}"
                        )

                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError as e:
                                logger.warning(
                                    f"工具参数 JSON 解析失败: {e}, 原始参数: {tool_args}"
                                )
                                try:
                                    import ast

                                    tool_args = ast.literal_eval(tool_args)
                                    if not isinstance(tool_args, dict):
                                        tool_args = {}
                                except Exception:
                                    tool_args = {}

                        # 发送工具执行开始事件
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': tool_name})}\n\n"

                        # 执行工具（区分内置工具和注册工具）
                        if tool_name in BUILTIN_TOOL_NAMES:
                            tool_result = call_builtin_tool(tool_name, tool_args or {})
                            logger.info(f"内置工具 {tool_name} 执行结果: {tool_result}")
                        else:
                            tool_result = tool_registry.call_tool(tool_name, tool_args)
                            logger.info(f"注册工具 {tool_name} 执行结果: {tool_result}")

                        # 发送工具执行结果事件
                        logger.info(
                            f"发送工具结果事件: tool_name={tool_name}, result type={type(tool_result)}"
                        )
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'result': tool_result})}\n\n"

                        # 添加工具调用结果到消息
                        messages.append(
                            {"role": "assistant", "content": None, "tool_calls": [tool_call]}
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "name": tool_name,
                                "content": json.dumps(tool_result, ensure_ascii=False),
                            }
                        )

                    # 再次调用LLM获取最终响应（流式，带 tools 支持链式调用）
                    full_response = ""
                    async for chunk in llm.stream_chat(
                        messages=messages,
                        temperature=agent_config.get("temperature", 0.7),
                        max_tokens=agent_config.get("max_tokens") or 4096,
                        tools=tools if tools else None,
                    ):
                        if chunk:
                            # 检查是否是字典类型（新的返回格式）
                            if isinstance(chunk, dict):
                                chunk_type = chunk.get("type")
                                if chunk_type == "content":
                                    content = chunk.get("content", "")
                                    full_response += content
                                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                                elif chunk_type == "thinking":
                                    thinking_content = chunk.get("content", "")
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': thinking_content})}\n\n"
                            # 兼容旧格式：字符串类型
                            elif isinstance(chunk, str):
                                full_response += chunk
                                yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                # 流结束，保存完整响应到上下文
                if full_response:
                    context_mgr.add_message(
                        session_id=session_id, role="assistant", content=full_response
                    )

                    # 当 LLM 不支持 tools 时，自动提取并存储记忆
                    _try_auto_store_memory(request.message, full_response, llm, session_id)

                # 发送完成事件
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

            except Exception as e:
                logger.error(f"流式聊天错误: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
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
        session = context_mgr.get_session(session_id)

        if not session:
            # 如果会话不存在，检查是否为 Agent 会话
            if session_id.startswith("agent-"):
                agent_id = session_id.replace("agent-", "")
                agent_config = get_agent_config(agent_id)

                if agent_config:
                    # 使用传入的 session_id 创建会话，而不是生成新的 UUID
                    context_mgr.create_session(
                        session_id=session_id,
                        workspace_id="agent-chats",
                        title=f"{agent_config.get('name', 'Agent')} 的对话",
                    )
                    context_mgr.update_session(session_id, metadata={"agent_id": agent_id})
                    session = context_mgr.get_session(session_id)

            if not session:
                return {
                    "status": "success",
                    "session_id": session_id,
                    "session": None,
                    "messages": [],
                }

        messages = context_mgr.get_messages(session_id, limit=limit)

        return {
            "status": "success",
            "session_id": session_id,
            "session": session,
            "messages": messages,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取聊天历史失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========== 记忆管理模型专用路由 ==========


class MemoryAgentChatRequest(BaseModel):
    """记忆管理模型聊天请求"""

    message: str  # 用户最新消息


@router.post("/memory-agent/chat/stream")
async def memory_agent_chat_stream(request: MemoryAgentChatRequest):
    """
    记忆管理模型流式聊天 - 支持上下文持久化
    记忆管理Agent只有一个固定会话
    """
    from backend.api.app import get_context_manager, get_memory_manager, get_model_router
    from backend.core.context.agent_context_manager import AgentContextManager

    try:
        # 1. 获取记忆管理Agent配置
        agent_config = get_agent_config("memory-agent")
        if not agent_config:
            raise HTTPException(status_code=404, detail="记忆管理Agent未配置")

        # 2. 获取管理器
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()
        agent_context_mgr = AgentContextManager()

        # 3. 获取记忆管理模型客户端
        model_router = get_model_router()
        llm = model_router.get_client("memory")
        if not llm:
            raise HTTPException(status_code=503, detail="记忆管理模型不可用")

        # 4. 获取/创建固定会话（记忆管理Agent只有一个会话）
        session_id = "memory-agent-default"
        existing_session = context_mgr.get_session(session_id)
        if not existing_session:
            context_mgr.create_session(
                session_id=session_id,
                workspace_id="memory-agent",
                title="记忆管理对话",
            )

        # 5. 加载历史上下文（从数据库）
        agent_id = "memory-agent"
        history_context = agent_context_mgr.get_message_history(agent_id, limit=20)

        # 6. 添加用户消息到上下文（持久化）
        context_mgr.add_message(session_id=session_id, role="user", content=request.message)
        agent_context_mgr.append_message(agent_id, "user", request.message)

        # 7. 构建消息列表（包含历史上下文）
        messages = []

        # 系统提示词
        system_prompt = agent_config.get("system_prompt", "")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 隐藏系统提示词（防呆：记忆管理工具使用指南，用户不可修改）
        messages.append({"role": "system", "content": MEMORY_AGENT_HIDDEN_SYSTEM_PROMPT})

        # 历史上下文（从数据库加载）
        for msg in history_context:
            if msg.get("role") in ["user", "assistant", "system"]:
                messages.append({"role": msg["role"], "content": msg.get("content", "")})

        # 7. 获取记忆管理工具（16个assistant类别工具）
        from backend.core.tools import tool_registry

        tools = tool_registry.list_openai_functions(include_builtin=False, category="assistant")

        logger.info(
            f"记忆管理模型配置了 {len(tools)} 个工具: {[t['function']['name'] for t in tools]}"
        )

        async def generate_stream():
            """生成流式响应"""
            full_response = ""
            full_thinking = ""
            tool_calls_buffer = []
            stream_error = None

            # 发送会话ID作为第一个事件
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            try:
                logger.info(
                    f"开始记忆管理模型流式聊天，消息数: {len(messages)}, 工具数: {len(tools)}"
                )
                # 调用LLM流式接口
                async for chunk in llm.stream_chat(
                    messages=messages,
                    temperature=agent_config.get("temperature", 0.3),
                    max_tokens=agent_config.get("max_tokens") or 4096,
                    tools=tools if tools else None,
                ):
                    if chunk:
                        # 检查是否是字典类型（新的返回格式）
                        if isinstance(chunk, dict):
                            chunk_type = chunk.get("type")
                            if chunk_type == "thinking":
                                thinking_content = chunk.get("content", "")
                                full_thinking += thinking_content
                                yield f"data: {json.dumps({'type': 'thinking', 'content': thinking_content})}\n\n"
                            elif chunk_type == "content":
                                content = chunk.get("content", "")
                                full_response += content
                                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                            elif chunk_type == "tool_calls":
                                new_tool_calls = chunk.get("tool_calls", [])
                                logger.info(f"检测到工具调用: {new_tool_calls}")
                                tool_calls_buffer.extend(new_tool_calls)  # 累积工具调用
                                # 发送工具调用事件
                                for tool_call in new_tool_calls:
                                    yield f"data: {json.dumps({'type': 'tool_call', 'tool_call': tool_call})}\n\n"
                            elif chunk_type == "error":
                                stream_error = chunk.get("content", "")
                                logger.warning(f"记忆管理模型流式聊天收到错误事件: {stream_error}")
                        # 兼容旧格式：字符串类型
                        elif isinstance(chunk, str):
                            full_response += chunk
                            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                # 如果流式调用失败（例如 vLLM 不支持工具的流式模式），回退到非流式聊天
                if not full_response and not tool_calls_buffer and stream_error:
                    logger.warning(f"记忆管理模型流式聊天失败，回退到非流式模式: {stream_error}")
                    try:
                        response = await llm.chat(
                            messages=messages,
                            stream=False,
                            temperature=agent_config.get("temperature", 0.3),
                            max_tokens=agent_config.get("max_tokens") or 4096,
                            tools=tools if tools else None,
                        )
                        # 处理非流式回退中的工具调用
                        if hasattr(response, "tool_calls") and response.tool_calls:
                            tool_calls_buffer = response.tool_calls
                        elif response.content:
                            full_response = response.content
                            yield f"data: {json.dumps({'type': 'content', 'content': full_response})}\n\n"
                    except Exception as fallback_err:
                        logger.error(f"记忆管理模型非流式回退也失败: {fallback_err}")

                # 处理工具调用
                if tool_calls_buffer:
                    from backend.core.tools.builtin import call_builtin_tool

                    BUILTIN_TOOL_NAMES = {"calculator", "datetime", "random", "json_format"}

                    for tool_call in tool_calls_buffer:
                        tool_name = tool_call.get("name") or tool_call.get("function", {}).get(
                            "name"
                        )
                        tool_args = tool_call.get("arguments") or tool_call.get("function", {}).get(
                            "arguments", "{}"
                        )

                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError as e:
                                logger.warning(
                                    f"工具参数 JSON 解析失败: {e}, 原始参数: {tool_args}"
                                )
                                try:
                                    import ast

                                    tool_args = ast.literal_eval(tool_args)
                                    if not isinstance(tool_args, dict):
                                        tool_args = {}
                                except Exception:
                                    tool_args = {}

                        # 发送工具执行开始事件
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': tool_name})}\n\n"

                        # 执行工具（区分内置工具和注册工具）
                        if tool_name in BUILTIN_TOOL_NAMES:
                            tool_result = call_builtin_tool(tool_name, tool_args or {})
                        else:
                            tool_result = tool_registry.call_tool(tool_name, tool_args)

                        # 发送工具执行结果事件
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'result': tool_result})}\n\n"

                        # 添加工具调用结果到消息
                        messages.append(
                            {"role": "assistant", "content": None, "tool_calls": [tool_call]}
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "name": tool_name,
                                "content": json.dumps(tool_result, ensure_ascii=False),
                            }
                        )

                    # 再次调用LLM获取最终响应（流式，带 tools 支持链式调用）
                    full_response = ""
                    async for chunk in llm.stream_chat(
                        messages=messages,
                        temperature=agent_config.get("temperature", 0.3),
                        max_tokens=agent_config.get("max_tokens") or 4096,
                        tools=tools if tools else None,
                    ):
                        if chunk:
                            # 检查是否是字典类型（新的返回格式）
                            if isinstance(chunk, dict):
                                chunk_type = chunk.get("type")
                                if chunk_type == "content":
                                    content = chunk.get("content", "")
                                    full_response += content
                                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                                elif chunk_type == "thinking":
                                    thinking_content = chunk.get("content", "")
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': thinking_content})}\n\n"
                            # 兼容旧格式：字符串类型
                            elif isinstance(chunk, str):
                                full_response += chunk
                                yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                # 流结束，保存完整响应到上下文
                if full_response:
                    context_mgr.add_message(
                        session_id=session_id, role="assistant", content=full_response
                    )
                    agent_context_mgr.append_message(agent_id, "assistant", full_response)

                    # 当 LLM 不支持 tools 时，自动提取并存储记忆
                    _try_auto_store_memory(request.message, full_response, llm, session_id)

                # 发送完成事件
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

            except Exception as e:
                logger.error(f"记忆管理模型流式聊天错误: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
