"""ModelRouter 客户端维度注入单元测试（模块1-20260926-08 修复）。

背景（真实验证发现）：
    真实 embedding 服务（Qwen3-Embedding-0.6B，别名 ``nomic-embed-text``）返回 **1024** 维，
    而 ``ModelRouter._create_client`` 构造 ``VLLMClient`` / ``OllamaClient`` 时未传 ``dimension``
    → 落到构造函数默认 **768**；该默认值又经 ``enable_vector_search`` 的
    ``embedding_model.dimension`` 优先规则决定向量库 collection 维度 →
    存储层按 768 构造、写入 1024 维真实索引 → HTTP 500（真实写入全部失败）。

修复口径：
    客户端 ``dimension`` 以配置 ``vector.embedding_dimension`` 为唯一真相源；
    配置缺失时保留 768 兜底（其它环境）。

覆盖点：
    1. 配置为 1024 → 客户端 ``dimension`` 为 1024（vllm / ollama 两种 provider）
    2. 配置缺失（None）→ 回退 768 兜底
"""

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def _model_config(provider: str = "vllm"):
    """构造一个最小可用的模型槽位配置（不触网）。"""
    from config.settings import ModelConfig

    return ModelConfig(
        provider=provider,
        host="http://localhost:8002",
        model="gemma4-e4b",
    )


def _router_with(monkeypatch, dimension, provider="vllm"):
    """构造裸 ModelRouter 并注入伪模型配置，返回 ``_create_client`` 的结果。"""
    from backend.core import model_router as mr

    monkeypatch.setattr(mr.settings.config.vector, "embedding_dimension", dimension, raising=False)
    monkeypatch.setattr(
        mr.settings.config.models,
        "get_model_config",
        lambda model_type: _model_config(provider),
    )
    router = object.__new__(mr.ModelRouter)
    return router._create_client("main")


@pytest.mark.parametrize("provider", ["vllm", "ollama"])
def test_create_client_injects_configured_dimension(monkeypatch, provider):
    """配置为 1024 → 客户端 dimension 为 1024（不再被构造函数默认 768 静默覆盖）。"""
    client = _router_with(monkeypatch, 1024, provider)

    assert client is not None
    assert client.dimension == 1024, "客户端维度必须来自配置（否则真实写入会维度不匹配）"


def test_create_client_falls_back_to_768_when_config_missing(monkeypatch):
    """配置缺失（None）→ 回退 768 兜底（其它环境兼容）。"""
    client = _router_with(monkeypatch, None)

    assert client is not None
    assert client.dimension == 768


def test_create_client_unknown_provider_returns_none(monkeypatch):
    """未知 provider → 返回 None（既有行为不变）。"""
    client = _router_with(monkeypatch, 1024, "unknown-provider")

    assert client is None