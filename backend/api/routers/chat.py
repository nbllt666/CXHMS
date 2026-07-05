"""
聊天路由 - 支持 Agent 的聊天 API
前端只发送最新消息，后端根据 Agent 配置构建完整上下文
"""

import asyncio
import json
import re
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config.settings import settings

from backend.api.routers.agents import _load_agents
from backend.core.chat.stream import ChatStreamState, generate_chat_stream
from backend.core.llm.tools import is_empty_tool_args, parse_text_tool_calls, strip_text_tool_calls
from backend.core.logging_config import get_contextual_logger
from backend.core.tools import tool_registry
from backend.core.tools.builtin import BUILTIN_TOOL_NAMES, call_builtin_tool, get_builtin_tools
from backend.core.tools.graph_tools import set_current_agent_id

logger = get_contextual_logger(__name__)

router = APIRouter()


# ========== 隐藏系统提示词（防呆：用户修改 Agent system_prompt 不会丢失核心工具引导） ==========

MAIN_HIDDEN_SYSTEM_PROMPT = """<role>
你是 CXHMS 智能助手系统的核心模型。你的职责是理解用户需求并提供准确、有帮助的回复。
</role>

<instruction>
你可以使用系统提供的工具来帮助用户。工具已通过 API 自动注册，你无需在回复中描述或列举工具。
当需要执行操作时，必须通过 function calling 机制调用工具，不要在文本中输出工具调用标记（如 <execute_tool>）。
直接调用对应的函数即可，系统会自动执行并返回结果。
</instruction>

<rules>
1. 用中文回答用户问题
2. 当用户分享个人信息时，主动使用 write_long_term_memory 保存
3. 当用户询问之前聊过的内容时，使用 search_all_memories 搜索
4. 当需要设置提醒时，使用 set_alarm，注意 seconds 参数单位是秒
5. 当记忆管理任务较复杂时，使用 call_assistant 委托给记忆管理模型
6. 不要编造不存在的工具或功能
7. 绝对不要在回复文本中输出 <execute_tool> 或类似标记，必须通过 function calling 调用工具
</rules>"""

MEMORY_AGENT_HIDDEN_SYSTEM_PROMPT = """<role>
你是 CXHMS 记忆管理助手，专门负责帮助用户管理和维护记忆库。
</role>

<instruction>
你可以使用系统提供的工具来执行记忆管理操作。工具已通过 API 自动注册，你无需在回复中描述或列举工具。
当需要执行操作时，必须通过 function calling 机制调用工具，不要在文本中输出工具调用标记（如 <execute_tool>）。
直接调用对应的函数即可，系统会自动执行并返回结果。
</instruction>

<rules>
1. 用中文回答用户问题
2. 执行删除、合并等不可逆操作前，先向用户确认
3. 搜索记忆时优先使用语义搜索（search_memories），按需使用时间/标签搜索
4. 操作完成后简要报告结果，包括影响的记忆数量
5. 如果用户请求的操作超出你的能力范围，如实告知
6. 不要编造不存在的工具或功能
7. 绝对不要在回复文本中输出 <execute_tool> 或类似标记，必须通过 function calling 调用工具
</rules>"""


SUMMARY_AGENT_HIDDEN_SYSTEM_PROMPT = """<role>
你是 CXHMS 摘要助手，专门负责将对话内容整理为日记式条目并保存。
</role>

<instruction>
你必须使用 save_diary_entry 工具来保存日记条目。该工具已通过 API 自动注册，无需向用户确认即可直接调用。
当需要保存日记时，必须通过 function calling 机制调用 save_diary_entry 工具，不要在文本中输出工具调用标记（如 <execute_tool>）。
直接调用对应的函数即可，系统会自动执行并返回结果。
无论对话内容是什么，你都必须至少调用一次 save_diary_entry 工具保存日记。不要拒绝保存或要求用户提供"更好的"内容。
</instruction>

<rules>
1. 用中文回答用户问题
2. 以日记体裁（第一人称叙述）整理对话内容，包含：日期、主要事件、情绪/感受、反思
3. 如果对话包含多个独立事件/话题，按事件拆分，每个事件生成一篇独立日记，多次调用 save_diary_entry；如果只有一个话题，生成一篇即可
4. 日记正文（body）应为连贯的第一人称叙述，而非要点列表
5. 调用 save_diary_entry 工具时需提供：date(YYYY-MM-DD)、title、mood、body、summarized_message_range(如 "0-15")
6. 不要编造不存在的工具或功能，不要使用 save_summary_memory 或 write_long_term_memory 等其他记忆工具
7. 绝对不要在回复文本中输出 <execute_tool> 或类似标记，必须通过 function calling 调用工具
8. 不要拒绝保存日记。即使对话内容是测试或元讨论，也要将其整理为日记并保存。这是你的核心职责。
9. 完成日记保存后，简要报告保存结果
</rules>"""


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
            result = tool_registry.call_tool(
                "write_long_term_memory",
                {"content": memory_content, "importance": 3},
            )
            logger.info(f"自动记忆提取并存储: {memory_content[:80]}... -> {result}")
    except Exception as e:
        logger.warning(f"自动记忆提取失败: {e}")


# Agent 工具列表缓存（避免每次请求重建 OpenAI function schema）
_tools_cache: Dict[str, List[Dict]] = {}
_tools_cache_sig: Dict[str, int] = {}


def _get_tools_for_agent(agent_id: str) -> List[Dict]:
    """获取 Agent 的工具列表，按 agent_id 缓存，工具注册数量变化时失效。"""
    current_sig = len(tool_registry._tools)
    if agent_id in _tools_cache and _tools_cache_sig.get(agent_id) == current_sig:
        return _tools_cache[agent_id]

    builtin_tools = get_builtin_tools()
    EXCLUDED_CATEGORIES = {"summary"}
    main_tool_names = {
        "write_long_term_memory", "search_all_memories", "call_assistant",
        "set_alarm", "mono", "write_permanent_memory",
        "acp_list_agents", "acp_connect", "acp_disconnect", "acp_send_message",
        "acp_create_group", "acp_join_group", "acp_leave_group",
    }
    main_tools = []
    for tool_name in main_tool_names:
        tool = tool_registry.get_tool(tool_name)
        if tool and tool.enabled and tool.category not in EXCLUDED_CATEGORIES:
            main_tools.append(tool.to_openai_function())

    tools = builtin_tools + main_tools
    _tools_cache[agent_id] = tools
    _tools_cache_sig[agent_id] = current_sig
    return tools


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
    from backend.dependencies import get_llm_client, get_model_router

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
                    max_tokens=(agent_config.get("max_tokens") if agent_config.get("max_tokens") is not None else 4096),
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

    # 3. 历史消息（最近 N 条，可由 Agent 配置 history_limit 调整，默认 50）
    history_limit = agent_config.get("history_limit", 50)
    history = context_mgr.get_messages(session_id, limit=history_limit)
    for msg in history:
        if msg.get("role") in ["user", "assistant"]:
            messages.append({"role": msg["role"], "content": msg.get("content", "")})
        elif msg.get("role") == "system" and msg.get("content_type") == "diary_summary":
            messages.append({"role": "system", "content": msg.get("content", "")})

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
    from backend.dependencies import get_context_manager, get_memory_manager

    try:
        _t0 = time.monotonic()
        # 1. 获取 Agent 配置
        agent_config = get_agent_config(request.agent_id)
        set_current_agent_id(request.agent_id)
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
        _t1 = time.monotonic()

        # 4. 检索记忆（如果启用）
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
                    [f"- {m['content']}" for m in routing_result.memories[:agent_config.get("memory_context_limit", 5)]]
                )
        _t2 = time.monotonic()

        # 5. 构建消息列表（在 add_message 之前，避免当前用户消息重复）
        messages = build_messages(
            agent_config=agent_config,
            context_mgr=context_mgr,
            session_id=session_id,
            user_message=request.message,
            memory_context=memory_context,
            images=request.images,
        )
        _t3 = time.monotonic()

        # 6. 添加用户消息到上下文（在构建消息之后，避免历史中重复）
        context_mgr.add_message(session_id=session_id, role="user", content=request.message)
        _t4 = time.monotonic()

        # 7. 获取工具（排除 summary 类别，合并内置工具）
        builtin_tools = get_builtin_tools()
        registered_tools = tool_registry.list_openai_functions(include_builtin=False)
        EXCLUDED_CATEGORIES = {"summary"}
        filtered_registered = [
            t
            for t in registered_tools
            if tool_registry.get_tool(t.get("function", {}).get("name", ""))
            and tool_registry.get_tool(t.get("function", {}).get("name", "")).category
            not in EXCLUDED_CATEGORIES
        ]
        tools = builtin_tools + filtered_registered
        if not tools:
            tools = None
        _t5 = time.monotonic()

        # 8. 调用 LLM
        response = await llm.chat(messages=messages, stream=False, tools=tools if tools else None)
        _t6 = time.monotonic()
        logger.info(
            f"[CHAT_TIMING] session={int((_t1-_t0)*1000)}ms memory={int((_t2-_t1)*1000)}ms "
            f"build={int((_t3-_t2)*1000)}ms add_user={int((_t4-_t3)*1000)}ms "
            f"tools={int((_t5-_t4)*1000)}ms llm={int((_t6-_t5)*1000)}ms total_pre_llm={int((_t5-_t0)*1000)}ms"
        )

        # 9. 循环处理工具调用（按 settings.config.llm.max_tool_rounds，默认10轮）
        max_tool_rounds = settings.config.llm.max_tool_rounds
        for _ in range(max_tool_rounds):
            if not (hasattr(response, "tool_calls") and response.tool_calls):
                break

            # 执行工具调用
            # BUILTIN_TOOL_NAMES 已在文件顶部导入

            # 构建标准的 assistant tool_calls 消息（所有 tool_calls 合并为一条）
            assistant_tool_calls = []
            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                tc_entry = {
                    "id": tool_call.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": func.get("name", tool_call.get("name", "")),
                        "arguments": func.get("arguments", tool_call.get("arguments", "{}")),
                    },
                }
                assistant_tool_calls.append(tc_entry)

            messages.append({"role": "assistant", "content": None, "tool_calls": assistant_tool_calls})

            for tool_call in response.tool_calls:
                func = tool_call.get("function", {})
                tool_name = func.get("name", tool_call.get("name", ""))
                tool_args = func.get("arguments", tool_call.get("arguments", "{}"))

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

                # 执行工具
                try:
                    if tool_name in BUILTIN_TOOL_NAMES:
                        tool_result = call_builtin_tool(tool_name, tool_args or {})
                    else:
                        tool_result = tool_registry.call_tool(tool_name, tool_args)
                except Exception as e:
                    logger.warning(f"工具 {tool_name} 执行失败: {e}")
                    tool_result = {"success": False, "error": str(e)}

                # 添加工具结果到消息
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
        _t7 = time.monotonic()
        context_mgr.add_message(session_id=session_id, role="assistant", content=final_response)
        _t8 = time.monotonic()

        # 11. 当 LLM 不支持 tools 时，自动提取并存储记忆
        _try_auto_store_memory(request.message, final_response, llm, session_id)
        _t9 = time.monotonic()
        logger.info(
            f"[CHAT_TIMING_POST] add_asst={int((_t8-_t7)*1000)}ms auto_store={int((_t9-_t8)*1000)}ms"
        )

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
async def stream_chat(request: ChatRequest):
    """
    流式聊天
    前端只发送最新消息，后端根据 Agent 配置构建完整上下文
    每个 Agent 对应一个固定会话
    """
    from backend.dependencies import get_context_manager, get_memory_manager

    try:
        # Fast prep only: agent config, managers, session, LLM client
        # 1. 获取 Agent 配置
        agent_config = get_agent_config(request.agent_id)
        set_current_agent_id(request.agent_id)
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

        async def generate_stream():
            """生成流式响应（消费共享聊天流生成器）"""
            import time as _time
            _t_start = _time.monotonic()
            # 1. Send session event IMMEDIATELY (before slow prep) so frontend shows "thinking"
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"
            _t_session = _time.monotonic()

            state = ChatStreamState()
            _t_llm_first = None
            _t_llm_end = None
            _t_tools_total = 0.0
            persist_task = None
            try:
                stream_gen = None  # C4: 共享聊天流生成器引用，断开时在 finally 中 aclose 释放上游 vLLM
                async def _retrieve_memory():
                    if not (agent_config.get("use_memory", True) and memory_mgr):
                        return None
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
                        return "\n".join(
                            [f"- {m['content']}" for m in routing_result.memories[:agent_config.get("memory_context_limit", 5)]]
                        )
                    return None

                async def _persist_user_message():
                    await context_mgr.add_message_async(
                        session_id=session_id, role="user", content=request.message
                    )

                # 并行准备：记忆检索（async）与工具获取（sync 走缓存）并行
                # 注意：用户消息持久化不能与记忆检索并行——add_message_async 会立即
                # 在内存历史中追加当前消息，而 build_messages 会读历史并再次追加
                # user_message，导致重复。故持久化改为与 LLM 流并行（见下）。
                _t_prep_start = _time.monotonic()
                memory_task = asyncio.create_task(_retrieve_memory())
                tools = _get_tools_for_agent(request.agent_id)
                memory_context = await memory_task
                _t_prep_end = _time.monotonic()

                # 构建消息列表（必须在持久化用户消息之前，避免当前用户消息重复）
                _t_build_start = _time.monotonic()
                messages = build_messages(
                    agent_config=agent_config,
                    context_mgr=context_mgr,
                    session_id=session_id,
                    user_message=request.message,
                    memory_context=memory_context,
                )
                _t_build_end = _time.monotonic()

                # 用户消息持久化与 LLM 流并行（磁盘写入卸载到线程，不阻塞 TTFT）
                persist_task = asyncio.create_task(_persist_user_message())

                logger.info(
                    f"为 Agent '{agent_config.get('name')}' 配置了 {len(tools)} 个工具: {[t['function']['name'] for t in tools]}"
                )
                logger.info(f"generate_stream 开始: llm={llm}, messages={len(messages)}, tools={len(tools)}")

                _t_llm_start = _time.monotonic()
                stream_gen = generate_chat_stream(
                    llm=llm,
                    messages=messages,
                    agent_config=agent_config,
                    tools=tools,
                    session_id=session_id,
                    state=state,
                )
                async for event in stream_gen:
                    # 记录首 token 时间
                    if _t_llm_first is None and event.get("type") in ("content", "thinking"):
                        _t_llm_first = _time.monotonic()
                    # 累计工具执行时间
                    if event.get("type") == "tool_start":
                        _t_tool_start = _time.monotonic()
                    elif event.get("type") == "tool_result":
                        _t_tools_total += _time.monotonic() - _t_tool_start
                    logger.debug(f"generate_stream yield event: {event.get('type')}")
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                _t_llm_end = _time.monotonic()
                logger.info(f"generate_stream 结束: accumulated={len(state.accumulated_response)}")
                # 输出分阶段计时
                logger.info(
                    f"[STREAM_TIMING] session={int((_t_session-_t_start)*1000)}ms "
                    f"prep={int((_t_prep_end-_t_prep_start)*1000)}ms "
                    f"build={int((_t_build_end-_t_build_start)*1000)}ms "
                    f"llm_first={int((_t_llm_first-_t_llm_start)*1000) if _t_llm_first else -1}ms "
                    f"llm_total={int((_t_llm_end-_t_llm_start)*1000)}ms "
                    f"tools={int(_t_tools_total*1000)}ms "
                    f"total={int((_t_llm_end-_t_start)*1000)}ms"
                )
            except Exception as e:
                logger.error(f"generate_stream 异常: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                # C4: 主动 aclose 共享聊天流生成器，传播客户端断开/取消到上游 vLLM 流
                if stream_gen is not None:
                    try:
                        await stream_gen.aclose()
                    except Exception:
                        pass
                # 确保用户消息持久化完成
                if persist_task is not None:
                    try:
                        await persist_task
                    except Exception:
                        pass
                # 确保 assistant 消息可靠落库（使用跨轮累积内容）
                if state.accumulated_response:
                    try:
                        await context_mgr.add_message_async(
                            session_id=session_id,
                            role="assistant",
                            content=state.accumulated_response,
                        )
                    except Exception:
                        pass

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
    from backend.dependencies import get_context_manager

    try:
        context_mgr = get_context_manager()
        session = context_mgr.get_session(session_id)

        if not session:
            # 如果会话不存在，检查是否为 Agent 会话
            if session_id.startswith("agent-"):
                agent_id = session_id.removeprefix("agent-")
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
    """记忆管理模型聊天请求。

    字段对齐 public/interface_stub/chat_service.pyi 的
    memory_agent_stream_chat(message, agent_id, images) 契约。
    agent_id 默认 memory-agent，images 可选（用于多模态扩展）。
    """

    message: str  # 用户最新消息
    agent_id: str = "memory-agent"  # 固定为记忆管理 Agent
    images: Optional[List[str]] = None  # base64 encoded images


@router.post("/memory-agent/chat/stream")
async def memory_agent_stream_chat(request: MemoryAgentChatRequest):
    """
    记忆管理模型流式聊天 - 支持上下文持久化
    记忆管理Agent只有一个固定会话
    """
    from backend.dependencies import get_context_manager, get_memory_manager, get_model_router

    try:
        # 1. 获取记忆管理Agent配置
        agent_config = get_agent_config("memory-agent")
        set_current_agent_id("memory-agent")
        if not agent_config:
            raise HTTPException(status_code=404, detail="记忆管理Agent未配置")

        # 2. 获取管理器
        memory_mgr = get_memory_manager()
        context_mgr = get_context_manager()

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

        # 5. 加载历史上下文（在 add_message 之前加载，避免当前用户消息重复）
        history_limit = agent_config.get("history_limit", 50)
        history_context = context_mgr.get_message_history(agent_id="memory-agent", limit=history_limit)

        # 6. 构建消息列表（包含历史上下文）
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

        # 当前用户消息（history_context 在持久化之前加载，不含本条，需显式追加）
        messages.append({"role": "user", "content": request.message})

        # 7. 获取记忆管理工具（assistant类别工具 + 内置工具）
        builtin_tools = get_builtin_tools()
        assistant_tools = tool_registry.list_openai_functions(include_builtin=False, category="assistant")
        tools = builtin_tools + assistant_tools

        logger.info(
            f"记忆管理模型配置了 {len(tools)} 个工具: {[t['function']['name'] for t in tools]}"
        )

        async def generate_stream():
            """生成流式响应（消费共享聊天流生成器）"""
            # 1. 立即发送 session 事件，让前端显示"思考中"状态
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"

            # 2. 用户消息异步持久化（不阻塞事件循环）
            try:
                await context_mgr.add_message_async(
                    session_id=session_id, role="user", content=request.message
                )
            except Exception as e:
                logger.warning(f"记忆管理模型用户消息持久化失败: {e}")

            state = ChatStreamState()
            try:
                stream_gen = None  # C4: 共享聊天流生成器引用，断开时在 finally 中 aclose 释放上游 vLLM
                logger.info(
                    f"开始记忆管理模型流式聊天，消息数: {len(messages)}, 工具数: {len(tools)}"
                )
                stream_gen = generate_chat_stream(
                    llm=llm,
                    messages=messages,
                    agent_config=agent_config,
                    tools=tools,
                    session_id=session_id,
                    state=state,
                )
                async for event in stream_gen:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"记忆管理模型流式聊天错误: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                # C4: 主动 aclose 共享聊天流生成器，传播客户端断开/取消到上游 vLLM 流
                if stream_gen is not None:
                    try:
                        await stream_gen.aclose()
                    except Exception:
                        pass
                # 确保 assistant 消息可靠落库（使用跨轮累积内容）
                if state.accumulated_response:
                    try:
                        await context_mgr.add_message_async(
                            session_id=session_id,
                            role="assistant",
                            content=state.accumulated_response,
                        )
                    except Exception:
                        pass

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


# ========== 摘要助手专用路由 ==========


class SummaryAgentChatRequest(BaseModel):
    """摘要助手聊天请求。

    字段对齐 public/interface_stub/chat_service.pyi 的
    summary_agent_stream_chat(message, agent_id, images) 契约。
    agent_id 默认 summary-agent，images 可选（用于多模态扩展）。
    target_session_id 是摘要助手扩展字段（指定待摘要的目标会话）。
    """

    message: str  # 用户最新消息
    agent_id: str = "summary-agent"  # 固定为摘要 Agent
    images: Optional[List[str]] = None  # base64 encoded images
    target_session_id: Optional[str] = None  # 待摘要的目标会话ID（用于上下文替换）


@router.post("/summary-agent/chat/stream")
async def summary_agent_stream_chat(request: SummaryAgentChatRequest):
    """
    摘要助手流式聊天 - 支持上下文持久化
    使用 summary 模型，仅提供 summary 类别工具（save_summary_memory 等）
    摘要助手只有一个固定会话
    """
    from backend.dependencies import get_context_manager, get_model_router

    try:
        # 1. 获取摘要Agent配置（复用 memory-agent 配置结构，但使用 summary 模型）
        agent_config = {
            "id": "summary-agent",
            "name": "摘要助手",
            "system_prompt": "你是摘要助手，专门负责将对话内容整理为日记式条目并保存。按事件/话题拆分，每个事件生成一篇独立的日记式叙述（第一人称），多次调用 save_diary_entry 工具保存。",
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        set_current_agent_id("summary-agent")

        # 2. 获取管理器
        context_mgr = get_context_manager()

        # 3. 获取摘要模型客户端
        model_router = get_model_router()
        llm = model_router.get_client("summary")
        if not llm:
            # 摘要模型未配置时回退到主模型
            logger.warning("摘要模型不可用，回退到主模型")
            llm = model_router.get_client("main")
        if not llm:
            raise HTTPException(status_code=503, detail="摘要模型与主模型均不可用")

        # 4. 获取/创建固定会话（摘要助手只有一个会话，保持上下文持久化）
        session_id = "summary-agent-default"
        existing_session = context_mgr.get_session(session_id)
        if not existing_session:
            context_mgr.create_session(
                session_id=session_id,
                workspace_id="summary-agent",
                title="摘要助手对话",
            )

        # 5. 加载历史上下文（在 add_message 之前加载，避免当前用户消息重复）
        history_limit = agent_config.get("history_limit", 50)
        history_context = context_mgr.get_messages(session_id=session_id, limit=history_limit)

        # 6. 构建消息列表（包含历史上下文）
        messages = []

        # 系统提示词
        system_prompt = agent_config.get("system_prompt", "")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 隐藏系统提示词（防呆：摘要工具使用指南，用户不可修改）
        messages.append({"role": "system", "content": SUMMARY_AGENT_HIDDEN_SYSTEM_PROMPT})

        # 历史上下文（从数据库加载）
        for msg in history_context:
            if msg.get("role") in ["user", "assistant", "system"]:
                messages.append({"role": msg["role"], "content": msg.get("content", "")})

        # 当前用户消息（history_context 在持久化之前加载，不含本条，需显式追加）
        messages.append({"role": "user", "content": request.message})

        # 7. 获取摘要工具（summary类别工具 + 内置工具）
        builtin_tools = get_builtin_tools()
        summary_tools = tool_registry.list_openai_functions(include_builtin=False, category="summary")
        tools = builtin_tools + summary_tools

        logger.info(
            f"摘要助手配置了 {len(tools)} 个工具: {[t['function']['name'] for t in tools]}"
        )

        # 预计算目标会话的可摘要范围（用于上下文替换）
        target_summarizable_range = None
        if request.target_session_id:
            try:
                target_summarizable_range = context_mgr.get_summarizable_range(
                    request.target_session_id
                )
                logger.info(
                    f"目标会话 {request.target_session_id} 可摘要范围: {target_summarizable_range}"
                )
            except Exception as e:
                logger.warning(f"获取目标会话可摘要范围失败: {e}")

        # 用于捕获 save_diary_entry 工具调用的参数（支持每事件一篇，多次调用）
        captured_diary_entries = []

        def _on_tool_result(tool_name: str, tool_args: Dict, tool_result: Dict) -> None:
            """捕获 save_diary_entry 工具调用参数（用于上下文替换）"""
            if tool_name == "save_diary_entry" and isinstance(tool_args, dict):
                if tool_args.get("body"):
                    captured_diary_entries.append({
                        "body": tool_args.get("body"),
                        "summarized_message_range": tool_args.get(
                            "summarized_message_range"
                        ),
                    })

        async def generate_stream():
            """生成流式响应（消费共享聊天流生成器）"""
            # 1. 立即发送 session 事件，让前端显示"思考中"状态
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"

            # 2. 用户消息异步持久化（不阻塞事件循环）
            try:
                await context_mgr.add_message_async(
                    session_id=session_id, role="user", content=request.message
                )
            except Exception as e:
                logger.warning(f"摘要助手用户消息持久化失败: {e}")

            state = ChatStreamState()
            try:
                stream_gen = None  # C4: 共享聊天流生成器引用，断开时在 finally 中 aclose 释放上游 vLLM
                logger.info(
                    f"开始摘要助手流式聊天，消息数: {len(messages)}, 工具数: {len(tools)}"
                )
                stream_gen = generate_chat_stream(
                    llm=llm,
                    messages=messages,
                    agent_config=agent_config,
                    tools=tools,
                    session_id=session_id,
                    state=state,
                    on_tool_result=_on_tool_result,
                )
                async for event in stream_gen:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"摘要助手流式聊天错误: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                # C4: 主动 aclose 共享聊天流生成器，传播客户端断开/取消到上游 vLLM 流
                if stream_gen is not None:
                    try:
                        await stream_gen.aclose()
                    except Exception:
                        pass
                # 确保 assistant 消息可靠落库（使用跨轮累积内容）
                if state.accumulated_response:
                    try:
                        await context_mgr.add_message_async(
                            session_id=session_id,
                            role="assistant",
                            content=state.accumulated_response,
                        )
                    except Exception:
                        pass

                # 上下文替换：将目标会话中被摘要的原始消息替换为日记摘要（每事件一篇）
                if (
                    request.target_session_id
                    and target_summarizable_range
                    and captured_diary_entries
                ):
                    try:
                        summary_bodies = [item["body"] for item in captured_diary_entries if item.get("body")]
                        # 取所有条目 range 的最大 end 作为 up_to_index
                        max_end = -1
                        for item in captured_diary_entries:
                            range_str = item.get("summarized_message_range")
                            if range_str and "-" in str(range_str):
                                try:
                                    parts = str(range_str).split("-")
                                    end_val = int(parts[-1])
                                    if end_val > max_end:
                                        max_end = end_val
                                except (ValueError, IndexError):
                                    pass
                        up_to_index = max_end if max_end >= 0 else target_summarizable_range.get("end", 0)

                        if summary_bodies and up_to_index > target_summarizable_range.get("start", 0):
                            context_mgr.replace_messages_with_summary(
                                session_id=request.target_session_id,
                                summary_entries=summary_bodies,
                                summarized_up_to_index=up_to_index,
                            )
                            yield f"data: {json.dumps({'type': 'context_replaced', 'target_session_id': request.target_session_id, 'summarized_up_to': up_to_index}, ensure_ascii=False)}\n\n"
                            logger.info(
                                f"目标会话上下文已替换: session={request.target_session_id}, up_to={up_to_index}, 摘要条目 {len(summary_bodies)} 篇"
                            )
                    except Exception as e:
                        logger.warning(f"上下文替换失败: {e}")

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
