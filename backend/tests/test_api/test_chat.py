"""Chat API endpoint tests."""
import pytest
from fastapi.testclient import TestClient


class TestChatEndpoints:
    """Test chat API endpoints."""

    def test_send_message_validation(self, client: TestClient):
        """Test sending a message without message field returns 422."""
        response = client.post(
            "/api/chat",
            json={
                "agent_id": "default"
            }
        )
        assert response.status_code == 422

    def test_get_chat_history(self, client: TestClient):
        """Test getting chat history for a session."""
        response = client.get("/api/chat/history/non-existent-session")
        # Should return empty or 404 depending on implementation
        assert response.status_code in [200, 404, 503]

    def test_stream_chat_validation(self, client: TestClient):
        """Test streaming chat endpoint validation."""
        response = client.post(
            "/api/chat/stream",
            json={
                "agent_id": "default"
            }
        )
        assert response.status_code == 422
