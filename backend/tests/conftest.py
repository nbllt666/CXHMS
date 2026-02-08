import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from fastapi.testclient import TestClient

from backend.api.app import app
from config.settings import settings


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="function")
def mock_settings():
    """Provide test settings."""
    return {
        "llm": {
            "main": {"model": "test-model", "api_key": "test-key"},
            "embedding": {"model": "test-embedding", "api_key": "test-key"}
        },
        "memory": {
            "db_path": ":memory:",
            "vector_store_type": "memory"
        }
    }
