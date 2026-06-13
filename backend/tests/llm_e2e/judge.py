"""LLM 评判代理 - 使用 vLLM + gemma4 进行自动化质量评判"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import asyncio

import requests

from .judge_tools import JUDGE_TOOLS, ToolExecutor

# 最大工具调用轮数，防止无限循环
MAX_TOOL_ROUNDS = 3


@dataclass
class JudgeResult:
    """评判结果"""

    score: int  # 1-5
    reason: str
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)


# ========== 评判提示词模板 ==========

_SYSTEM_PROMPT_RESPONSE = """你是一个专业的AI系统测试评判员。你的任务是评估AI助手的回复质量。

评估维度：
1. 相关性：回复是否与用户问题相关
2. 正确性：回复内容是否准确无误
3. 完整性：回复是否充分回答了用户的问题
4. 有用性：回复是否对用户有帮助

请以JSON格式返回评估结果：
{"score": 1-5, "reason": "详细理由"}

评分标准：
5分：完全正确、相关、完整
4分：基本正确，有小瑕疵
3分：部分正确，有明显不足
2分：大部分不正确或不相关
1分：完全错误或无关"""

_SYSTEM_PROMPT_MEMORY_SEARCH = """你是一个专业的AI系统测试评判员。你的任务是评估记忆搜索结果的质量。

评估维度：
1. 语义相关性：搜索结果是否与查询语义相关
2. 排序合理性：更相关的结果是否排在前面
3. 完整性：是否遗漏了明显应该返回的记忆
4. 准确性：返回的记忆内容是否准确

请以JSON格式返回评估结果：
{"score": 1-5, "reason": "详细理由"}

评分标准：
5分：搜索结果完全相关且排序合理
4分：大部分结果相关，排序基本合理
3分：部分结果相关，排序有改进空间
2分：大部分结果不相关
1分：搜索结果完全无关"""

_SYSTEM_PROMPT_TOOL_CALL = """你是一个专业的AI系统测试评判员。你的任务是评估工具调用的正确性。

评估维度：
1. 工具选择：是否选择了正确的工具
2. 参数正确性：传递的参数是否正确
3. 结果处理：是否正确使用了工具返回的结果
4. 最终回复：基于工具结果的最终回复是否准确完整

请以JSON格式返回评估结果：
{"score": 1-5, "reason": "详细理由"}

评分标准：
5分：工具选择正确，参数准确，结果处理完美
4分：工具选择正确，参数基本准确，结果处理有小问题
3分：工具选择基本正确，但参数或结果处理有明显问题
2分：工具选择或参数大部分不正确
1分：工具调用完全错误或无关"""

_SYSTEM_PROMPT_CONTEXT_COHERENCE = """你是一个专业的AI系统测试评判员。你的任务是评估多轮对话的上下文连贯性。

评估维度：
1. 上下文保持：系统是否正确保留了之前对话的内容
2. 指代消解：系统是否正确理解了代词和省略指代
3. 信息累积：系统是否在多轮对话中累积和利用了信息
4. 一致性：系统的回复是否在多轮对话中保持一致

请以JSON格式返回评估结果：
{"score": 1-5, "reason": "详细理由"}

评分标准：
5分：上下文完全连贯，所有指代和信息都正确处理
4分：上下文基本连贯，有小的遗漏或不一致
3分：部分上下文丢失，有明显的指代消解问题
2分：大量上下文丢失，回复与历史脱节
1分：完全没有上下文意识，每轮对话独立"""

# 带工具的提示词版本
_SYSTEM_PROMPT_RESPONSE_WITH_TOOLS = _SYSTEM_PROMPT_RESPONSE.replace(
    "请以JSON格式返回评估结果：",
    "你可以使用辅助工具来验证系统的行为。例如，你可以搜索记忆库来验证记忆是否被正确存储。\n\n请以JSON格式返回评估结果："
)

_SYSTEM_PROMPT_MEMORY_SEARCH_WITH_TOOLS = _SYSTEM_PROMPT_MEMORY_SEARCH.replace(
    "请以JSON格式返回评估结果：",
    "你可以使用 search_memories 工具来交叉验证搜索结果。\n\n请以JSON格式返回评估结果："
)

_SYSTEM_PROMPT_TOOL_CALL_WITH_TOOLS = _SYSTEM_PROMPT_TOOL_CALL.replace(
    "请以JSON格式返回评估结果：",
    "你可以使用 list_tools 工具来验证系统中的工具是否可用。\n\n请以JSON格式返回评估结果："
)

_SYSTEM_PROMPT_CONTEXT_COHERENCE_WITH_TOOLS = _SYSTEM_PROMPT_CONTEXT_COHERENCE.replace(
    "请以JSON格式返回评估结果：",
    "你可以使用 get_chat_history 工具来验证对话历史是否完整保留。\n\n请以JSON格式返回评估结果："
)


class JudgeAgent:
    """LLM 评判代理，使用 vLLM + gemma4 通过 function calling 进行自动化质量评判。"""

    def __init__(self, config: Any, tool_executor: ToolExecutor) -> None:
        """初始化评判代理。

        Args:
            config: TestConfig 配置对象，需包含以下属性：
                - judge_vllm_base_url: vLLM 服务地址
                - judge_model: 评判模型名称
                - chat_timeout: 聊天超时时间
                - judge_supports_tools: 评判模型是否支持工具调用
            tool_executor: ToolExecutor 工具执行器实例
        """
        self.config = config
        self.tool_executor = tool_executor
        self.base_url = config.judge_vllm_base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.timeout = config.chat_timeout
        self.model = getattr(config, "judge_model", "gemma4")
        self.api_key = getattr(config, "judge_api_key", "") or ""
        self.supports_tools = getattr(config, "judge_supports_tools", True)

    async def judge_response(
        self,
        user_message: str,
        system_response: str,
        context: str = "",
    ) -> JudgeResult:
        """评判聊天回复的质量。

        Args:
            user_message: 用户消息
            system_response: 系统回复
            context: 额外上下文信息

        Returns:
            JudgeResult 评判结果
        """
        user_prompt = f"用户消息：{user_message}\n\n系统回复：{system_response}"
        if context:
            user_prompt += f"\n\n额外上下文：{context}"

        return await self._call_judge(
            system_prompt=_SYSTEM_PROMPT_RESPONSE_WITH_TOOLS if self.supports_tools else _SYSTEM_PROMPT_RESPONSE,
            user_prompt=user_prompt,
        )

    async def judge_memory_search(
        self, query: str, search_results: List[Dict[str, Any]]
    ) -> JudgeResult:
        """评判记忆搜索结果的语义相关性。

        Args:
            query: 搜索查询
            search_results: 搜索结果列表

        Returns:
            JudgeResult 评判结果
        """
        results_text = json.dumps(search_results, ensure_ascii=False, default=str)
        user_prompt = f"搜索查询：{query}\n\n搜索结果：{results_text}"

        return await self._call_judge(
            system_prompt=_SYSTEM_PROMPT_MEMORY_SEARCH_WITH_TOOLS if self.supports_tools else _SYSTEM_PROMPT_MEMORY_SEARCH,
            user_prompt=user_prompt,
        )

    async def judge_tool_call(
        self,
        user_message: str,
        tool_calls: List[Dict[str, Any]],
        tool_results: List[Dict[str, Any]],
        final_response: str,
    ) -> JudgeResult:
        """评判工具调用的正确性。

        Args:
            user_message: 用户消息
            tool_calls: 工具调用列表
            tool_results: 工具返回结果列表
            final_response: 最终回复

        Returns:
            JudgeResult 评判结果
        """
        user_prompt = (
            f"用户消息：{user_message}\n\n"
            f"工具调用：{json.dumps(tool_calls, ensure_ascii=False, default=str)}\n\n"
            f"工具结果：{json.dumps(tool_results, ensure_ascii=False, default=str)}\n\n"
            f"最终回复：{final_response}"
        )

        return await self._call_judge(
            system_prompt=_SYSTEM_PROMPT_TOOL_CALL_WITH_TOOLS if self.supports_tools else _SYSTEM_PROMPT_TOOL_CALL,
            user_prompt=user_prompt,
        )

    async def judge_context_coherence(
        self, messages: List[Dict[str, str]], response: str
    ) -> JudgeResult:
        """评判多轮对话的上下文连贯性。

        Args:
            messages: 对话消息列表
            response: 最终回复

        Returns:
            JudgeResult 评判结果
        """
        messages_text = json.dumps(messages, ensure_ascii=False)
        user_prompt = f"对话历史：\n{messages_text}\n\n最终回复：{response}"

        return await self._call_judge(
            system_prompt=_SYSTEM_PROMPT_CONTEXT_COHERENCE_WITH_TOOLS if self.supports_tools else _SYSTEM_PROMPT_CONTEXT_COHERENCE,
            user_prompt=user_prompt,
        )

    async def _call_judge(
        self, system_prompt: str, user_prompt: str
    ) -> JudgeResult:
        """核心方法：调用评判 LLM，支持工具调用循环。

        流程：
        1. 发送消息和工具定义到 vLLM
        2. 如果响应包含 tool_calls，执行工具并将结果加入消息，继续调用
        3. 最多进行 MAX_TOOL_ROUNDS 轮工具调用
        4. 解析最终文本响应中的评分和理由

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词

        Returns:
            JudgeResult 评判结果
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 是否使用工具（vLLM 可能不支持 tool calling，首次失败后禁用）
        use_tools = self.supports_tools

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        url = f"{self.base_url}/v1/chat/completions"

        def _do_post(req_body, req_headers):
            return requests.post(url, json=req_body, headers=req_headers, timeout=self.timeout)

        for _ in range(MAX_TOOL_ROUNDS + 1):
            request_body = {
                "model": self.model,
                "messages": messages,
                "temperature": getattr(self.config, "judge_temperature", 0.1),
                "max_tokens": getattr(self.config, "judge_max_tokens", 1024),
            }
            if use_tools:
                request_body["tools"] = JUDGE_TOOLS

            try:
                response = await asyncio.to_thread(_do_post, request_body, headers)
                response.raise_for_status()
            except requests.HTTPError as e:
                # 如果带工具请求返回 400，尝试不带工具重试
                status_code = e.response.status_code if e.response is not None else 0
                if status_code == 400 and use_tools:
                    use_tools = False
                    continue
                return JudgeResult(
                    score=3,
                    reason=f"评判请求失败: HTTP {status_code}",
                    passed=False,
                    details={"error": str(e)},
                )
            except requests.RequestException as e:
                # 网络错误时重试一次（可能是连接超时或被重置）
                try:
                    response = await asyncio.to_thread(_do_post, request_body, headers)
                    response.raise_for_status()
                except Exception as retry_err:
                    return JudgeResult(
                        score=3,
                        reason=f"评判请求网络错误(重试后): {retry_err}",
                        passed=False,
                        details={"error": str(e), "retry_error": str(retry_err)},
                    )

            data = response.json()
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})

            # 检查是否有工具调用
            tool_calls = message.get("tool_calls")
            if tool_calls:
                # 将助手消息（含工具调用）加入消息列表
                messages.append(message)

                # 执行每个工具调用
                for tool_call in tool_calls:
                    func = tool_call.get("function", {})
                    tool_name = func.get("name", "")
                    try:
                        tool_args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        tool_args = {}

                    tool_result = await self.tool_executor.execute(tool_name, tool_args)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": tool_result,
                        }
                    )

                # 继续下一轮调用
                continue

            # 没有工具调用，解析最终文本
            content = message.get("content", "")
            return self._parse_judge_response(content)

        # 超过最大工具调用轮数
        return JudgeResult(
            score=3,
            reason="评判超过最大工具调用轮数限制",
            passed=False,
            details={"max_rounds_reached": True},
        )

    def _parse_judge_response(self, content: str) -> JudgeResult:
        """解析评判 LLM 的文本响应，提取评分和理由。

        尝试以下解析策略：
        1. 从文本中提取 JSON 对象
        2. 从文本中匹配评分模式（如 "评分: 4" 或 "Score: 4/5"）
        3. 默认评分为 3

        Args:
            content: LLM 返回的文本内容

        Returns:
            JudgeResult 评判结果
        """
        if not content:
            return JudgeResult(
                score=3,
                reason="评判返回空内容",
                passed=False,
                details={"raw_content": content},
            )

        # 策略1：提取 JSON
        score, reason = self._try_parse_json(content)
        if score is not None:
            return JudgeResult(
                score=score,
                reason=reason,
                passed=score >= 4,
                details={"raw_content": content},
            )

        # 策略2：匹配评分模式
        score = self._try_extract_score(content)
        if score is not None:
            return JudgeResult(
                score=score,
                reason=content.strip(),
                passed=score >= 4,
                details={"raw_content": content, "parse_method": "pattern"},
            )

        # 策略3：默认评分
        return JudgeResult(
            score=3,
            reason=f"无法解析评判结果，原始内容：{content[:200]}",
            passed=False,
            details={"raw_content": content, "parse_method": "fallback"},
        )

    def _try_parse_json(self, content: str) -> tuple:
        """尝试从文本中提取 JSON 评分对象。

        Args:
            content: 文本内容

        Returns:
            (score, reason) 元组，解析失败返回 (None, None)
        """
        # 尝试直接解析整个内容
        try:
            result = json.loads(content.strip())
            if isinstance(result, dict) and "score" in result:
                return (
                    self._clamp_score(result["score"]),
                    result.get("reason", ""),
                )
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        json_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        for match in re.finditer(json_block_pattern, content, re.DOTALL):
            try:
                result = json.loads(match.group(1).strip())
                if isinstance(result, dict) and "score" in result:
                    return (
                        self._clamp_score(result["score"]),
                        result.get("reason", ""),
                    )
            except json.JSONDecodeError:
                continue

        # 尝试从文本中提取花括号包围的 JSON
        brace_pattern = r"\{[^{}]*\"score\"\s*:\s*\d[^{}]*\}"
        for match in re.finditer(brace_pattern, content):
            try:
                result = json.loads(match.group(0))
                if isinstance(result, dict) and "score" in result:
                    return (
                        self._clamp_score(result["score"]),
                        result.get("reason", ""),
                    )
            except json.JSONDecodeError:
                continue

        return (None, None)

    def _try_extract_score(self, content: str) -> Optional[int]:
        """尝试从文本中匹配评分模式。

        支持的模式：
        - "评分: 4" / "评分：4"
        - "Score: 4" / "score: 4"
        - "4/5"
        - "4分"

        Args:
            content: 文本内容

        Returns:
            评分整数，匹配失败返回 None
        """
        patterns = [
            r"[评评]分[：:]\s*(\d)",  # 评分: 4
            r"[Ss]core[：:]\s*(\d)",  # Score: 4
            r"(\d)\s*/\s*5",  # 4/5
            r"(\d)\s*分",  # 4分
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return self._clamp_score(int(match.group(1)))

        return None

    @staticmethod
    def _clamp_score(score: int) -> int:
        """将评分限制在 1-5 范围内。

        Args:
            score: 原始评分

        Returns:
            限制后的评分
        """
        try:
            score = int(score)
        except (ValueError, TypeError):
            return 3
        return max(1, min(5, score))

    async def close(self) -> None:
        """关闭连接（requests 无需手动关闭）。"""
        pass
