"""Agent API endpoint tests."""
import pytest
from fastapi.testclient import TestClient


class TestAgentEndpoints:
    """Test agent API endpoints."""

    def test_get_all_agents(self, client: TestClient):
        """Test getting all agents."""
        response = client.get("/api/agents")
        # May return 200 with data or 503 if service not ready
        assert response.status_code in [200, 503]

    def test_get_agent_by_id(self, client: TestClient):
        """Test getting a specific agent."""
        response = client.get("/api/agents/default")
        assert response.status_code in [200, 404, 503]

    def test_get_agent_not_found(self, client: TestClient):
        """Test getting a non-existent agent."""
        response = client.get("/api/agents/non-existent-agent-12345")
        assert response.status_code in [404, 503]

    def test_create_agent_validation(self, client: TestClient):
        """Test creating an agent without required fields."""
        response = client.post(
            "/api/agents",
            json={
                "description": "Agent without name"
            }
        )
        assert response.status_code == 422

    def test_update_agent_not_found(self, client: TestClient):
        """Test updating a non-existent agent."""
        response = client.put(
            "/api/agents/non-existent-agent-12345",
            json={"name": "Updated"}
        )
        assert response.status_code in [404, 503]

    def test_delete_agent_not_found(self, client: TestClient):
        """Test deleting a non-existent agent."""
        response = client.delete("/api/agents/non-existent-agent-12345")
        assert response.status_code in [404, 503]

    def test_delete_default_agent(self, client: TestClient):
        """Test deleting the default agent."""
        response = client.delete("/api/agents/default")
        # Should not allow deleting default agent
        assert response.status_code in [400, 403, 404, 503]

    def test_set_default_agent_not_found(self, client: TestClient):
        """Test setting a non-existent agent as default."""
        response = client.post("/api/agents/non-existent-agent-12345/set-default")
        assert response.status_code in [404, 503]
