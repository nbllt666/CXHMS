"""
共享聊天流核心逻辑

提供统一的异步生成器函数 `generate_chat_stream`，被 SSE 端点（`chat.py`）和
WebSocket 处理器（`handlers.py`）共同消费，确保两条路径行为完全一致。

事件类型（标准化字典）:
    {"type": "session", "session_id": "..."}
    {"type": "thinking", "content": "..."}
    {"type": "content", "content": "..."}
    {"type": "tool_call", "tool_call": {...}}
    {"type": "tool_start", "tool_name": "..."}
    {"type": "tool_result", "tool_name": "...", "result": {...}}
    {"type": "done", "session_id": "..."}
    {"type": "error", "error": "..."}
    {"type": "cancelled", "timestamp": "..."}
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from backend.core.llm.tools import parse_text_tool_calls, strip_text_tool_calls
from backend.core.logging_config import get_contextual_logger
from backend.core.tools import tool_registry
from backend.core.tools.builtin import BUILTIN_TOOL_NAMES, call_builtin_tool

logger = get_contextual_logger(__name__)


# ============================================================================
# ThinkTagStreamParser（从 chat.py 复制，避免循环导入）
# ============================================================================


class ThinkTagStreamParser:
    """流式解析内嵌在 content 中的 <think>...</think> 标签。

    某些模型（如 gemma4-e4b via vLLM）不输出 reasoning_content 字段，
    而是把思考过程放在 <think>...</think> 标签内嵌在 content 中流式输出。
    本解析器将这些标签内容分离为 thinking 通道，其余作为 content 通道，
    支持标签跨 chunk 拆分的情况。
    """

    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self):
        self.buffer = ""
        self.in_think = False

    def feed(self, content: str) -> tuple:
        """喂入新 content，返回 (thinking_output, content_output)。"""
        if not content:
            return ("", "")
        self.buffer += content
        thinking_parts: List[str] = []
        content_parts: List[str] = []

        while True:
            if not self.in_think:
                idx = self.buffer.find(self.OPEN_TAG)
                if idx == -1:
                    safe = self._safe_emit_length(self.OPEN_TAG)
                    if safe > 0:
                        content_parts.append(self.buffer[:safe])
                        self.buffer = self.buffer[safe:]
                    break
                if idx > 0:
                    content_parts.append(self.buffer[:idx])
                self.buffer = self.buffer[idx + len(self.OPEN_TAG):]
                self.in_think = True
            else:
                idx = self.buffer.find(self.CLOSE_TAG)
                if idx == -1:
                    safe = self._safe_emit_length(self.CLOSE_TAG)
                    if safe > 0:
                        thinking_parts.append(self.buffer[:safe])
                        self.buffer = self.buffer[safe:]
                    break
                if idx > 0:
                    thinking_parts.append(self.buffer[:idx])
                self.buffer = self.buffer[idx + len(self.CLOSE_TAG):]
                self.in_think = False

        return ("".join(thinking_parts), "".join(content_parts))

    def flush(self) -> tuple:
        """流结束时调用，把 buffer 中剩余内容按当前状态输出，并重置状态。"""
        remaining = self.buffer
        was_in_think = self.in_think
        self.buffer = ""
        self.in_think = False
        if not remaining:
            return ("", "")
        if was_in_think:
            return (remaining, "")
        return ("", remaining)

    def _safe_emit_length(self, pending_tag: str) -> int:
        max_prefix = min(len(pending_tag) - 1, len(self.buffer))
        for prefix_len in range(max_prefix, 0, -1):
            if self.buffer.endswith(pending_tag[:prefix_len]):
                return len(self.buffer) - prefix_len
        return len(self.buffer)


# ============================================================================
# 可变状态对象（调用方创建，生成器更新，生成器结束后调用方读取）
# ============================================================================


@dataclass
class ChatStreamState:
    """聊天流状态对象，由调用方创建并传入 generate_chat_stream。

    生成器结束后，调用方可读取以下字段用于持久化：
    - accumulated_response: 跨轮累积的所有展示内容（已清理工具标记）
    - full_thinking: 全部思考内容
    - tool_calls: 全部工具调用记录（含 name/arguments/result/status）
    """

    accumulated_response: str = ""
    full_thinking: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================================
# 核心异步生成器
# ============================================================================


async def generate_chat_stream(
    llm,
    messages: List[Dict[str, Any]],
    agent_config: Dict[str, Any],
    tools: List[Dict[str, Any]],
    session_id: str,
    state: ChatStreamState,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """共享聊天流核心逻辑，产出标准化事件字典。

    参数:
        llm: LLM 客户端实例（需实现 stream_chat 方法）
        messages: 消息列表（会被原地修改，追加 assistant/tool 消息）
        agent_config: Agent 配置字典
        tools: 工具列表（OpenAI function 格式）
        session_id: 会话 ID
        state: 可变状态对象，生成器结束后调用方读取累积内容
        is_cancelled: 可选的取消检查回调，返回 True 时中止生成

    产出:
        标准化事件字典（见模块文档字符串）
    """
    full_response = ""
    full_thinking = ""
    accumulated_response = ""
    had_tool_calls = False
    think_parser = ThinkTagStreamParser()

    # 发送会话ID作为第一个事件
    yield {"type": "session", "session_id": session_id}

    try:
        logger.info(
            f"开始共享流式聊天，消息数: {len(messages)}, 工具数: {len(tools) if tools else 0}"
        )

        max_tool_rounds = 50
        for round_idx in range(max_tool_rounds):
            # 检查取消
            if is_cancelled and is_cancelled():
                yield {"type": "cancelled", "timestamp": datetime.now().isoformat()}
                break

            full_response = ""
            tool_calls_buffer: List[Dict[str, Any]] = []
            stream_error = None

            logger.info(
                f"工具调用循环第{round_idx+1}轮开始，当前消息数: {len(messages)}, "
                f"had_tool_calls: {had_tool_calls}"
            )

            # 调用LLM流式接口
            async for chunk in llm.stream_chat(
                messages=messages,
                temperature=agent_config.get("temperature", 0.7),
                max_tokens=(
                    agent_config.get("max_tokens")
                    if agent_config.get("max_tokens") is not None
                    else 4096
                ),
                tools=tools if tools else None,
            ):
                # 检查取消（流式过程中也可能被取消）
                if is_cancelled and is_cancelled():
                    yield {"type": "cancelled", "timestamp": datetime.now().isoformat()}
                    # 更新状态后退出
                    state.accumulated_response = accumulated_response
                    state.full_thinking = full_thinking
                    return

                if not chunk:
                    continue

                if isinstance(chunk, dict):
                    chunk_type = chunk.get("type")
                    if chunk_type == "thinking":
                        thinking_content = chunk.get("content", "")
                        full_thinking += thinking_content
                        yield {"type": "thinking", "content": thinking_content}
                    elif chunk_type == "content":
                        content = chunk.get("content", "")
                        # 解析内嵌的 <think>...</think> 标签
                        thinking_out, content_out = think_parser.feed(content)
                        if thinking_out:
                            full_thinking += thinking_out
                            yield {"type": "thinking", "content": thinking_out}
                        if content_out:
                            full_response += content_out
                            yield {"type": "content", "content": content_out}
                    elif chunk_type == "tool_calls":
                        new_tool_calls = chunk.get("tool_calls", [])
                        logger.info(
                            f"检测到工具调用(第{round_idx+1}轮): "
                            f"{[tc.get('function', {}).get('name', '') for tc in new_tool_calls]}"
                        )
                        tool_calls_buffer.extend(new_tool_calls)
                        for tool_call in new_tool_calls:
                            yield {"type": "tool_call", "tool_call": tool_call}
                    elif chunk_type == "error":
                        stream_error = chunk.get("content", "")
                        logger.warning(f"流式聊天收到错误事件: {stream_error}")
                elif isinstance(chunk, str):
                    # 字符串 chunk 同样需要解析 <think> 标签
                    thinking_out, content_out = think_parser.feed(chunk)
                    if thinking_out:
                        full_thinking += thinking_out
                        yield {"type": "thinking", "content": thinking_out}
                    if content_out:
                        full_response += content_out
                        yield {"type": "content", "content": content_out}

            # 流式结束，刷新 <think> 标签解析器
            flush_thinking, flush_content = think_parser.flush()
            if flush_thinking:
                full_thinking += flush_thinking
                yield {"type": "thinking", "content": flush_thinking}
            if flush_content:
                full_response += flush_content
                yield {"type": "content", "content": flush_content}

            logger.info(
                f"第{round_idx+1}轮流式结束: full_response长度={len(full_response)}, "
                f"tool_calls数量={len(tool_calls_buffer)}, stream_error={stream_error}"
            )

            # 如果流式调用失败，回退到非流式聊天
            if not full_response and not tool_calls_buffer and stream_error:
                logger.warning(f"流式聊天失败，回退到非流式模式: {stream_error}")
                try:
                    response = await llm.chat(
                        messages=messages,
                        stream=False,
                        temperature=agent_config.get("temperature", 0.7),
                        max_tokens=(
                            agent_config.get("max_tokens")
                            if agent_config.get("max_tokens") is not None
                            else 4096
                        ),
                        tools=tools if tools else None,
                    )
                    if hasattr(response, "tool_calls") and response.tool_calls:
                        tool_calls_buffer = response.tool_calls
                    elif response.content:
                        full_response = response.content
                        yield {"type": "content", "content": full_response}
                except Exception as fallback_err:
                    logger.error(f"非流式回退也失败: {fallback_err}")

            # 文本工具调用兜底
            if not tool_calls_buffer and full_response:
                tool_name_set = (
                    {t["function"]["name"] for t in tools} if tools else set()
                )
                tool_name_set |= {"calculator", "datetime", "random", "json_format"}
                text_tool_calls = parse_text_tool_calls(full_response, tool_name_set)
                # 防御性过滤：剔除空参数的工具调用
                text_tool_calls = [
                    tc
                    for tc in text_tool_calls
                    if tc.get("function", {}).get("arguments", "{}")
                    not in ("{}", "", None)
                ]
                if text_tool_calls:
                    logger.info(
                        f"文本工具调用兜底解析(第{round_idx+1}轮): "
                        f"{[tc.get('function', {}).get('name', '') for tc in text_tool_calls]}"
                    )
                    tool_calls_buffer = text_tool_calls
                    for tool_call in text_tool_calls:
                        yield {"type": "tool_call", "tool_call": tool_call}
                    # 清理展示文本中的工具标记
                    full_response = strip_text_tool_calls(full_response)

            # 空内容兜底
            if not full_response and not tool_calls_buffer and had_tool_calls:
                logger.info(f"第{round_idx+1}轮触发空内容兜底：发送默认提示")
                fallback_message = "已完成工具调用。"
                full_response = fallback_message
                yield {"type": "content", "content": fallback_message}

            # 累积本轮内容
            accumulated_response += full_response

            logger.info(
                f"第{round_idx+1}轮结束: accumulated_response长度={len(accumulated_response)}, "
                f"将退出循环={not tool_calls_buffer}"
            )

            # 没有工具调用，退出循环
            if not tool_calls_buffer:
                break

            # 处理工具调用
            # 构建标准的 assistant tool_calls 消息
            assistant_tool_calls = []
            for tool_call in tool_calls_buffer:
                func = tool_call.get("function", {})
                tc_entry = {
                    "id": tool_call.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": func.get("name", tool_call.get("name", "")),
                        "arguments": func.get(
                            "arguments", tool_call.get("arguments", "{}")
                        ),
                    },
                }
                assistant_tool_calls.append(tc_entry)

            messages.append(
                {
                    "role": "assistant",
                    "content": full_response or None,
                    "tool_calls": assistant_tool_calls,
                }
            )

            for tool_call in tool_calls_buffer:
                func = tool_call.get("function", {})
                tool_name = func.get("name", tool_call.get("name", ""))
                tool_args = func.get(
                    "arguments", tool_call.get("arguments", "{}")
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
                yield {"type": "tool_start", "tool_name": tool_name}

                # 执行工具
                try:
                    if tool_name in BUILTIN_TOOL_NAMES:
                        tool_result = call_builtin_tool(tool_name, tool_args or {})
                    else:
                        tool_result = tool_registry.call_tool(tool_name, tool_args)
                except Exception as e:
                    logger.warning(f"工具 {tool_name} 执行失败: {e}")
                    tool_result = {"success": False, "error": str(e)}

                # 发送工具执行结果事件
                yield {
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "result": tool_result,
                }

                # 记录工具调用信息（用于状态/持久化）
                state.tool_calls.append(
                    {
                        "id": tool_call.get("id", ""),
                        "name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                        "status": "completed",
                    }
                )

                # 添加工具结果到消息
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "name": tool_name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

            # 标记已执行工具调用
            had_tool_calls = True

        # 流结束，兜底再清理一次工具标记
        if accumulated_response:
            accumulated_response = strip_text_tool_calls(accumulated_response)

        # 更新状态对象（供调用方读取）
        state.accumulated_response = accumulated_response
        state.full_thinking = full_thinking

        # 发送完成事件
        yield {"type": "done", "session_id": session_id}

    except Exception as e:
        logger.error(f"共享流式聊天错误: {e}", exc_info=True)
        # 更新状态对象（部分内容）
        state.accumulated_response = accumulated_response
        state.full_thinking = full_thinking
        yield {"type": "error", "error": str(e)}
