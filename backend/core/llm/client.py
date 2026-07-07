import asyncio
import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


class LLMError(Exception):
    """LLM调用基础错误"""

    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_text = response_text

    def __str__(self):
        if self.status_code:
            return f"[HTTP {self.status_code}] {self.message}"
        return self.message


@dataclass
class LLMMessage:
    role: str
    content: str
    name: Optional[str] = None


@dataclass
class LLMResponse:
    content: str
    finish_reason: str
    usage: Dict = None
    error: str = None
    error_details: Dict = field(default_factory=dict)
    tool_calls: List[Dict] = field(default_factory=list)


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict], stream: bool = False, **kwargs) -> LLMResponse:
        pass

    @abstractmethod
    async def stream_chat(self, messages: List[Dict], **kwargs):
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """检查模型是否可用

        Returns:
            是否可用
        """
        pass

    @abstractmethod
    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本的向量嵌入

        Args:
            text: 输入文本

        Returns:
            向量列表或None
        """
        pass


class OllamaClient(LLMClient):
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3.2",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        dimension: int = 768,
        api_key: str = None,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.dimension = dimension
        self.api_key = api_key

    def _validate_messages(self, messages: List[Dict]) -> None:
        """验证消息格式"""
        if not messages:
            raise ValueError("消息列表不能为空")

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"消息 {i} 必须是字典类型")
            if "role" not in msg:
                raise ValueError(f"消息 {i} 缺少 'role' 字段")
            if "content" not in msg and msg["role"] != "tool":
                raise ValueError(f"消息 {i} 缺少 'content' 字段")
            if msg["role"] not in ["system", "user", "assistant", "tool"]:
                raise ValueError(f"消息 {i} 的 role 必须是 'system', 'user', 'assistant' 或 'tool'")

    async def chat(self, messages: List[Dict], stream: bool = False, **kwargs) -> LLMResponse:
        """发送聊天请求

        Args:
            messages: 消息列表
            stream: 是否流式响应
            **kwargs: 额外参数，支持 tools (工具列表)

        Returns:
            LLMResponse: 包含响应内容或错误信息
        """
        try:
            # 验证输入
            self._validate_messages(messages)

            # 构建请求体
            request_body = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": kwargs.get("temperature", self.temperature),
                    "num_predict": kwargs.get("max_tokens", self.max_tokens),
                },
            }

            # 添加工具支持 (如果提供了 tools)
            tools = kwargs.get("tools")
            if tools:
                request_body["tools"] = tools

            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                response = await client.post(f"{self.host}/api/chat", json=request_body)

                if response.status_code == 200:
                    result = response.json()
                    message = result.get("message") or {}

                    # 检查是否有工具调用
                    tool_calls = []
                    if message.get("tool_calls"):
                        tool_calls = message["tool_calls"]

                    # 优先使用 content，如果没有则使用 thinking（某些模型如 qwen3-vl）
                    content = message.get("content", "")
                    if not content:
                        content = message.get("thinking", "")

                    return LLMResponse(
                        content=content,
                        finish_reason=result.get("done_reason", "stop"),
                        usage={"eval_count": result.get("eval_count", 0)},
                        tool_calls=tool_calls,
                    )
                else:
                    # 详细的错误处理
                    error_text = response.text[:500] if response.text else "无响应内容"
                    logger.error(f"Ollama错误: HTTP {response.status_code}, {error_text}")

                    return LLMResponse(
                        content="",
                        finish_reason="error",
                        error=f"HTTP {response.status_code}",
                        error_details={
                            "status_code": response.status_code,
                            "response_text": error_text,
                            "model": self.model,
                            "host": self.host,
                        },
                    )

        except httpx.ConnectError as e:
            error_msg = f"无法连接到Ollama服务器: {self.host}"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e), "host": self.host},
            )
        except httpx.TimeoutException as e:
            error_msg = "Ollama服务器响应超时"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)},
            )
        except ValueError as e:
            error_msg = f"请求参数错误: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)},
            )
        except Exception as e:
            error_msg = f"Ollama调用失败: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)},
            )

    async def stream_chat(self, messages: List[Dict], **kwargs):
        try:
            request_body = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": kwargs.get("temperature", self.temperature),
                    "num_predict": kwargs.get("max_tokens", self.max_tokens),
                },
            }

            if "tools" in kwargs and kwargs["tools"]:
                request_body["tools"] = kwargs["tools"]

            # 添加 Authorization header 如果提供了 API Key
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                async with client.stream(
                    "POST", f"{self.host}/api/chat", json=request_body, headers=headers
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                message = data.get("message", {})

                                # 根据 Ollama 文档正确处理 thinking 和 content
                                thinking = message.get("thinking", "")
                                content = message.get("content", "")

                                # 如果 content 存在，作为最终回复
                                if content:
                                    yield {"type": "content", "content": content}
                                # 如果 content 为空但 thinking 存在，作为思考过程
                                elif thinking:
                                    yield {"type": "thinking", "content": thinking}

                                if data.get("done", False):
                                    break

                                tool_calls = message.get("tool_calls")
                                if tool_calls:
                                    yield {"type": "tool_calls", "tool_calls": tool_calls}
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error(f"Ollama流式调用失败: {e}")

    @property
    def model_name(self) -> str:
        return f"ollama/{self.model}"

    async def is_available(self) -> bool:
        """检查Ollama模型是否可用"""
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """使用Ollama获取文本的向量嵌入"""
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                response = await client.post(
                    f"{self.host}/api/embeddings", json={"model": self.model, "prompt": text}
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get("embedding")
                else:
                    logger.warning(f"Ollama获取embedding失败: HTTP {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Ollama获取embedding失败: {e}")
            return None


class VLLMClient(LLMClient):
    def __init__(
        self,
        host: str = "http://localhost:8100",
        model: str = "llama3.2",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        dimension: int = 768,
        embedding_host: str = None,
        embedding_model: str = None,
        api_key: Optional[str] = None,
        supports_tools: bool = True,
        max_concurrent: int = 4,
    ):
        self.host = host.rstrip("/")
        # 如果 host 已包含 /v1 后缀，去掉以避免拼接时重复
        if self.host.endswith("/v1"):
            self.host = self.host[:-3]
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.dimension = dimension
        # 独立的 embedding 端点配置
        self.embedding_host = (embedding_host or self.host).rstrip("/")
        self.embedding_model = embedding_model or self.model
        self.api_key = api_key
        self.supports_tools = supports_tools
        # 信号量控制并发上限（默认 4）；用户请求通过 _user_waiting 优先于后台任务
        # 注意：不再使用 _http_lock 全局串行，避免 locked()+release() 竞态与并发瓶颈
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._bg_semaphore = asyncio.Semaphore(max_concurrent)
        self._user_waiting = 0
        self._user_count_lock = asyncio.Lock()

    async def _acquire_http(self, is_background: bool = False):
        """获取 HTTP 访问权。用户请求优先于后台任务。

        通过 _semaphore / _bg_semaphore 控制并发上限；
        不再使用 _http_lock 全局串行，避免 locked()+release() 之间的竞态。
        """
        if is_background:
            await self._bg_semaphore.acquire()
            try:
                while True:
                    async with self._user_count_lock:
                        if self._user_waiting == 0:
                            break
                    await asyncio.sleep(0.05)
            except BaseException:
                self._bg_semaphore.release()
                raise
        else:
            async with self._user_count_lock:
                self._user_waiting += 1
            acquired_semaphore = False
            try:
                await self._semaphore.acquire()
                acquired_semaphore = True
                async with self._user_count_lock:
                    self._user_waiting -= 1
            except BaseException:
                if acquired_semaphore:
                    self._semaphore.release()
                raise

    def _release_http(self, is_background: bool = False):
        """释放 HTTP 访问权。仅释放信号量，不再操作 _http_lock。"""
        if is_background:
            self._bg_semaphore.release()
        else:
            self._semaphore.release()

    def _validate_messages(self, messages: List[Dict]) -> None:
        """验证消息格式"""
        if not messages:
            raise ValueError("消息列表不能为空")

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"消息 {i} 必须是字典类型")
            if "role" not in msg:
                raise ValueError(f"消息 {i} 缺少 'role' 字段")
            if "content" not in msg and msg["role"] != "tool":
                raise ValueError(f"消息 {i} 缺少 'content' 字段")
            if msg["role"] not in ["system", "user", "assistant", "tool"]:
                raise ValueError(f"消息 {i} 的 role 必须是 'system', 'user', 'assistant' 或 'tool'")

    def _parse_gemma4_tool_call(self, text: str) -> Optional[Dict]:
        """解析 gemma4 流式模式下的文本格式 tool_call。
        输入格式：<|tool_call>call:calculator{expression:<|"|>25 * 15<|"|>}<tool_call|>
        输出：{"id": "...", "type": "function", "function": {"name": "calculator", "arguments": '{"expression": "25 * 15"}'}}
        """
        import re
        import uuid

        inner = text.replace("<|tool_call>", "").replace("<tool_call|>", "").strip()
        if not inner.startswith("call:"):
            logger.warning(f"gemma4 tool_call 格式异常: {text[:200]}")
            return None

        inner = inner[5:]
        brace_idx = inner.find("{")
        if brace_idx == -1:
            logger.warning(f"gemma4 tool_call 缺少参数: {inner[:200]}")
            return None

        name = inner[:brace_idx].strip()
        args_str = inner[brace_idx:]
        args_str = args_str.replace('<|"|>', '"')

        try:
            args_dict = json.loads(args_str)
            args_json = json.dumps(args_dict, ensure_ascii=False)
        except json.JSONDecodeError:
            fixed = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', args_str)
            try:
                args_dict = json.loads(fixed)
                args_json = json.dumps(args_dict, ensure_ascii=False)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"gemma4 tool_call 参数解析失败，使用空参数。原始: {args_str[:200]}, 错误: {e}"
                )
                args_json = "{}"

        return {
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": args_json,
            },
        }

    async def chat(self, messages: List[Dict], stream: bool = False, is_background: bool = False, **kwargs) -> LLMResponse:
        """发送聊天请求

        Args:
            messages: 消息列表
            stream: 是否流式响应
            is_background: 是否为后台任务（用户请求优先）
            **kwargs: 额外参数（tools, temperature, max_tokens 等）

        Returns:
            LLMResponse: 包含响应内容或错误信息
        """
        await self._acquire_http(is_background=is_background)
        try:
            # 验证输入
            self._validate_messages(messages)

            request_body = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "temperature": kwargs.get("temperature", self.temperature),
            }
            max_tokens = kwargs.get("max_tokens", self.max_tokens)
            if max_tokens and max_tokens > 0:
                request_body["max_tokens"] = max_tokens

            # 添加 tools 参数（如果提供且模型支持）
            tools = kwargs.get("tools")
            if tools and self.supports_tools:
                request_body["tools"] = tools
            elif tools and not self.supports_tools:
                logger.debug(f"模型 {self.model} 不支持 tools，已跳过 tools 参数")

            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            url = f"{self.host}/v1/chat/completions"
            logger.info(f"VLLM请求: {url}, model={self.model}, supports_tools={self.supports_tools}, has_tools={bool(tools)}")

            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as http_client:
                response = await http_client.post(url, json=request_body, headers=headers)

                if response.status_code == 200:
                    result = response.json()
                    choice = result["choices"][0]
                    content = choice["message"].get("content")
                    if not content:
                        content = choice["message"].get("reasoning_content")
                    return LLMResponse(
                        content=content,
                        finish_reason=choice.get("finish_reason", "stop"),
                        usage=result.get("usage", {}),
                        tool_calls=choice["message"].get("tool_calls"),
                    )
                else:
                    # 如果带 tools 请求失败，尝试不带 tools 降级请求（复用同一 client）
                    if tools and response.status_code in (400, 422, 500):
                        err_body = response.text[:800] if response.text else ""
                        logger.warning(f"带 tools 请求失败 (HTTP {response.status_code})，尝试不带 tools 降级请求。错误体: {err_body}")
                        request_body_fallback = {k: v for k, v in request_body.items() if k != "tools"}
                        response = await http_client.post(url, json=request_body_fallback, headers=headers)
                        if response.status_code == 200:
                            result = response.json()
                            choice = result["choices"][0]
                            content = choice["message"].get("content")
                            if not content:
                                content = choice["message"].get("reasoning_content")
                            return LLMResponse(
                                content=content,
                                finish_reason=choice.get("finish_reason", "stop"),
                                usage=result.get("usage", {}),
                            )

                    # 详细的错误处理
                    error_text = response.text[:500] if response.text else "无响应内容"
                    logger.error(f"VLLM错误: HTTP {response.status_code}, {error_text}")

                    return LLMResponse(
                        content="",
                        finish_reason="error",
                        error=f"HTTP {response.status_code}",
                        error_details={
                            "status_code": response.status_code,
                            "response_text": error_text,
                            "model": self.model,
                            "host": self.host,
                        },
                    )

        except httpx.ConnectError as e:
            error_msg = f"无法连接到VLLM服务器: {self.host}"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e), "host": self.host},
            )
        except httpx.TimeoutException as e:
            # 如果带 tools 请求超时，尝试不带 tools 降级请求（新建独立 client）
            if tools:
                logger.warning(f"带 tools 请求超时，尝试不带 tools 降级请求")
                try:
                    request_body_fallback = {k: v for k, v in request_body.items() if k != "tools"}
                    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as fallback_client:
                        response = await fallback_client.post(url, json=request_body_fallback, headers=headers)
                        if response.status_code == 200:
                            result = response.json()
                            choice = result["choices"][0]
                            content = choice["message"].get("content")
                            if not content:
                                content = choice["message"].get("reasoning_content")
                            return LLMResponse(
                                content=content,
                                finish_reason=choice.get("finish_reason", "stop"),
                                usage=result.get("usage", {}),
                            )
                except Exception as fallback_err:
                    logger.error(f"降级请求也失败: {fallback_err}")

            error_msg = "VLLM服务器响应超时"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)},
            )
        except (KeyError, IndexError) as e:
            error_msg = f"响应格式错误: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)},
            )
        except ValueError as e:
            error_msg = f"请求参数错误: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)},
            )
        except Exception as e:
            error_msg = f"VLLM调用失败: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)},
            )
        finally:
            self._release_http(is_background=is_background)

    async def stream_chat(self, messages: List[Dict], is_background: bool = False, **kwargs):
        await self._acquire_http(is_background=is_background)
        try:
            enable_thinking = kwargs.get("enable_thinking", False)
            request_body = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "temperature": kwargs.get("temperature", self.temperature),
                "chat_template_kwargs": {"enable_thinking": enable_thinking},
            }
            max_tokens = kwargs.get("max_tokens", self.max_tokens)
            if max_tokens and max_tokens > 0:
                request_body["max_tokens"] = max_tokens

            if "tools" in kwargs and kwargs["tools"] and self.supports_tools:
                request_body["tools"] = kwargs["tools"]
            elif "tools" in kwargs and kwargs["tools"] and not self.supports_tools:
                logger.debug(f"模型 {self.model} 不支持 tools（stream_chat），已跳过 tools 参数")

            logger.debug(f"vLLM stream_chat 请求体: model={request_body.get('model')}, max_tokens={request_body.get('max_tokens', '未设置')}, tools={len(request_body.get('tools', []))}个")

            # 临时调试日志：捕获多轮工具调用第2轮的请求特征
            msg_summary = []
            for m in messages:
                role = m.get("role", "?")
                content = m.get("content")
                content_len = len(content) if isinstance(content, str) else 0
                has_tc = "tool_calls" in m
                tc_id = m.get("tool_call_id", "")
                msg_summary.append(f"{role}(content={content_len},tc={has_tc},tc_id={tc_id})")
            logger.info(f"stream_chat 请求消息概览: total={len(messages)}, summary={msg_summary}")

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            url = f"{self.host}/v1/chat/completions"

            # 增量拼接 tool_calls 的缓冲区
            # vLLM 流式返回 tool_calls 时是增量的：第一个 chunk 包含 id/name，
            # 后续 chunk 只包含 arguments 的片段，需要拼接
            tool_calls_accumulator: Dict[int, Dict] = {}

            # gemma4 流式模式把 tool_calls 作为 content 文本返回：
            # <|tool_call>call:calculator{expression:<|"|>25 * 15<|"|>}<tool_call|>
            # 需要检测标签并解析为结构化 tool_calls
            content_buffer = ""
            in_tool_call = False

            # 临时调试：流式 chunk 统计
            _dbg_chunks = 0
            _dbg_content_chars = 0
            _dbg_reasoning_chars = 0
            _dbg_tool_call_chunks = 0
            _dbg_finish_reason = None
            _dbg_first_chunk_preview = None
            # 新增：完整文本捕获（定位 tool_call 失败根因）
            _dbg_full_content = []  # 全部 content 文本
            _dbg_full_reasoning = []  # 全部 reasoning 文本
            _dbg_special_chunks = []  # 含特殊 token 的原始 delta（限前 20 条）
            _dbg_raw_first_chunks = []  # 前 5 条原始 delta JSON

            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), trust_env=False) as client:
                async with client.stream("POST", url, json=request_body, headers=headers) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        error_msg = error_text.decode("utf-8", errors="replace")[:500]
                        logger.error(f"VLLM流式调用失败: HTTP {response.status_code}, {error_msg}")
                        yield {"type": "error", "content": f"HTTP {response.status_code}: {error_msg}"}
                        return

                    async for line in response.aiter_lines():
                        if line:
                            decoded = line if isinstance(line, str) else line.decode("utf-8")
                            if decoded.startswith("data: "):
                                _dbg_chunks += 1
                                data = decoded[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    choice = chunk["choices"][0]
                                    delta = choice.get("delta", {})
                                    # 临时调试：捕获 finish_reason
                                    _fr = choice.get("finish_reason")
                                    if _fr:
                                        _dbg_finish_reason = _fr
                                    # 新增：前 5 条原始 delta JSON（用于排查字段结构）
                                    if len(_dbg_raw_first_chunks) < 5:
                                        _dbg_raw_first_chunks.append({
                                            "idx": _dbg_chunks,
                                            "delta": delta,
                                            "finish_reason": _fr,
                                        })
                                    # 新增：检测含特殊 token 的 chunk（限前 20 条）
                                    _delta_str = json.dumps(delta, ensure_ascii=False)
                                    if ("<|" in _delta_str or "tool_call" in _delta_str or "channel" in _delta_str) and len(_dbg_special_chunks) < 20:
                                        _dbg_special_chunks.append({
                                            "idx": _dbg_chunks,
                                            "delta": delta,
                                            "finish_reason": _fr,
                                        })
                                    reasoning_content = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                                    if reasoning_content and reasoning_content != "<pad>":
                                        _dbg_reasoning_chars += len(reasoning_content)
                                        _dbg_full_reasoning.append(reasoning_content)
                                        yield {"type": "thinking", "content": reasoning_content}
                                    content = delta.get("content", "")
                                    if content and content != "<pad>":
                                        _dbg_content_chars += len(content)
                                        _dbg_full_content.append(content)
                                    # 临时调试：捕获首 chunk 预览
                                    if _dbg_first_chunk_preview is None and (content or reasoning_content):
                                        _dbg_first_chunk_preview = (content or reasoning_content)[:80]
                                    if content and content != "<pad>":
                                        # gemma4 流式 tool_call 文本检测
                                        content_buffer += content
                                        if "<|tool_call>" in content_buffer and not in_tool_call:
                                            # 检测到 tool_call 开始标签
                                            in_tool_call = True
                                            # 提取标签前的正常 content（如果有）
                                            before_tag = content_buffer.split("<|tool_call>")[0]
                                            if before_tag:
                                                yield {"type": "content", "content": before_tag}
                                            content_buffer = "<|tool_call>" + content_buffer.split("<|tool_call>", 1)[1]
                                        elif in_tool_call:
                                            # 在 tool_call 内，继续缓冲
                                            if "<tool_call|>" in content_buffer:
                                                # 检测到结束标签，解析 tool_call
                                                in_tool_call = False
                                                parsed_tc = self._parse_gemma4_tool_call(content_buffer)
                                                if parsed_tc:
                                                    tool_calls_accumulator[0] = parsed_tc
                                                content_buffer = ""
                                            # 不 yield content，避免前端显示原始标签
                                        else:
                                            # 正常 content，直接 yield
                                            yield {"type": "content", "content": content}
                                            content_buffer = ""
                                    tool_calls = delta.get("tool_calls")
                                    if tool_calls:
                                        _dbg_tool_call_chunks += 1
                                        # 标准结构化 tool_calls（非 gemma4 文本格式）
                                        for tc in tool_calls:
                                            idx = tc.get("index", 0)
                                            if idx not in tool_calls_accumulator:
                                                tool_calls_accumulator[idx] = {
                                                    "id": tc.get("id", ""),
                                                    "type": tc.get("type", "function"),
                                                    "function": {
                                                        "name": tc.get("function", {}).get("name", ""),
                                                        "arguments": tc.get("function", {}).get("arguments", ""),
                                                    },
                                                }
                                            else:
                                                func_delta = tc.get("function", {})
                                                if func_delta.get("name"):
                                                    tool_calls_accumulator[idx]["function"]["name"] += func_delta["name"]
                                                if func_delta.get("arguments"):
                                                    tool_calls_accumulator[idx]["function"]["arguments"] += func_delta["arguments"]
                                                if tc.get("id"):
                                                    tool_calls_accumulator[idx]["id"] = tc["id"]
                                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                                    continue

                    # 流结束后，处理 buffer 中残留的 content
                    if content_buffer and not in_tool_call:
                        yield {"type": "content", "content": content_buffer}

                    # yield 拼接完成的 tool_calls
                    if tool_calls_accumulator:
                        complete_tool_calls = [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())]
                        logger.info(f"流式 tool_calls 拼接完成: {len(complete_tool_calls)} 个工具调用")
                        yield {"type": "tool_calls", "tool_calls": complete_tool_calls}

                    # 临时调试：流式统计汇总
                    logger.info(
                        f"stream_chat 流式统计: chunks={_dbg_chunks}, "
                        f"content_chars={_dbg_content_chars}, "
                        f"reasoning_chars={_dbg_reasoning_chars}, "
                        f"tool_call_chunks={_dbg_tool_call_chunks}, "
                        f"finish_reason={_dbg_finish_reason}, "
                        f"first_chunk_preview={repr(_dbg_first_chunk_preview) if _dbg_first_chunk_preview else None}"
                    )
                    # 新增：完整文本输出（截断到 1500 字符避免日志爆炸）
                    _full_content_text = "".join(_dbg_full_content)
                    _full_reasoning_text = "".join(_dbg_full_reasoning)
                    logger.info(
                        f"stream_chat 完整 content ({len(_full_content_text)} chars): "
                        f"{repr(_full_content_text[:1500])}"
                    )
                    logger.info(
                        f"stream_chat 完整 reasoning ({len(_full_reasoning_text)} chars): "
                        f"{repr(_full_reasoning_text[:1500])}"
                    )
                    # 新增：前 5 条原始 delta（排查字段结构）
                    logger.info(f"stream_chat 前5条原始 delta: {_dbg_raw_first_chunks}")
                    # 新增：含特殊 token 的 chunk（最多 20 条）
                    logger.info(f"stream_chat 特殊 token chunks ({len(_dbg_special_chunks)} 条): {_dbg_special_chunks}")

        except Exception as e:
            logger.error(f"VLLM流式调用失败: {e}")
            yield {"type": "error", "content": str(e)}
        finally:
            self._release_http(is_background=is_background)

    @property
    def model_name(self) -> str:
        return f"vllm/{self.model}"

    async def is_available(self) -> bool:
        """检查VLLM模型是否可用"""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            # 先尝试 /health（本地 vLLM），再尝试 /models（NVIDIA NIM 等云服务）
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                for endpoint in [f"{self.host}/health", f"{self.host}/models"]:
                    try:
                        response = await client.get(endpoint, headers=headers)
                        if response.status_code == 200:
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            return False

    async def warmup(self, timeout: float = 90.0) -> bool:
        """发送预热请求到 vLLM，触发模型加载与 kernel 编译。

        在后端启动时调用，确保首个用户请求不会承担冷启动延迟。
        失败不抛异常，仅记录警告。
        """
        import time as _time

        start = _time.monotonic()
        url = f"{self.host}/v1/chat/completions"
        request_body = {
            "model": self.model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 4,
            "temperature": 0.0,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=10.0), trust_env=False
            ) as client:
                response = await client.post(url, json=request_body, headers=headers)
                if response.status_code == 200:
                    elapsed_ms = int((_time.monotonic() - start) * 1000)
                    logger.info(f"vLLM 预热完成: {elapsed_ms}ms")
                    return True
                else:
                    logger.warning(
                        f"vLLM 预热返回非 200: HTTP {response.status_code}, "
                        f"body={response.text[:200]}"
                    )
                    return False
        except Exception as e:
            logger.warning(f"vLLM 预热失败（不阻断启动）: {e}")
            return False

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """使用VLLM获取文本的向量嵌入

        VLLM 支持通过 /v1/embeddings 端点获取 embedding
        使用独立的 embedding_host 和 embedding_model 配置
        """
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                response = await client.post(
                    f"{self.embedding_host}/v1/embeddings",
                    json={"model": self.embedding_model, "input": text},
                )

                if response.status_code == 200:
                    result = response.json()
                    # OpenAI 格式返回 embedding 在 data[0].embedding
                    if "data" in result and len(result["data"]) > 0:
                        return result["data"][0].get("embedding")
                    return None
                else:
                    logger.warning(f"VLLM获取embedding失败: HTTP {response.status_code} - {response.text[:200]}")
                    return None

        except Exception as e:
            logger.error(f"VLLM获取embedding失败: {e}")
            return None


class LLMFactory:
    _clients: Dict[str, LLMClient] = {}
    _clients_lock = threading.Lock()

    @classmethod
    def create_client(cls, provider: str = "ollama", **kwargs) -> LLMClient:
        key = f"{provider}:{kwargs.get('model', 'default')}"

        # 线程安全保护 _clients 字典（双重检查锁定，避免并发重复实例化）
        with cls._clients_lock:
            if key in cls._clients:
                return cls._clients[key]

            if provider == "ollama":
                client = OllamaClient(**kwargs)
            elif provider == "vllm":
                client = VLLMClient(**kwargs)
            else:
                raise ValueError(f"不支持的LLM提供商: {provider}")

            cls._clients[key] = client
            return client

    @classmethod
    def get_client(cls, provider: str = "ollama", **kwargs) -> LLMClient:
        return cls.create_client(provider, **kwargs)

    @classmethod
    def clear_cache(cls):
        with cls._clients_lock:
            cls._clients.clear()
