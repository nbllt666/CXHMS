"""模拟 LLM 客户端，用于端到端测试。

继承真实抽象基类 ``backend.core.llm.client.LLMClient``，实现一个确定性的、
不依赖外部服务的假 LLM。主要用途：
    - 在不调用真实模型（Ollama / vLLM）的情况下驱动聊天路由的完整流程
      （含流式 chunk 消费、工具调用循环、记忆/上下文管理等）。
    - 提供"上下文感知"的简单回复，便于断言对话上下文是否被正确传递。

stream_chat 产出的 chunk 为 dict，type 取值与真实路由 ``backend.api.routers.chat.py``
``generate_stream`` 消费的格式一致：
    - {"type": "thinking",  "content": "..."}
    - {"type": "content",   "content": "..."}
    - {"type": "tool_calls", "tool_calls": [...]}   # OpenAI function calling 格式
    - {"type": "error",     "content": "..."}
"""

import asyncio
import json
import re
from typing import Dict, List, Optional

from backend.core.llm.client import LLMClient, LLMResponse
from backend.tests.simulation.fakes.fake_embedding import FakeEmbeddingModel


# 匹配算式的正则：支持链式运算，如 "123+456"、"1+2*3-4"
_CALC_EXPRESSION_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*[-+*/]\s*)+\d+(?:\.\d+)?"
)

# 用户询问自己名字的问法
_ASK_NAME_RE = re.compile(
    r"我(?:叫什么(?:名字)?|叫啥(?:名字)?|的名字是什么|的名字叫什么|的称呼是什么)"
)

# 用户询问"我刚才说了什么"的问法
_ASK_LAST_MSG_RE = re.compile(
    r"我刚才(?:说了什么|说什么了|说的是什么)|你刚才听到我说了什么|重复一下我刚才"
)

# 从历史 user 消息中提取名字的模式（按优先级）
_NAME_DECL_PATTERNS = [
    re.compile(r"我的名字(?:叫|是|为)\s*([\w·]{2,10})"),
    re.compile(r"我叫\s*([\w·]{2,10})"),
    re.compile(r"我是\s*([\w·]{2,10})"),
]

# 时间/几点相关关键词
_TIME_KEYWORDS = ("时间", "现在几点", "几点了", "当前时间", "现在时间")

# 随机数相关关键词
_RANDOM_KEYWORDS = ("随机数", "random")

# JSON 格式化相关关键词
_JSON_FORMAT_KEYWORDS = ("格式化 json", "json 格式化", "format json")


class FakeLLMClient(LLMClient):
    """确定性假 LLM 客户端（继承真实 ABC 契约）。

    所有方法均为 async 且不触发任何网络 IO，可安全用于测试与 CI。

    Args:
        model: 模型名，``model_name`` 属性返回 ``fake/{model}``。
        temperature: 仅用于记录，不影响假回复（假 LLM 是确定性的）。
        max_tokens: 仅用于记录。
        dimension: embedding 维度（透传给 FakeEmbeddingModel，默认与之一致）。
        response_delay: 每个 chunk 前模拟的延迟秒数，用于测试流式时序。
        scripted_replies: 关键词 -> 回复 映射，``chat`` 会按子串匹配命中即返回。
        embedding_model: 可选的 FakeEmbeddingModel 注入实例；不传则在构造时创建一个。
    """

    def __init__(
        self,
        model: str = "fake-llm",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        dimension: int = 256,
        response_delay: float = 0.0,
        scripted_replies: Optional[Dict[str, str]] = None,
        embedding_model: Optional[FakeEmbeddingModel] = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.dimension = dimension
        self.response_delay = response_delay
        self.scripted_replies: Dict[str, str] = dict(scripted_replies or {})
        self._embedding_model = embedding_model or FakeEmbeddingModel()

    # ------------------------------------------------------------------ #
    # LLMClient ABC 实现
    # ------------------------------------------------------------------ #

    async def chat(
        self, messages: List[Dict], stream: bool = False, **kwargs
    ) -> LLMResponse:
        """生成确定性回复或工具调用。

        决策顺序：
            0. 检测 messages 末尾是否有 ``role=tool`` 消息 → 基于工具结果生成最终
               content，使工具调用循环在下一轮 break（不再触发新 tool_calls）。
            1. 工具调用关键词（计算 / 时间 / 随机数 / JSON 格式化）→ 返回带
               ``tool_calls`` 的响应。
            2. ``scripted_replies`` 子串匹配 → 返回对应回复。
            3. 上下文感知回复（询问名字 / 询问上一条消息）。
            4. 默认确认回复 ``收到：{user_text[:50]}``。
        """
        user_text = self._last_user_text(messages)

        # 0. 工具结果回传 → 生成最终 content，终止工具调用循环
        tool_reply = self._tool_result_reply(messages)
        if tool_reply is not None:
            prompt_chars = self._total_chars(messages)
            usage = {
                "prompt_tokens": prompt_chars // 4,
                "completion_tokens": max(len(tool_reply) // 4, 1),
                "total_tokens": (prompt_chars + len(tool_reply)) // 4,
            }
            return LLMResponse(
                content=tool_reply,
                finish_reason="stop",
                usage=usage,
            )

        # 1. 工具调用
        tool_calls = self._maybe_tool_calls(user_text)
        if tool_calls:
            prompt_chars = self._total_chars(messages)
            usage = {
                "prompt_tokens": prompt_chars // 4,
                "completion_tokens": 0,
                "total_tokens": prompt_chars // 4,
            }
            return LLMResponse(
                content="",
                finish_reason="tool_calls",
                usage=usage,
                tool_calls=tool_calls,
            )

        # 2. 脚本化回复（子串匹配）
        reply = None
        if self.scripted_replies:
            for keyword, text in self.scripted_replies.items():
                if keyword and keyword in user_text:
                    reply = text
                    break

        # 3. 上下文感知回复
        if reply is None:
            reply = self._context_aware_reply(messages, user_text)

        # 4. 默认回复（理论上 _context_aware_reply 已兜底，双保险）
        if reply is None:
            reply = f"收到：{user_text[:50]}"

        prompt_chars = self._total_chars(messages)
        usage = {
            "prompt_tokens": prompt_chars // 4,
            "completion_tokens": max(len(reply) // 4, 1),
            "total_tokens": (prompt_chars + len(reply)) // 4,
        }
        return LLMResponse(
            content=reply,
            finish_reason="stop",
            usage=usage,
        )

    async def stream_chat(self, messages: List[Dict], **kwargs):
        """异步生成器：产出 dict chunk，格式与真实路由消费的一致。

        流程：
            - 可选 ``response_delay`` 延迟。
            - 先 yield 一个 thinking chunk。
            - 调用 ``chat`` 计算回复：
                * 若产生 tool_calls → yield ``{"type": "tool_calls", ...}``。
                * 否则将 content 按每 8 字符一段切分，依次 yield content chunk。
        """
        if self.response_delay > 0:
            await asyncio.sleep(self.response_delay)

        yield {"type": "thinking", "content": "思考中..."}

        # 复用 chat() 的决策逻辑，避免重复实现
        response = await self.chat(messages, **kwargs)

        if self.response_delay > 0:
            await asyncio.sleep(self.response_delay)

        if response.tool_calls:
            yield {"type": "tool_calls", "tool_calls": response.tool_calls}
            return

        content = response.content or ""
        chunk_size = 8  # 每 5-10 字符一段
        for i in range(0, len(content), chunk_size):
            yield {"type": "content", "content": content[i : i + chunk_size]}
            if self.response_delay > 0:
                await asyncio.sleep(self.response_delay)

    @property
    def model_name(self) -> str:
        return f"fake/{self.model}"

    async def is_available(self) -> bool:
        return True

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """委托 FakeEmbeddingModel 生成确定性向量。"""
        return await self._embedding_model.get_embedding(text)

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    @staticmethod
    def _last_user_text(messages: List[Dict]) -> str:
        """取最后一条 user 消息的文本内容。"""
        for msg in reversed(messages or []):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    return content
                # 多模态 content（list[dict]）→ 拼接所有 text 部分
                if isinstance(content, list):
                    parts = [
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    return "".join(parts)
                return ""
        return ""

    @staticmethod
    def _total_chars(messages: List[Dict]) -> int:
        """统计所有消息内容的总字符数，用于估算 prompt_tokens。"""
        total = 0
        for msg in messages or []:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for p in content:
                    if isinstance(p, dict):
                        total += len(str(p.get("text", "")))
        return total

    @staticmethod
    def _tool_result_reply(messages: List[Dict]) -> Optional[str]:
        """检测 messages 末尾是否有 ``role=tool`` 消息，若有则基于工具结果生成最终 content。

        工具调用循环中，工具执行结果以 ``{"role": "tool", "tool_call_id": ...,
        "content": <json.dumps(result)>}`` 形式追加到 messages 末尾。检测到该消息
        说明工具已执行、结果已回传，此时应基于工具结果生成最终回复，使循环在
        下一轮 break（不再重新触发 tool_calls）。

        取最后一条 ``role=tool`` 消息的结果进行回复。返回 None 表示未检测到
        tool 消息，调用方应继续走原有决策流程。
        """
        last_tool_content: Optional[str] = None
        for msg in reversed(messages or []):
            if not isinstance(msg, dict):
                break
            if msg.get("role") != "tool":
                break
            content = msg.get("content")
            if isinstance(content, str):
                last_tool_content = content
                break
            # content 可能已被解析为 dict
            if isinstance(content, dict):
                last_tool_content = json.dumps(content, ensure_ascii=False)
                break
            break

        if last_tool_content is None:
            return None

        try:
            result = json.loads(last_tool_content)
        except (json.JSONDecodeError, TypeError):
            return f"工具已执行，结果：{last_tool_content[:200]}"

        if not isinstance(result, dict):
            return f"工具已执行，结果：{json.dumps(result, ensure_ascii=False)[:200]}"

        # 错误结果
        if result.get("error") is not None:
            return f"工具执行失败：{result.get('error')}"

        # calculator: {"success": True, "result": <数值>, "expression": "..."}
        if "result" in result and "expression" in result and result.get("success") is True:
            return f"{result.get('expression')} 的结果是 {result.get('result')}"

        # datetime: {"success": True, "formatted": str, ...}
        if "formatted" in result and "timestamp" in result:
            return f"当前时间是 {result.get('formatted')}"

        # random: {"success": True, "value": <数值>, ...}
        if "value" in result and "min" in result and "max" in result:
            return f"生成的随机数是 {result.get('value')}"

        # json_format: {"success": True, "formatted": str, "compact": str, "is_valid": bool, ...}
        if "formatted" in result and "compact" in result and "is_valid" in result:
            return f"格式化后的 JSON：\n{result.get('formatted')}"

        # 兜底：截断展示
        return f"工具已执行，结果：{json.dumps(result, ensure_ascii=False)[:200]}"

    def _maybe_tool_calls(self, user_text: str) -> List[Dict]:
        """识别工具调用关键词，返回 OpenAI function calling 格式的 tool_calls。

        - 包含"计算"且含数字算式 → calculate / calculator
        - 包含"时间"/"现在几点"等 → datetime
        - 包含"随机数"/"random" → random
        - 包含"格式化 json"/"json 格式化"/"format json" → json_format
        """
        tool_calls: List[Dict] = []

        # 计算工具
        if "计算" in user_text:
            match = _CALC_EXPRESSION_RE.search(user_text)
            if match:
                expression = match.group(0).replace(" ", "")
                tool_name = self._resolve_calc_tool_name()
                tool_calls.append(self._make_tool_call(tool_name, {"expression": expression}))

        # 时间工具（对齐内置工具名 "datetime"）
        if any(kw in user_text for kw in _TIME_KEYWORDS):
            tool_calls.append(self._make_tool_call("datetime", {}))

        # 随机数工具
        if any(kw in user_text.lower() for kw in _RANDOM_KEYWORDS):
            tool_calls.append(
                self._make_tool_call("random", {"min": 1, "max": 100, "type": "int"})
            )

        # JSON 格式化工具
        if any(kw in user_text.lower() for kw in _JSON_FORMAT_KEYWORDS):
            tool_calls.append(
                self._make_tool_call(
                    "json_format",
                    {"json_string": '{"a":1,"b":2}', "indent": 2},
                )
            )

        return tool_calls

    @staticmethod
    def _make_tool_call(name: str, arguments: Dict) -> Dict:
        """构造 OpenAI function calling 格式的 tool_call。"""
        return {
            "id": f"call_{abs(hash(name)) % 100000}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            },
        }

    @staticmethod
    def _resolve_calc_tool_name() -> str:
        """优先使用 "calculate"；若系统中不存在该工具则回退到 "calculator"。

        引入 try/except 是为了在隔离单元测试中（未初始化工具注册表）也能安全工作。
        """
        try:
            from backend.core.tools.builtin import BUILTIN_TOOL_NAMES
            from backend.core.tools import tool_registry

            if "calculate" in BUILTIN_TOOL_NAMES:
                return "calculate"
            if tool_registry.get_tool("calculate"):
                return "calculate"
            # "calculate" 不存在 → 回退到内置的 "calculator"
            return "calculator"
        except Exception:
            return "calculate"

    def _context_aware_reply(
        self, messages: List[Dict], user_text: str
    ) -> Optional[str]:
        """基于历史消息生成上下文感知回复。

        - 询问名字 → 从历史找最近一条名字声明，回复"你叫X"。
        - 询问"我刚才说了什么" → 回显上一条 user 消息。
        - 否则返回默认确认回复。
        """
        # 询问名字
        if _ASK_NAME_RE.search(user_text):
            name = self._find_name_in_history(messages)
            if name:
                return f"你叫{name}"
            return "我还不知道你的名字。"

        # 询问上一条消息
        if _ASK_LAST_MSG_RE.search(user_text):
            prev = self._previous_user_text(messages)
            if prev is not None:
                return f"你刚才说了：{prev}"
            return "你刚才没有说什么。"

        # 默认确认回复
        return f"收到：{user_text[:50]}"

    @staticmethod
    def _find_name_in_history(messages: List[Dict]) -> Optional[str]:
        """从历史 user 消息或系统记忆消息中倒序查找最近一次名字声明。

        跳过最后一条 user 消息（即当前提问，如"我叫什么"），
        避免把疑问词"什么"误当作名字捕获。

        优先从 user 消息中找（对话历史）；若找不到，再从 system 消息
        的"相关记忆"部分中找（模拟真实 LLM 从记忆增强上下文中理解信息）。
        """
        # 收集所有 user 文本消息，并丢弃最后一条（当前提问）
        user_texts: List[str] = []
        for msg in messages or []:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    user_texts.append(content)
        if len(user_texts) > 1:
            history_texts = user_texts[:-1]
            for content in reversed(history_texts):
                for pattern in _NAME_DECL_PATTERNS:
                    m = pattern.search(content)
                    if m:
                        return m.group(1).strip()

        # 从 system 消息的"相关记忆"部分中找（模拟记忆增强）
        for msg in messages or []:
            if not isinstance(msg, dict) or msg.get("role") != "system":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            # 匹配"相关记忆:\n- 我叫小明\n- ..." 格式
            if "相关记忆" in content:
                for pattern in _NAME_DECL_PATTERNS:
                    m = pattern.search(content)
                    if m:
                        return m.group(1).strip()
        return None

    @staticmethod
    def _previous_user_text(messages: List[Dict]) -> Optional[str]:
        """返回倒数第二条 user 消息的文本（即"上一条"用户消息）。"""
        user_texts = []
        for msg in messages or []:
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = msg.get("content")
            if isinstance(content, str):
                user_texts.append(content)
            elif isinstance(content, list):
                parts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                user_texts.append("".join(parts))
        if len(user_texts) >= 2:
            return user_texts[-2]
        return None


class FakeModelRouter:
    """确定性假模型路由器，用于端到端模拟测试。

    对齐真实 ``backend.core.model_router.ModelRouter`` 在路由、工具注册、
    副模型路由等场景中被调用的接口：

        - ``await initialize()``        生命周期初始化（no-op）
        - ``get_client(name)``          任意 name 均返回同一个 FakeLLMClient
        - ``get_secondary_client(name)`` 同上
        - ``model_name``                透传底层 FakeLLMClient.model_name
        - ``await close()``             生命周期关闭（no-op）
        - ``is_available(name)``        始终返回 True
        - ``get_config``/``get_model_info``/``get_all_models_info``/``get_all_status``
                                        返回合理默认字典
        - ``await check_status(name)``/``await check_all_status()``
                                        返回可用状态
        - ``await chat(name, messages)`` 委托给 FakeLLMClient
        - ``await get_embedding(name, text)`` 委托给 FakeLLMClient

    设计原则：所有 ``get_client`` 调用返回同一实例，保证 ``memory-agent`` 与
    ``summary-agent`` 路由（直接调用 ``model_router.get_client("memory"/"summary")``）
    不会因为 None 而崩溃。
    """

    def __init__(self, client: Optional[FakeLLMClient] = None) -> None:
        self._client: FakeLLMClient = client or FakeLLMClient()
        self._initialized = False

    # ---------------- 生命周期 ----------------
    async def initialize(self) -> None:
        self._initialized = True

    async def close(self) -> None:
        self._initialized = False

    # ---------------- 客户端获取 ----------------
    def get_client(self, model_type: str = "main"):
        return self._client

    def get_secondary_client(self, name: str):
        return self._client

    @property
    def model_name(self) -> str:
        return self._client.model_name

    # ---------------- 状态查询 ----------------
    def is_available(self, model_type: str = "main") -> bool:
        return True

    def get_config(self, model_type: str = "main"):
        return None

    def get_model_info(self, model_type: str = "main") -> Dict:
        return {
            "type": model_type,
            "provider": "fake",
            "model": self._client.model_name,
            "available": True,
        }

    def get_all_models_info(self) -> Dict[str, Dict]:
        info = self.get_model_info("main")
        return {"main": info, "summary": info, "memory": info}

    def get_all_status(self) -> Dict:
        return {}

    async def check_status(self, model_type: str):
        return {
            "name": model_type,
            "available": True,
            "last_check": "",
            "error": None,
        }

    async def check_all_status(self) -> Dict:
        return {}

    # ---------------- 委托调用 ----------------
    async def chat(self, model_type: str, messages: List[Dict], stream: bool = False, **kwargs):
        """委托给底层 FakeLLMClient，返回 dict 形式结果（兼容 ModelRouter.chat）。"""
        response = await self._client.chat(messages, stream=stream, **kwargs)
        return {
            "success": getattr(response, "finish_reason", "stop") != "error",
            "content": getattr(response, "content", ""),
            "finish_reason": getattr(response, "finish_reason", "stop"),
            "usage": getattr(response, "usage", None),
            "tool_calls": getattr(response, "tool_calls", None),
        }

    async def get_embedding(self, model_type: str, text: str) -> Optional[List[float]]:
        return await self._client.get_embedding(text)
