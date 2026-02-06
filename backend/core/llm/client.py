from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import logging
import httpx
import json

logger = logging.getLogger(__name__)


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


class LLMConnectionError(LLMError):
    """LLM连接错误"""
    pass


class LLMTimeoutError(LLMError):
    """LLM超时错误"""
    pass


class LLMRateLimitError(LLMError):
    """LLM速率限制错误"""
    pass


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


class LLMClient(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: List[Dict],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict],
        **kwargs
    ):
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
        max_tokens: int = 4096
    ):
        self.host = host.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _validate_messages(self, messages: List[Dict]) -> None:
        """验证消息格式"""
        if not messages:
            raise ValueError("消息列表不能为空")
        
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"消息 {i} 必须是字典类型")
            if "role" not in msg:
                raise ValueError(f"消息 {i} 缺少 'role' 字段")
            if "content" not in msg:
                raise ValueError(f"消息 {i} 缺少 'content' 字段")
            if msg["role"] not in ["system", "user", "assistant"]:
                raise ValueError(f"消息 {i} 的 role 必须是 'system', 'user' 或 'assistant'")

    async def chat(
        self,
        messages: List[Dict],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求
        
        Args:
            messages: 消息列表
            stream: 是否流式响应
            **kwargs: 额外参数
            
        Returns:
            LLMResponse: 包含响应内容或错误信息
        """
        try:
            # 验证输入
            self._validate_messages(messages)
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.host}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": stream,
                        "options": {
                            "temperature": kwargs.get("temperature", self.temperature),
                            "num_predict": kwargs.get("max_tokens", self.max_tokens)
                        }
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    return LLMResponse(
                        content=result.get("message", {}).get("content", ""),
                        finish_reason=result.get("done_reason", "stop"),
                        usage=result.get("eval_count", {})
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
                            "host": self.host
                        }
                    )

        except httpx.ConnectError as e:
            error_msg = f"无法连接到Ollama服务器: {self.host}"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e), "host": self.host}
            )
        except httpx.TimeoutException as e:
            error_msg = "Ollama服务器响应超时"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)}
            )
        except ValueError as e:
            error_msg = f"请求参数错误: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)}
            )
        except Exception as e:
            error_msg = f"Ollama调用失败: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)}
            )

    async def stream_chat(self, messages: List[Dict], **kwargs):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.host}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "options": {
                            "temperature": kwargs.get("temperature", self.temperature),
                            "num_predict": kwargs.get("max_tokens", self.max_tokens)
                        }
                    }
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                content = data.get("message", {}).get("content", "")
                                yield content
                                if data.get("done", False):
                                    break
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """使用Ollama获取文本的向量嵌入"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.host}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": text
                    }
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
        host: str = "http://localhost:8000",
        model: str = "llama3.2",
        temperature: float = 0.7,
        max_tokens: int = 4096
    ):
        self.host = host.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _validate_messages(self, messages: List[Dict]) -> None:
        """验证消息格式"""
        if not messages:
            raise ValueError("消息列表不能为空")
        
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"消息 {i} 必须是字典类型")
            if "role" not in msg:
                raise ValueError(f"消息 {i} 缺少 'role' 字段")
            if "content" not in msg:
                raise ValueError(f"消息 {i} 缺少 'content' 字段")
            if msg["role"] not in ["system", "user", "assistant"]:
                raise ValueError(f"消息 {i} 的 role 必须是 'system', 'user' 或 'assistant'")

    async def chat(
        self,
        messages: List[Dict],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求
        
        Args:
            messages: 消息列表
            stream: 是否流式响应
            **kwargs: 额外参数
            
        Returns:
            LLMResponse: 包含响应内容或错误信息
        """
        try:
            # 验证输入
            self._validate_messages(messages)
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.host}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": stream,
                        "temperature": kwargs.get("temperature", self.temperature),
                        "max_tokens": kwargs.get("max_tokens", self.max_tokens)
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    choice = result["choices"][0]
                    return LLMResponse(
                        content=choice["message"]["content"],
                        finish_reason=choice.get("finish_reason", "stop"),
                        usage=result.get("usage", {})
                    )
                else:
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
                            "host": self.host
                        }
                    )

        except httpx.ConnectError as e:
            error_msg = f"无法连接到VLLM服务器: {self.host}"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e), "host": self.host}
            )
        except httpx.TimeoutException as e:
            error_msg = "VLLM服务器响应超时"
            logger.error(f"{error_msg}, {e}")
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)}
            )
        except (KeyError, IndexError) as e:
            error_msg = f"响应格式错误: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)}
            )
        except ValueError as e:
            error_msg = f"请求参数错误: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)}
            )
        except Exception as e:
            error_msg = f"VLLM调用失败: {e}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                finish_reason="error",
                error=error_msg,
                error_details={"exception": str(e)}
            )

    async def stream_chat(self, messages: List[Dict], **kwargs):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.host}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "temperature": kwargs.get("temperature", self.temperature),
                        "max_tokens": kwargs.get("max_tokens", self.max_tokens)
                    }
                ) as response:
                    async for line in response.aiter_lines():
                        if line and line.startswith("data: "):
                            data = line[6:]
                            if data != "[DONE]":
                                try:
                                    chunk = json.loads(data)
                                    content = chunk["choices"][0]["delta"].get("content", "")
                                    if content:
                                        yield content
                                except json.JSONDecodeError:
                                    continue

        except Exception as e:
            logger.error(f"VLLM流式调用失败: {e}")

    @property
    def model_name(self) -> str:
        return f"vllm/{self.model}"

    async def is_available(self) -> bool:
        """检查VLLM模型是否可用"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # VLLM 使用 /health 端点检查健康状态
                response = await client.get(f"{self.host}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """使用VLLM获取文本的向量嵌入
        
        VLLM 支持通过 /v1/embeddings 端点获取 embedding
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.host}/v1/embeddings",
                    json={
                        "model": self.model,
                        "input": text
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    # OpenAI 格式返回 embedding 在 data[0].embedding
                    if "data" in result and len(result["data"]) > 0:
                        return result["data"][0].get("embedding")
                    return None
                else:
                    logger.warning(f"VLLM获取embedding失败: HTTP {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"VLLM获取embedding失败: {e}")
            return None


class LLMFactory:
    _clients: Dict[str, LLMClient] = {}

    @classmethod
    def create_client(
        cls,
        provider: str = "ollama",
        **kwargs
    ) -> LLMClient:
        key = f"{provider}:{kwargs.get('model', 'default')}"

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
        cls._clients.clear()
