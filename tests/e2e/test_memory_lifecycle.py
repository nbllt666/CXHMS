"""G7 E2E: 记忆生命周期端到端测试。

覆盖死区：
    - 写入 long_term 记忆（POST /api/memories）
    - 按内容关键词搜索（POST /api/memories/search）
    - 按标签搜索、按时间范围搜索
    - 读取单条记忆含 decay_score 字段（GET /api/memories/{id}）
    - 删除记忆后 GET 返回 404（DELETE /api/memories/{id}）

断言风格：语义断言（status=success、记忆非空、字段存在、id 匹配），
不依赖精确召回排序。所有记忆用唯一 marker 标识，agent_id 用 e2e-test-
前缀，测试结束后 try/finally 硬删除清理。
"""

import time
import uuid

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _e2e_agent_id() -> str:
    """Generate a unique e2e-test agent_id for memory isolation."""
    return f"e2e-test-mem-{uuid.uuid4().hex[:8]}"


def _write_memory(
    real_app, agent_id: str, content: str, tags=None, memory_type: str = "long_term"
) -> int:
    """Write a memory via POST /api/memories, return memory_id."""
    body = {
        "content": content,
        "type": memory_type,
        "importance": 3,
        "tags": tags or [],
        "metadata": {},
        "permanent": False,
        "workspace_id": "default",
        "agent_id": agent_id,
    }
    resp = real_app.post("/api/memories", json=body)
    assert resp.status_code == 200, f"写入记忆失败: {resp.status_code} {resp.text}"
    return resp.json()["memory_id"]


def _search_memories(real_app, agent_id: str, **kwargs):
    """Search memories via POST /api/memories/search, return response dict."""
    body = {"agent_id": agent_id, "workspace_id": "default", "limit": 20}
    body.update(kwargs)
    resp = real_app.post("/api/memories/search", json=body)
    assert resp.status_code == 200, f"搜索记忆失败: {resp.status_code} {resp.text}"
    return resp.json()


def _delete_memory(real_app, mem_id: int, agent_id: str) -> None:
    """Hard-delete a memory (best-effort, no assert)."""
    try:
        real_app.delete(
            f"/api/memories/{mem_id}",
            params={"soft_delete": "false", "agent_id": agent_id},
        )
    except Exception:
        pass


def test_write_and_search_memory(real_app, vllm_available):
    """写入 long_term 记忆后，按内容关键词搜索应能召回该记忆。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _e2e_agent_id()
    marker = f"ZephyrMem-{uuid.uuid4().hex[:6]}"
    mem_id = None
    try:
        mem_id = _write_memory(
            real_app, agent_id, f"这是 E2E 测试记忆，标记 {marker}，用于验证写入与搜索闭环。"
        )
        assert mem_id > 0, f"memory_id 应为正整数，实际: {mem_id}"

        data = _search_memories(real_app, agent_id, query=marker, limit=20)
        assert data["status"] == "success"
        memories = data.get("memories") or []
        assert memories, f"搜索应能召回刚写入的记忆（marker={marker}），实际: {memories!r}"
        assert any(m.get("id") == mem_id for m in memories), (
            f"召回结果应包含刚写入的 memory_id={mem_id}，实际: {[m.get('id') for m in memories]}"
        )
    finally:
        if mem_id:
            _delete_memory(real_app, mem_id, agent_id)


def test_tag_search(real_app, vllm_available):
    """按标签搜索记忆应能召回带对应标签的记忆。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _e2e_agent_id()
    tag = f"e2e-tag-{uuid.uuid4().hex[:6]}"
    mem_id = None
    try:
        mem_id = _write_memory(
            real_app,
            agent_id,
            "E2E 标签搜索测试记忆，带唯一标签。",
            tags=[tag],
        )
        assert mem_id > 0

        data = _search_memories(real_app, agent_id, tags=[tag], limit=20)
        assert data["status"] == "success"
        memories = data.get("memories") or []
        assert memories, f"按标签 {tag} 搜索应召回记忆"
        assert any(m.get("id") == mem_id for m in memories), (
            f"标签搜索结果应包含刚写入的 memory_id={mem_id}"
        )
    finally:
        if mem_id:
            _delete_memory(real_app, mem_id, agent_id)


def test_time_range_search(real_app, vllm_available):
    """按时间范围搜索（time_range=1d）应能召回最近写入的记忆。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _e2e_agent_id()
    marker = f"TimeRange-{uuid.uuid4().hex[:6]}"
    mem_id = None
    try:
        # Record timestamp before write to assert the memory falls in range
        _before = int(time.time())
        mem_id = _write_memory(
            real_app, agent_id, f"E2E 时间范围测试记忆 {marker}。"
        )
        assert mem_id > 0

        data = _search_memories(
            real_app, agent_id, query=marker, time_range="1d", limit=20
        )
        assert data["status"] == "success"
        memories = data.get("memories") or []
        assert memories, "时间范围搜索应召回刚写入的记忆"
        assert any(m.get("id") == mem_id for m in memories), (
            f"时间范围搜索结果应包含刚写入的 memory_id={mem_id}"
        )
    finally:
        if mem_id:
            _delete_memory(real_app, mem_id, agent_id)


def test_get_memory_has_decay_score(real_app, vllm_available):
    """GET /api/memories/{id} 返回的记忆 dict 应包含 decay_score 字段。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _e2e_agent_id()
    mem_id = None
    try:
        mem_id = _write_memory(real_app, agent_id, "E2E 衰减字段测试记忆。")
        assert mem_id > 0

        resp = real_app.get(f"/api/memories/{mem_id}", params={"agent_id": agent_id})
        assert resp.status_code == 200, f"获取记忆失败: {resp.status_code} {resp.text}"
        body = resp.json()
        assert body["status"] == "success"
        memory = body["memory"]
        assert memory is not None, "记忆不应为 None"
        assert "decay_score" in memory, (
            f"记忆应包含 decay_score 字段，实际 keys: {list(memory.keys())}"
        )
        # decay_score should be a numeric value (float)
        assert isinstance(memory["decay_score"], (int, float)), (
            f"decay_score 应为数值，实际: {memory['decay_score']!r}"
        )
    finally:
        if mem_id:
            _delete_memory(real_app, mem_id, agent_id)


def test_delete_memory_returns_404(real_app, vllm_available):
    """硬删除记忆后，GET /api/memories/{id} 应返回 404。"""
    if not vllm_available:
        pytest.skip("vLLM 服务不可用，跳过 E2E 测试")

    agent_id = _e2e_agent_id()
    mem_id = None
    try:
        mem_id = _write_memory(real_app, agent_id, "E2E 删除测试记忆，即将被删除。")
        assert mem_id > 0

        # Verify it exists before delete
        before = real_app.get(f"/api/memories/{mem_id}", params={"agent_id": agent_id})
        assert before.status_code == 200, f"删除前 GET 应返回 200，实际: {before.status_code}"

        # Hard delete
        del_resp = real_app.delete(
            f"/api/memories/{mem_id}",
            params={"soft_delete": "false", "agent_id": agent_id},
        )
        assert del_resp.status_code == 200, (
            f"删除记忆失败: {del_resp.status_code} {del_resp.text}"
        )
        assert del_resp.json()["status"] == "success"

        # Verify it's gone (GET returns 404 after hard delete)
        after = real_app.get(f"/api/memories/{mem_id}", params={"agent_id": agent_id})
        assert after.status_code == 404, (
            f"删除后 GET 应返回 404，实际: {after.status_code}"
        )
        # Mark deleted so finally cleanup is a no-op
        mem_id = None
    finally:
        if mem_id:
            _delete_memory(real_app, mem_id, agent_id)
