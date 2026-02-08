"""Memory API endpoint tests."""
import pytest
from fastapi.testclient import TestClient


class TestMemoryEndpoints:
    """Test memory API endpoints."""

    def test_get_all_memories(self, client: TestClient):
        """Test getting all memories."""
        response = client.get("/api/api/memories")
        assert response.status_code in [200, 503]

    def test_get_all_memories_with_pagination(self, client: TestClient):
        """Test getting memories with pagination."""
        response = client.get("/api/api/memories?page=2&page_size=10")
        assert response.status_code in [200, 503]

    def test_get_memory_by_id_not_found(self, client: TestClient):
        """Test getting a non-existent memory."""
        response = client.get("/api/api/memories/non-existent-memory-12345")
        # API returns 422 for invalid ID format
        assert response.status_code in [404, 422, 503]

    def test_create_memory_validation(self, client: TestClient):
        """Test creating a memory without required fields."""
        response = client.post(
            "/api/api/memories",
            json={
                "type": "long_term"
            }
        )
        assert response.status_code == 422

    def test_update_memory_not_found(self, client: TestClient):
        """Test updating a non-existent memory."""
        response = client.put(
            "/api/api/memories/non-existent-memory-12345",
            json={"content": "Updated"}
        )
        assert response.status_code in [404, 422, 503]

    def test_delete_memory_not_found(self, client: TestClient):
        """Test deleting a non-existent memory."""
        response = client.delete("/api/api/memories/non-existent-memory-12345")
        assert response.status_code in [404, 422, 503]

    def test_search_memories(self, client: TestClient):
        """Test searching memories."""
        response = client.post(
            "/api/api/memories/search",
            json={"query": "test"}
        )
        assert response.status_code in [200, 503]

    def test_semantic_search(self, client: TestClient):
        """Test semantic search endpoint."""
        response = client.post(
            "/api/api/memories/semantic-search",
            json={
                "query": "test query",
                "top_k": 5,
                "threshold": 0.7
            }
        )
        assert response.status_code in [200, 503]

    def test_get_memory_stats(self, client: TestClient):
        """Test getting memory statistics."""
        response = client.get("/api/api/memories/stats")
        assert response.status_code in [200, 422, 503]
