"""fixtures smoke 测试：验证 tests/conftest.py 的每个 fixture 可获取且类型正确。

覆盖 fixture 清单（对齐 spec tasks.md Task G2）：
    - mock_settings        dict 含 llm/memory/database
    - fake_llm             FakeLLMClient
    - fake_embedding       FakeEmbeddingModel
    - fake_vector_store    InMemoryVectorStore
    - fake_graph_store     InMemoryGraphStore
    - memory_manager       MemoryManager
    - sim_app              FastAPI TestClient（含 app.state.services）
    - client               同 sim_app
    - async_client         httpx.AsyncClient
    - sim_actor            SimUserActor

设计原则：仅验证 fixture 可获取且类型正确，不验证业务逻辑。
sim_app / async_client / sim_actor 会触发完整 lifespan（较慢），合并到少数
测试函数中减少 lifespan 启动次数。
"""

import pytest


# --------------------------------------------------------------------------- #
# 简单 fixtures（不触发 lifespan）
# --------------------------------------------------------------------------- #


def test_mock_settings_fixture(mock_settings):
    """mock_settings 返回 dict 且含 llm/memory/database 三节。"""
    assert isinstance(mock_settings, dict)
    assert "llm" in mock_settings
    assert "memory" in mock_settings
    assert "database" in mock_settings
    assert mock_settings["llm"]["model"]
    assert mock_settings["memory"]["vector_enabled"] is True


def test_fake_llm_fixture(fake_llm):
    """fake_llm fixture 返回 FakeLLMClient 实例。"""
    from fakes.fake_llm import FakeLLMClient

    assert isinstance(fake_llm, FakeLLMClient)


def test_fake_embedding_fixture(fake_embedding):
    """fake_embedding fixture 返回 FakeEmbeddingModel 实例。"""
    from fakes.fake_embedding import FakeEmbeddingModel

    assert isinstance(fake_embedding, FakeEmbeddingModel)


def test_fake_vector_store_fixture(fake_vector_store):
    """fake_vector_store fixture 返回 InMemoryVectorStore 实例。"""
    from fakes.fake_vector_store import InMemoryVectorStore

    assert isinstance(fake_vector_store, InMemoryVectorStore)


def test_fake_graph_store_fixture(fake_graph_store):
    """fake_graph_store fixture 返回 InMemoryGraphStore 实例。"""
    from fakes.fake_graph import InMemoryGraphStore

    assert isinstance(fake_graph_store, InMemoryGraphStore)


def test_memory_manager_fixture(memory_manager):
    """memory_manager fixture 返回 MemoryManager 实例且已注入 fakes。"""
    from backend.core.memory.manager import MemoryManager

    assert isinstance(memory_manager, MemoryManager)
    # fakes 已注入：_vector_store 与 _embedding_model 已设置（私有属性）
    assert memory_manager._vector_store is not None
    assert memory_manager._embedding_model is not None


# --------------------------------------------------------------------------- #
# sim_app / client / sim_actor（触发 lifespan，合并以减少启动次数）
# --------------------------------------------------------------------------- #


def test_sim_app_and_client_fixture(sim_app, client, sim_actor):
    """sim_app / client / sim_actor 三个 fixture 可获取且类型正确。

    合并到一个测试函数避免 lifespan 多次启动。
    """
    from fastapi.testclient import TestClient
    from simulation.actor import SimUserActor

    # sim_app 是 TestClient
    assert isinstance(sim_app, TestClient)
    # client 复用 sim_app
    assert client is sim_app
    # sim_actor 包裹 sim_app
    assert isinstance(sim_actor, SimUserActor)
    assert sim_actor.client is sim_app


def test_sim_app_service_state_injected(sim_app):
    """sim_app 启动后 app.state.services 已装配 ServiceState（D1 注入模式）。"""
    from backend.dependencies import ServiceState

    fastapi_app = sim_app.app
    service_state = getattr(fastapi_app.state, "services", None)
    assert service_state is not None
    assert isinstance(service_state, ServiceState)
    # fakes 已注入到 ServiceState
    assert service_state.memory_manager is not None
    assert service_state.llm_client is not None
    assert service_state.model_router is not None


def test_sim_app_health_endpoint(sim_app):
    """sim_app 的 /health 端点可访问且返回 200（验证完整路由栈可用）。"""
    resp = sim_app.get("/health")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# async_client（async，独立测试）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_async_client_fixture(async_client):
    """async_client fixture 返回 httpx.AsyncClient 且可发请求。"""
    from httpx import AsyncClient

    assert isinstance(async_client, AsyncClient)
    # 用 async_client 发一个请求验证 ASGITransport 路由正常
    resp = await async_client.get("/health")
    assert resp.status_code == 200
