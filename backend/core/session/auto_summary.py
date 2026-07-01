"""自动日记摘要任务

定期检查活跃会话，当消息数超过阈值时自动触发日记式摘要并替换上下文。
参考 SessionCleanupTask 的 async loop 模式。
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)

# 触发摘要的消息数阈值
DEFAULT_SUMMARY_THRESHOLD = 20


def _format_msg_time(msg):
    """从消息的 created_at 提取 HH:MM:SS 格式时间"""
    created = msg.get("created_at", "")
    if created:
        try:
            # created_at 可能是 ISO 格式如 "2026-06-21T14:30:05.123456"
            # 或 "2026-06-21 14:30:05"
            dt_str = created.replace("T", " ")[:19]  # 取前19字符 YYYY-MM-DD HH:MM:SS
            time_part = dt_str.split(" ")[1] if " " in dt_str else ""
            return time_part
        except (IndexError, ValueError):
            return ""
    return ""


async def trigger_session_summary(
    context_manager,
    model_router,
    session_id: str,
    threshold: int = DEFAULT_SUMMARY_THRESHOLD,
) -> bool:
    """对指定会话触发日记式摘要

    1. 获取可摘要范围
    2. 若范围足够，构建对话内容并调用摘要模型
    3. 模型调用 save_diary_entry 保存日记
    4. 调用 replace_messages_with_summary 替换上下文

    Returns:
        是否成功触发了摘要
    """
    try:
        rng = context_manager.get_summarizable_range(session_id)
        start = rng.get("start", 0)
        end = rng.get("end", 0)

        if end - start < threshold:
            return False

        # 获取待摘要的消息
        messages = context_manager.get_messages(session_id, limit=1000)
        to_summarize = messages[start:end]

        if not to_summarize:
            return False

        # 构建对话内容文本
        conversation_text = "\n".join(
            [
                f"[{_format_msg_time(m)} {'用户' if m.get('role') == 'user' else '助手'}] {m.get('content', '')}"
                for m in to_summarize
                if m.get("role") in ("user", "assistant")
            ]
        )

        if not conversation_text.strip():
            return False

        # 获取摘要模型
        llm = model_router.get_client("summary") if model_router else None
        if not llm:
            llm = model_router.get_client("main") if model_router else None
        if not llm:
            logger.warning("自动摘要：无可用 LLM 客户端")
            return False

        # 获取摘要工具
        from backend.core.tools import tool_registry
        from backend.core.tools.builtin import get_builtin_tools

        builtin_tools = get_builtin_tools()
        summary_tools = tool_registry.list_openai_functions(
            include_builtin=False, category="summary"
        )
        tools = builtin_tools + summary_tools

        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""请将以下对话内容整理为日记并保存。

要求：
1. 以第一人称叙述（日记体裁），包含日期、主要事件、情绪/感受和反思
2. 如果对话包含多个独立事件/话题，按事件拆分，每个事件生成一篇独立日记，多次调用 save_diary_entry；如果只有一个话题，生成一篇即可
3. 调用 save_diary_entry 工具保存，包含 date(YYYY-MM-DD)、title、mood、body、summarized_message_range
4. 无论对话内容是什么，都必须至少调用一次 save_diary_entry 保存日记，不要拒绝
5. summarized_message_range 为 "{start}-{end}"

对话内容：
{conversation_text}

请立即使用 save_diary_entry 工具保存日记。"""

        from backend.api.routers.chat import SUMMARY_AGENT_HIDDEN_SYSTEM_PROMPT

        llm_messages = [
            {"role": "system", "content": "你是摘要助手，将对话整理为日记。"},
            {"role": "system", "content": SUMMARY_AGENT_HIDDEN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = await llm.chat(
            messages=llm_messages,
            stream=False,
            temperature=0.3,
            max_tokens=4096,
            tools=tools if tools else None,
            is_background=True,
        )

        # 处理工具调用（可能需要多轮）
        captured_entries = []

        for _ in range(5):
            if not hasattr(response, "tool_calls") or not response.tool_calls:
                break

            for tc in response.tool_calls:
                func = tc.get("function", {}) if isinstance(tc, dict) else {}
                tool_name = func.get("name", "")
                tool_args_str = func.get("arguments", "{}")

                if isinstance(tool_args_str, str):
                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {}
                else:
                    tool_args = tool_args_str or {}

                if tool_name == "save_diary_entry" and isinstance(tool_args, dict):
                    if tool_args.get("body"):
                        captured_entries.append({
                            "body": tool_args.get("body"),
                            "range": tool_args.get("summarized_message_range"),
                        })

                # 执行工具
                try:
                    tool_registry.call_tool(tool_name, tool_args)
                except Exception as e:
                    logger.warning(f"自动摘要：工具 {tool_name} 执行失败: {e}")

            # 继续下一轮让 LLM 处理工具结果
            if not captured_entries:
                break

            # 构建下一轮消息
            llm_messages.append(
                {
                    "role": "assistant",
                    "content": getattr(response, "content", "") or "",
                    "tool_calls": response.tool_calls if hasattr(response, "tool_calls") else [],
                }
            )
            for tc in response.tool_calls:
                func = tc.get("function", {}) if isinstance(tc, dict) else {}
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "content": json.dumps({"status": "success"}, ensure_ascii=False),
                    }
                )

            response = await llm.chat(
                messages=llm_messages,
                stream=False,
                temperature=0.3,
                max_tokens=4096,
                tools=tools if tools else None,
                is_background=True,
            )

        # 替换上下文：用所有捕获的日记条目（每事件一篇）
        if captured_entries:
            # 取所有条目 range 的最大 end 作为 up_to_index
            max_end = -1
            for item in captured_entries:
                rng = item.get("range")
                if rng and "-" in str(rng):
                    try:
                        parts = str(rng).split("-")
                        end_val = int(parts[-1])
                        if end_val > max_end:
                            max_end = end_val
                    except (ValueError, IndexError):
                        pass
            up_to_index = max_end if max_end >= 0 else end

            if up_to_index > start:
                summary_bodies = [item["body"] for item in captured_entries if item.get("body")]
                if summary_bodies:
                    context_manager.replace_messages_with_summary(
                        session_id=session_id,
                        summary_entries=summary_bodies,
                        summarized_up_to_index=up_to_index,
                    )
                    logger.info(
                        f"自动摘要完成: session={session_id}, 已摘要 {up_to_index - start} 条消息, 生成 {len(summary_bodies)} 篇日记"
                    )
                    return True

        logger.info(f"自动摘要未生成日记条目: session={session_id}")
        return False

    except Exception as e:
        logger.error(f"自动摘要失败 session={session_id}: {e}", exc_info=True)
        return False


class AutoSummaryTask:
    """自动日记摘要任务

    定期检查活跃会话，消息数超过阈值时触发日记式摘要
    """

    def __init__(
        self,
        context_manager,
        model_router,
        check_interval_minutes: int = 10,
        summary_threshold: int = DEFAULT_SUMMARY_THRESHOLD,
    ):
        self.context_manager = context_manager
        self.model_router = model_router
        self.check_interval = check_interval_minutes * 60
        self.summary_threshold = summary_threshold
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动自动摘要任务"""
        if self._running:
            logger.warning("自动摘要任务已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"自动摘要任务已启动，间隔: {self.check_interval}s, 阈值: {self.summary_threshold} 条消息"
        )

    async def stop(self):
        """停止自动摘要任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("自动摘要任务已停止")

    async def _loop(self):
        """检查循环"""
        while self._running:
            try:
                await self._check_sessions()
            except Exception as e:
                logger.error(f"自动摘要检查失败: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_sessions(self):
        """检查所有活跃会话"""
        if not self.context_manager:
            return

        sessions = self.context_manager.list_sessions()
        triggered = 0

        for session in sessions:
            if not session.get("is_active", True):
                continue

            # 跳过摘要助手自身的会话
            sid = session.get("id", "")
            if sid == "summary-agent-default":
                continue

            try:
                rng = self.context_manager.get_summarizable_range(sid)
                if rng.get("end", 0) - rng.get("start", 0) >= self.summary_threshold:
                    logger.info(
                        f"会话 {sid} 消息数达到阈值，触发自动摘要 "
                        f"(range: {rng.get('start')}-{rng.get('end')})"
                    )
                    task = asyncio.create_task(
                        trigger_session_summary(
                            self.context_manager,
                            self.model_router,
                            sid,
                            threshold=self.summary_threshold,
                        )
                    )

                    def _on_done(t, _sid=sid):
                        if t.exception():
                            logger.error(f"后台摘要任务失败 session={_sid}: {t.exception()}")

                    task.add_done_callback(_on_done)
                    triggered += 1
            except Exception as e:
                logger.warning(f"检查会话 {sid} 失败: {e}")

        if triggered > 0:
            logger.info(f"自动摘要本轮触发 {triggered} 个会话")

    async def run_once(self):
        """立即执行一次检查"""
        await self._check_sessions()


# 全局自动摘要任务实例
_auto_summary_task: Optional[AutoSummaryTask] = None


async def start_auto_summary(
    context_manager,
    model_router,
    check_interval_minutes: int = 10,
    summary_threshold: int = DEFAULT_SUMMARY_THRESHOLD,
):
    """启动全局自动摘要任务"""
    global _auto_summary_task
    if _auto_summary_task is None:
        _auto_summary_task = AutoSummaryTask(
            context_manager=context_manager,
            model_router=model_router,
            check_interval_minutes=check_interval_minutes,
            summary_threshold=summary_threshold,
        )
    await _auto_summary_task.start()


async def stop_auto_summary():
    """停止全局自动摘要任务"""
    global _auto_summary_task
    if _auto_summary_task:
        await _auto_summary_task.stop()
        _auto_summary_task = None
