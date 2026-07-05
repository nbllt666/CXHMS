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

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from config.settings import settings

from backend.core.llm.tools import parse_text_tool_calls, strip_text_tool_calls
from backend.core.logging_config import get_contextual_logger
from backend.core.tools import tool_registry
from backend.core.tools.builtin import (
    BUILTIN_TOOL_NAMES,
    call_builtin_tool,
    call_builtin_tool_async,
)

logger = get_contextual_logger(__name__)


# ============================================================================
# ThinkTagStreamParser 正式定义（chat.py 重复副本已于 D4 移除）
# ============================================================================


THOUGHT_MARKER = "thought\n"
FINAL_MARKER = "final\n"


class ThinkTagStreamParser:
    """流式解析内嵌在 content 中的思考标签。

    支持三种格式：
    1. 标准标签：<think>...</think>（Qwen3、DeepSeek 等）
    2. Gemma 4 channel 分隔符：`<|channel|>thought` 换行 ... `<|channel|>final` 换行
       - `<|channel|>thought\n` 开启思考模式
       - 下一个 `<|channel|>...`（如 `<|channel|>final\n`）关闭思考模式

    本解析器将这些标签内容分离为 thinking 通道，其余作为 content 通道，
    支持标签跨 chunk 拆分的情况。

    3. 无前缀裸标记（tokenizer 剥离 <|channel|> 后的残余）：
       - 响应开头出现 `thought\n` → 进入思考模式
       - 思考中出现 `final\n` → 退出思考模式
    """

    THOUGHT_MARKER = THOUGHT_MARKER
    FINAL_MARKER = FINAL_MARKER

    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"
    # Gemma 4 channel 分隔符
    GEMMA_CHANNEL_PREFIX = "<|channel|>"
    GEMMA_THOUGHT_OPEN = "thought\n"  # 紧跟在 GEMMA_CHANNEL_PREFIX 之后，表示开启思考模式

    def __init__(self):
        self.buffer = ""
        self.in_think = False
        self.seen_content = False

    def feed(self, content: str) -> tuple:
        """喂入新 content，返回 (thinking_output, content_output)。"""
        if not content:
            return ("", "")
        self.buffer += content
        thinking_parts = []
        content_parts = []

        while True:
            if not self.in_think:
                candidates = []
                think_idx = self.buffer.find(self.OPEN_TAG)
                if think_idx != -1:
                    candidates.append((think_idx, "think_open"))
                gemma_idx = self.buffer.find(self.GEMMA_CHANNEL_PREFIX)
                if gemma_idx != -1:
                    candidates.append((gemma_idx, "gemma"))
                if not self.seen_content:
                    thought_idx = self.buffer.find(self.THOUGHT_MARKER)
                    if thought_idx == 0:
                        candidates.append((thought_idx, "thought_bare"))

                if not candidates:
                    pending = [self.OPEN_TAG, self.GEMMA_CHANNEL_PREFIX]
                    if not self.seen_content:
                        pending.append(self.THOUGHT_MARKER)
                    safe = self._safe_emit_length_multi(pending)
                    if safe > 0:
                        content_parts.append(self.buffer[:safe])
                        self.seen_content = True
                        self.buffer = self.buffer[safe:]
                    break

                idx, kind = min(candidates)
                if idx > 0:
                    content_parts.append(self.buffer[:idx])
                    self.seen_content = True

                if kind == "think_open":
                    self.buffer = self.buffer[idx + len(self.OPEN_TAG):]
                    self.in_think = True
                elif kind == "thought_bare":
                    self.buffer = self.buffer[idx + len(self.THOUGHT_MARKER):]
                    self.in_think = True
                    self.seen_content = True
                else:
                    rest = self.buffer[idx + len(self.GEMMA_CHANNEL_PREFIX):]
                    if rest.startswith(self.GEMMA_THOUGHT_OPEN):
                        self.buffer = rest[len(self.GEMMA_THOUGHT_OPEN):]
                        self.in_think = True
                    else:
                        nl_idx = rest.find("\n")
                        if nl_idx == -1:
                            self.buffer = self.buffer[idx:]
                            break
                        self.buffer = rest[nl_idx + 1:]
            else:
                candidates = []
                think_close_idx = self.buffer.find(self.CLOSE_TAG)
                if think_close_idx != -1:
                    candidates.append((think_close_idx, "think_close"))
                gemma_idx = self.buffer.find(self.GEMMA_CHANNEL_PREFIX)
                if gemma_idx != -1:
                    candidates.append((gemma_idx, "gemma"))
                final_idx = self.buffer.find(self.FINAL_MARKER)
                if final_idx != -1:
                    candidates.append((final_idx, "final_bare"))

                if not candidates:
                    safe = self._safe_emit_length_multi(
                        [self.CLOSE_TAG, self.GEMMA_CHANNEL_PREFIX, self.FINAL_MARKER]
                    )
                    if safe > 0:
                        thinking_parts.append(self.buffer[:safe])
                        self.buffer = self.buffer[safe:]
                    break

                idx, kind = min(candidates)
                if idx > 0:
                    thinking_parts.append(self.buffer[:idx])

                if kind == "think_close":
                    self.buffer = self.buffer[idx + len(self.CLOSE_TAG):]
                    self.in_think = False
                    self.seen_content = True
                elif kind == "final_bare":
                    self.buffer = self.buffer[idx + len(self.FINAL_MARKER):]
                    self.in_think = False
                    self.seen_content = True
                else:
                    rest = self.buffer[idx + len(self.GEMMA_CHANNEL_PREFIX):]
                    if rest.startswith(self.GEMMA_THOUGHT_OPEN):
                        self.buffer = rest[len(self.GEMMA_THOUGHT_OPEN):]
                    else:
                        nl_idx = rest.find("\n")
                        if nl_idx == -1:
                            self.buffer = self.buffer[idx:]
                            break
                        self.buffer = rest[nl_idx + 1:]
                        self.in_think = False

        return ("".join(thinking_parts), "".join(content_parts))

    def flush(self) -> tuple:
        """流结束时调用，把 buffer 中剩余内容按当前状态输出，并重置状态。"""
        remaining = self.buffer
        was_in_think = self.in_think
        self.buffer = ""
        self.in_think = False
        self.seen_content = False
        if not remaining:
            return ("", "")
        if was_in_think:
            return (remaining, "")
        return ("", remaining)

    def _safe_emit_length_multi(self, pending_tags):
        """Calculate safe emit length to avoid outputting incomplete prefix of any pending_tag."""
        max_prefix_len = 0
        for tag in pending_tags:
            max_prefix = min(len(tag) - 1, len(self.buffer))
            for prefix_len in range(max_prefix, 0, -1):
                if self.buffer.endswith(tag[:prefix_len]):
                    if prefix_len > max_prefix_len:
                        max_prefix_len = prefix_len
                    break
        return len(self.buffer) - max_prefix_len


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
    on_tool_result: Optional[Callable[[str, Dict, Dict], None]] = None,
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
        on_tool_result: 可选回调，每次工具执行后调用，签名 (tool_name, tool_args, tool_result)，
                        供调用方（如摘要助手）捕获特定工具调用参数

    产出:
        标准化事件字典（见模块文档字符串）
    """
    full_response = ""
    full_thinking = ""
    accumulated_response = ""
    had_tool_calls = False
    think_parser = ThinkTagStreamParser()

    current_upstream = None  # C4: 当前轮的上游 vLLM 流引用，断开时由外层 except 主动 aclose
    try:
        logger.info(
            f"开始共享流式聊天，消息数: {len(messages)}, 工具数: {len(tools) if tools else 0}"
        )

        max_tool_rounds = settings.config.llm.max_tool_rounds
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

            # 调用LLM流式接口（C4: 捕获上游生成器，断开时由外层 except 主动 aclose 释放 vLLM 连接）
            current_upstream = llm.stream_chat(
                messages=messages,
                temperature=agent_config.get("temperature", 0.7),
                max_tokens=(
                    agent_config.get("max_tokens")
                    if agent_config.get("max_tokens") is not None
                    else 4096
                ),
                tools=tools if tools else None,
                enable_thinking=agent_config.get("enable_thinking", False),
            )
            async for chunk in current_upstream:
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
            current_upstream = None  # C4: 本轮流式已耗尽，清除引用（避免外层 except 误 aclose 已关闭的生成器）
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

                # 执行工具（异步，不阻塞事件循环）
                try:
                    if tool_name in BUILTIN_TOOL_NAMES:
                        tool_result = await call_builtin_tool_async(tool_name, tool_args or {})
                    else:
                        tool_result = await tool_registry.call_tool_async(tool_name, tool_args)
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

                # 通知调用方工具执行完成（供摘要助手捕获 save_diary_entry 参数等）
                if on_tool_result:
                    try:
                        on_tool_result(tool_name, tool_args or {}, tool_result)
                    except Exception as cb_err:
                        logger.warning(f"on_tool_result 回调失败: {cb_err}")

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
    except (asyncio.CancelledError, GeneratorExit):
        # C4: 客户端断开 / 生成器被外层 aclose 时进入此分支。
        # CancelledError 与 GeneratorExit 均为 BaseException 子类，不会被上面的 except Exception 捕获。
        # 主动 aclose 当前轮的上游 vLLM 流，触发 httpx async-with 上下文退出，关闭 HTTP 连接，
        # 从而让 vLLM 停止继续生成 token（满足 C4.1/C4.2）。
        upstream = current_upstream
        current_upstream = None
        if upstream is not None:
            try:
                await upstream.aclose()
            except Exception as cleanup_err:
                logger.warning(f"aclose 上游 vLLM 流失败: {cleanup_err}")
        logger.info("共享流式聊天被取消/断开，已释放上游 vLLM 流")
        # 更新状态对象（部分内容）
        state.accumulated_response = accumulated_response
        state.full_thinking = full_thinking
        # 取消/关闭异常必须继续向上抛出，使 Starlette StreamingResponse 正确终止
        raise
