"""LLM client unit tests."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx

from backend.core.llm.client import OllamaClient, LLMResponse


class TestOllamaClient:
    """Test Ollama client functionality."""

    @pytest.fixture
    def client(self):
        """Create an Ollama client for testing."""
        return OllamaClient(
            model="test-model",
            api_key="test-key",
            base_url="http://localhost:11434"
        )

    @pytest.mark.asyncio
    async def test_generate(self, client):
        """Test text generation."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value={
                    "response": "Test response",
                    "done": True
                })
            )

            response = await client.generate("Hello")
            assert isinstance(response, LLMResponse)
            assert response.content == "Test response"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, client):
        """Test generation with system prompt."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value={
                    "response": "Response with context",
                    "done": True
                })
            )

            response = await client.generate(
                "Hello",
                system_prompt="You are a helpful assistant"
            )
            assert response.content == "Response with context"

    @pytest.mark.asyncio
    async def test_generate_stream(self, client):
        """Test streaming generation."""
        with patch('httpx.AsyncClient.post') as mock_post:
            # Mock streaming response
            mock_response = Mock()
            mock_response.aiter_lines = Mock(return_value=[
                '{"response": "Hello"}',
                '{"response": " world"}',
                '{"done": true}'
            ])
            mock_post.return_value = mock_response

            chunks = []
            async for chunk in client.generate_stream("Hello"):
                chunks.append(chunk)

            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_generate_error(self, client):
        """Test handling generation errors."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = Mock(
                status_code=500,
                text="Internal Server Error"
            )

            with pytest.raises(Exception):
                await client.generate("Hello")

    @pytest.mark.asyncio
    async def test_get_embedding(self, client):
        """Test getting embeddings."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value={
                    "embedding": [0.1, 0.2, 0.3, 0.4, 0.5]
                })
            )

            embedding = await client.get_embedding("Test text")
            assert isinstance(embedding, list)
            assert len(embedding) == 5

    @pytest.mark.asyncio
    async def test_get_embedding_empty_text(self, client):
        """Test embedding empty text."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value={
                    "embedding": []
                })
            )

            embedding = await client.get_embedding("")
            assert isinstance(embedding, list)

    @pytest.mark.asyncio
    async def test_check_health(self, client):
        """Test health check."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=Mock(return_value={
                    "models": [{"name": "test-model"}]
                })
            )

            is_healthy = await client.check_health()
            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_check_health_failure(self, client):
        """Test health check failure."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value = Mock(
                status_code=500,
                text="Error"
            )

            is_healthy = await client.check_health()
            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_chat_with_history(self, client):
        """Test chat with message history."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value={
                    "message": {"content": "Response"},
                    "done": True
                })
            )

            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
                {"role": "user", "content": "How are you?"}
            ]

            response = await client.chat(messages)
            assert response.content == "Response"

    def test_model_configuration(self, client):
        """Test model configuration."""
        assert client.model == "test-model"
        assert client.api_key == "test-key"
        assert client.base_url == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_timeout_handling(self, client):
        """Test timeout handling."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(httpx.TimeoutException):
                await client.generate("Hello")

    @pytest.mark.asyncio
    async def test_connection_error(self, client):
        """Test connection error handling."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(httpx.ConnectError):
                await client.generate("Hello")
