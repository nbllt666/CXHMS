"""Memory manager unit tests."""
import pytest
import sqlite3
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from backend.core.memory.manager import MemoryManager


class TestMemoryManager:
    """Test memory manager functionality."""

    @pytest.fixture
    def memory_manager(self, tmp_path):
        """Create a memory manager with temporary database."""
        db_path = tmp_path / "test_memories.db"
        manager = MemoryManager(db_path=str(db_path))
        yield manager

    def test_initialization(self, memory_manager):
        """Test memory manager initialization."""
        assert memory_manager.db_path is not None
        assert memory_manager.conn is not None

    def test_add_memory(self, memory_manager):
        """Test adding a memory."""
        memory = memory_manager.add_memory(
            content="Test memory",
            memory_type="long_term",
            importance=3
        )
        assert memory is not None
        assert memory["content"] == "Test memory"
        assert memory["memory_type"] == "long_term"
        assert memory["importance"] == 3

    def test_get_memory(self, memory_manager):
        """Test getting a memory by ID."""
        # Add a memory first
        added = memory_manager.add_memory(
            content="Test memory",
            memory_type="long_term"
        )

        # Retrieve it
        memory = memory_manager.get_memory(added["id"])
        assert memory is not None
        assert memory["content"] == "Test memory"

    def test_get_memory_not_found(self, memory_manager):
        """Test getting a non-existent memory."""
        memory = memory_manager.get_memory("non-existent-id")
        assert memory is None

    def test_update_memory(self, memory_manager):
        """Test updating a memory."""
        # Add a memory
        added = memory_manager.add_memory(
            content="Original content",
            memory_type="long_term"
        )

        # Update it
        updated = memory_manager.update_memory(
            added["id"],
            content="Updated content"
        )
        assert updated is not None
        assert updated["content"] == "Updated content"

    def test_delete_memory(self, memory_manager):
        """Test deleting a memory."""
        # Add a memory
        added = memory_manager.add_memory(
            content="To be deleted",
            memory_type="short_term"
        )

        # Delete it
        result = memory_manager.delete_memory(added["id"])
        assert result is True

        # Verify it's gone
        memory = memory_manager.get_memory(added["id"])
        assert memory is None

    def test_get_all_memories(self, memory_manager):
        """Test getting all memories."""
        # Add multiple memories
        memory_manager.add_memory(content="Memory 1", memory_type="long_term")
        memory_manager.add_memory(content="Memory 2", memory_type="short_term")
        memory_manager.add_memory(content="Memory 3", memory_type="permanent")

        result = memory_manager.get_all_memories()
        assert result["total"] == 3
        assert len(result["memories"]) == 3

    def test_get_memories_by_type(self, memory_manager):
        """Test getting memories filtered by type."""
        # Add memories of different types
        memory_manager.add_memory(content="Long term", memory_type="long_term")
        memory_manager.add_memory(content="Short term", memory_type="short_term")
        memory_manager.add_memory(content="Another long", memory_type="long_term")

        long_term = memory_manager.get_memories_by_type("long_term")
        assert len(long_term) == 2

    def test_search_memories(self, memory_manager):
        """Test searching memories."""
        # Add memories
        memory_manager.add_memory(content="Python programming")
        memory_manager.add_memory(content="JavaScript coding")
        memory_manager.add_memory(content="Machine learning")

        # Search
        results = memory_manager.search_memories("python")
        assert len(results) >= 1

    def test_memory_importance_levels(self, memory_manager):
        """Test different importance levels."""
        for importance in range(1, 6):
            memory = memory_manager.add_memory(
                content=f"Importance {importance}",
                importance=importance
            )
            assert memory["importance"] == importance

    def test_memory_timestamps(self, memory_manager):
        """Test memory timestamps."""
        memory = memory_manager.add_memory(content="Test")

        assert "created_at" in memory
        assert "updated_at" in memory

        # Parse timestamps
        created = datetime.fromisoformat(memory["created_at"])
        assert isinstance(created, datetime)

    def test_get_memory_stats(self, memory_manager):
        """Test getting memory statistics."""
        # Add memories of different types
        memory_manager.add_memory(content="Long", memory_type="long_term")
        memory_manager.add_memory(content="Short", memory_type="short_term")
        memory_manager.add_memory(content="Permanent", memory_type="permanent")

        stats = memory_manager.get_memory_stats()
        assert stats["total"] == 3
        assert stats["long_term"] == 1
        assert stats["short_term"] == 1
        assert stats["permanent"] == 1

    def test_cleanup_expired_memories(self, memory_manager):
        """Test cleaning up expired memories."""
        # Add a short-term memory
        memory_manager.add_memory(
            content="Short term",
            memory_type="short_term"
        )

        # Clean up (should not remove anything in this test)
        count = memory_manager.cleanup_expired_memories()
        assert isinstance(count, int)

    def test_create_session(self, memory_manager):
        """Test creating a chat session."""
        session = memory_manager.create_session(
            title="Test Session",
            agent_id="default"
        )
        assert session is not None
        assert session["title"] == "Test Session"
        assert "id" in session

    def test_get_session(self, memory_manager):
        """Test getting a session."""
        created = memory_manager.create_session(title="Test")
        session = memory_manager.get_session(created["id"])
        assert session is not None
        assert session["title"] == "Test"

    def test_add_session_message(self, memory_manager):
        """Test adding a message to a session."""
        session = memory_manager.create_session(title="Test")

        message = memory_manager.add_session_message(
            session_id=session["id"],
            role="user",
            content="Hello"
        )
        assert message is not None
        assert message["role"] == "user"
        assert message["content"] == "Hello"

    def test_get_session_messages(self, memory_manager):
        """Test getting session messages."""
        session = memory_manager.create_session(title="Test")

        # Add messages
        memory_manager.add_session_message(session["id"], "user", "Hello")
        memory_manager.add_session_message(session["id"], "assistant", "Hi!")

        messages = memory_manager.get_session_messages(session["id"])
        assert len(messages) == 2

    def test_create_agent(self, memory_manager):
        """Test creating an agent."""
        agent = memory_manager.create_agent(
            name="Test Agent",
            description="A test agent",
            model="test-model"
        )
        assert agent is not None
        assert agent["name"] == "Test Agent"
        assert agent["is_default"] is False

    def test_get_agent(self, memory_manager):
        """Test getting an agent."""
        created = memory_manager.create_agent(name="Test")
        agent = memory_manager.get_agent(created["id"])
        assert agent is not None
        assert agent["name"] == "Test"

    def test_update_agent(self, memory_manager):
        """Test updating an agent."""
        created = memory_manager.create_agent(name="Original")
        updated = memory_manager.update_agent(
            created["id"],
            name="Updated"
        )
        assert updated["name"] == "Updated"

    def test_delete_agent(self, memory_manager):
        """Test deleting an agent."""
        created = memory_manager.create_agent(name="To Delete")
        result = memory_manager.delete_agent(created["id"])
        assert result is True

        # Verify deletion
        agent = memory_manager.get_agent(created["id"])
        assert agent is None

    def test_set_default_agent(self, memory_manager):
        """Test setting default agent."""
        agent = memory_manager.create_agent(name="Default")
        result = memory_manager.set_default_agent(agent["id"])
        assert result is True

        # Verify
        updated = memory_manager.get_agent(agent["id"])
        assert updated["is_default"] is True
