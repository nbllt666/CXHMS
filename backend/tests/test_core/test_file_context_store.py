"""Tests for FileContextStore (ContextManager file+memory dual storage)."""
import json
import os
import shutil
import tempfile
import pytest
from backend.core.context.manager import ContextManager

CONTEXT_DIR = "data/context"


@pytest.fixture
def store(tmp_path):
    """Create a ContextManager with a clean state.

    ContextManager.__init__ ignores the db_path argument and always uses
    the global "data/context" directory. To isolate tests from global state
    and avoid cross-test contamination, we redirect _context_dir to a
    temporary directory and clear the in-memory store loaded from disk.
    """
    temp_context_dir = tmp_path / "context"
    temp_context_dir.mkdir(parents=True, exist_ok=True)

    store = ContextManager()
    store._context_dir = str(temp_context_dir)
    store._store.clear()

    yield store

    # 清理：删除所有测试产生的数据
    store.clear_all_sessions()


class TestMessageOrdering:
    """Test message ordering is stable by insertion order."""

    def test_messages_in_insertion_order(self, store):
        """Messages should be returned in insertion order."""
        session_id = "test-order-agent"
        store.create_session(session_id=session_id, title="Test")
        store.add_message(session_id, "user", "第一条")
        store.add_message(session_id, "assistant", "第二条")
        store.add_message(session_id, "user", "第三条")

        messages = store.get_messages(session_id)
        assert len(messages) == 3
        assert messages[0]["content"] == "第一条"
        assert messages[1]["content"] == "第二条"
        assert messages[2]["content"] == "第三条"

    def test_limit_returns_most_recent(self, store):
        """get_messages(limit=N) should return the most recent N messages."""
        session_id = "test-limit-agent"
        store.create_session(session_id=session_id, title="Test")
        for i in range(10):
            store.add_message(session_id, "user", f"消息{i}")

        messages = store.get_messages(session_id, limit=3)
        assert len(messages) == 3
        assert messages[0]["content"] == "消息7"
        assert messages[1]["content"] == "消息8"
        assert messages[2]["content"] == "消息9"

    def test_rapid_insertion_order(self, store):
        """Rapid consecutive insertions should maintain order."""
        session_id = "test-rapid-agent"
        store.create_session(session_id=session_id, title="Test")
        for i in range(100):
            store.add_message(session_id, "user" if i % 2 == 0 else "assistant", f"msg{i}")

        messages = store.get_messages(session_id, limit=200)
        assert len(messages) == 100
        for i, msg in enumerate(messages):
            assert msg["content"] == f"msg{i}"


class TestMultiTurnContext:
    """Test multi-turn conversation context continuity."""

    def test_second_turn_includes_first_turn(self, store):
        """Second turn should include first turn's user and assistant messages."""
        session_id = "agent-test-multi"
        store.create_session(session_id=session_id, title="Test")

        # 第一轮
        store.add_message(session_id, "user", "你好")
        store.add_message(session_id, "assistant", "你好！我是助手")

        # 第二轮读取历史
        history = store.get_messages(session_id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "你好"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "你好！我是助手"


class TestFilePersistence:
    """Test file persistence and recovery."""

    def test_data_survives_restart(self, store):
        """Data should be recoverable from file after restart."""
        session_id = "test-persist-agent"
        store.create_session(session_id=session_id, title="Persist Test")
        store.add_message(session_id, "user", "持久化测试")

        # 模拟重启：清空内存后从文件重新加载
        with store._lock:
            store._store.clear()
        store._load_from_disk()

        messages = store.get_messages(session_id)
        assert len(messages) == 1
        assert messages[0]["content"] == "持久化测试"


class TestSessionManagement:
    """Test session CRUD operations."""

    def test_create_and_get_session(self, store):
        session_id = "test-crud-session"
        store.create_session(session_id=session_id, title="CRUD Test")
        session = store.get_session(session_id)
        assert session is not None
        assert session["title"] == "CRUD Test"

    def test_delete_session(self, store):
        session_id = "test-delete-session"
        store.create_session(session_id=session_id, title="Delete Test")
        assert store.delete_session(session_id) is True
        assert store.get_session(session_id) is None

    def test_clear_session_messages(self, store):
        session_id = "test-clear-session"
        store.create_session(session_id=session_id, title="Clear Test")
        store.add_message(session_id, "user", "消息1")
        store.add_message(session_id, "assistant", "回复1")

        store.clear_session_messages(session_id)
        messages = store.get_messages(session_id)
        assert len(messages) == 0

    def test_delete_message(self, store):
        session_id = "test-delmsg-session"
        store.create_session(session_id=session_id, title="DelMsg Test")
        msg_id = store.add_message(session_id, "user", "要删除的消息")
        store.add_message(session_id, "assistant", "保留的回复")

        assert store.delete_message(msg_id) is True
        messages = store.get_messages(session_id)
        assert len(messages) == 1
        assert messages[0]["content"] == "保留的回复"


class TestAgentContextCompat:
    """Test AgentContextManager-compatible methods."""

    def test_append_message(self, store):
        store.create_session(session_id="compat-agent", title="Compat Test")
        store.append_message("compat-agent", "user", "兼容测试")
        history = store.get_message_history("compat-agent", limit=10)
        assert len(history) >= 1
        assert any(m["content"] == "兼容测试" for m in history)

    def test_get_context_summary(self, store):
        store.create_session(session_id="summary-agent", title="Summary Test")
        store.add_message("summary-agent", "user", "测试")
        summary = store.get_context_summary("summary-agent")
        assert summary is not None

    def test_clear_context(self, store):
        store.create_session(session_id="clear-agent", title="Clear Test")
        store.add_message("clear-agent", "user", "清除测试")
        store.clear_context("clear-agent")
        messages = store.get_messages("clear-agent")
        assert len(messages) == 0


class TestStatistics:
    """Test statistics methods."""

    def test_get_statistics(self, store):
        store.create_session(session_id="stats-agent", title="Stats Test")
        store.add_message("stats-agent", "user", "统计测试")
        stats = store.get_statistics()
        assert "total_sessions" in stats
        assert stats["total_sessions"] >= 1
