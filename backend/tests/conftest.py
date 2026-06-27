import asyncio
import atexit
import os
import shutil
from typing import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from backend.api.app import app
from config.settings import settings

AGENTS_CONFIG_PATH = "data/agents.json"
AGENTS_BACKUP_PATH = "data/agents.json.backup"
_backup_created = False


def _restore_agents():
    """Restore agents.json from backup if exists."""
    global _backup_created
    if _backup_created and os.path.exists(AGENTS_BACKUP_PATH):
        try:
            shutil.copy2(AGENTS_BACKUP_PATH, AGENTS_CONFIG_PATH)
            os.remove(AGENTS_BACKUP_PATH)
        except Exception:
            pass
        _backup_created = False


def _cleanup_alarm_manager():
    """Cleanup alarm manager to prevent logging errors after tests."""
    try:
        from backend.core.alarm.manager import reset_alarm_manager

        reset_alarm_manager()
    except Exception:
        pass


atexit.register(_restore_agents)
atexit.register(_cleanup_alarm_manager)


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI app."""
    global _backup_created

    os.makedirs("data", exist_ok=True)

    if os.path.exists(AGENTS_CONFIG_PATH):
        shutil.copy2(AGENTS_CONFIG_PATH, AGENTS_BACKUP_PATH)
        _backup_created = True

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        _restore_agents()


@pytest.fixture(scope="session")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="function")
def mock_settings():
    """Provide test settings."""
    return {
        "llm": {
            "main": {"model": "test-model", "api_key": "test-key"},
            "embedding": {"model": "test-embedding", "api_key": "test-key"},
        },
        "memory": {"db_path": ":memory:", "vector_store_type": "memory"},
    }


@pytest.fixture(scope="function")
def sim_app(monkeypatch):
    """模拟模式 TestClient：用假实现驱动真实 FastAPI app（无外部依赖）。

    通过 ``CXHMS_SIMULATION`` 环境变量触发 ``lifespan`` 的模拟分支，
    装配 FakeLLMClient/FakeModelRouter/InMemoryVectorStore 等假实现。
    每个 test 独立隔离：重置 MemoryManager 单例与图注册表，避免残留。
    """
    from backend.api.app import app
    from backend.core.memory.manager import MemoryManager

    import backend.dependencies as _deps

    monkeypatch.setenv("CXHMS_SIMULATION", "1")

    # 重置单例与图注册表，防止上一次启动残留
    MemoryManager._instance = None
    _deps._graph_databases.clear()
    _deps._graph_stores.clear()

    with TestClient(app) as test_client:
        yield test_client

    # teardown：重置单例与图注册表，清空 data/context 目录
    MemoryManager._instance = None
    _deps._graph_databases.clear()
    _deps._graph_stores.clear()
    try:
        ctx_dir = "data/context"
        if os.path.isdir(ctx_dir):
            shutil.rmtree(ctx_dir, ignore_errors=True)
        os.makedirs(ctx_dir, exist_ok=True)
    except Exception:
        pass


@pytest.fixture(scope="function")
def sim_client(sim_app):
    """模拟模式 TestClient（依赖 sim_app）。"""
    return sim_app


@pytest.fixture(scope="function")
def sim_actor(sim_client):
    """无头用户演员：以业务语义驱动真实后端 API。

    依赖 ``sim_client``（每个测试函数独立），返回
    ``SimUserActor(sim_client)``，让测试用 ``actor.send_streaming_message(...)``
    等方法编写断言，避免在测试里裸构造 HTTP 请求。
    """
    from backend.tests.simulation.actor import SimUserActor

    return SimUserActor(sim_client)

