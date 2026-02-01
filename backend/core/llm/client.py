from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging
import httpx
import json

logger = logging.getLogger(__name__)


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

    async def chat(
        self,
        messages: List[Dict],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        try:
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
                    logger.error(f"Ollama错误: {response.status_code}")
                    return LLMResponse(content="", finish_reason="error")

        except Exception as e:
            logger.error(f"Ollama调用失败: {e}")
            return LLMResponse(content="", finish_reason="error")

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

    async def chat(
        self,
        messages: List[Dict],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        try:
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
                    logger.error(f"VLLM错误: {response.status_code}")
                    return LLMResponse(content="", finish_reason="error")

        except Exception as e:
            logger.error(f"VLLM调用失败: {e}")
            return LLMResponse(content="", finish_reason="error")

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
