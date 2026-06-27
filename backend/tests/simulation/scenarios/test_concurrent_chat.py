"""SubTask 8.6 - 多会话并发不串扰场景。

覆盖死区：多 agent_id 并发会话隔离、后端 context_manager 按 agent_id
派生 session_id（``f"agent-{agent_id}"``）的隔离机制、串行场景的兜底验证。
验证不同 agent 的上下文互不污染，名字回溯各取其主。
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed


def _create_test_agent(sim_actor, label: str) -> str:
    """创建一个测试用 Agent，返回其 id。

    使用 uuid 后缀避免跨测试运行的名称冲突（``create_agent`` 检查 name 唯一）。
    Agent 配置对齐 default agent（``model=main`` / ``use_memory=True`` /
    ``use_tools=True``），确保 chat 路由能正常工作。
    """
    unique_name = f"concurrent-test-{label}-{uuid.uuid4().hex[:6]}"
    payload = {
        "name": unique_name,
        "description": f"并发隔离测试 agent: {label}",
        "system_prompt": "你是测试助手。",
        "model": "main",
        "temperature": 0.7,
        "max_tokens": 1024,
        "use_memory": True,
        "use_tools": True,
        "memory_scene": "chat",
        "decay_model": "exponential",
        "vision_enabled": False,
    }
    resp = sim_actor.create_agent(payload)
    return resp["agent"]["id"]


def _delete_test_agent(sim_actor, agent_id: str) -> None:
    """删除测试用 Agent（兜底清理，失败时静默以不影响断言）。"""
    try:
        sim_actor.client.delete(f"/api/agents/{agent_id}")
    except Exception:
        pass


def test_multiple_agent_sessions_isolated(sim_actor):
    """4 个 agent_id 通过线程池并发发送"我叫X"，再串行问"我叫什么"，
    断言每个 agent 看到自己的名字（多会话不串扰）。

    TestClient 在多线程下可能不安全，用 ``threading.Lock`` 保护 client.post，
    使并发的 HTTP 调用串行执行，但仍验证"多 agent_id 并发提交 + 隔离"路径。
    不同 agent_id 经 chat 路由派生为不同 session_id（``f"agent-{agent_id}"``），
    天然隔离后端 context_manager 历史。
    """
    labels_and_names = [
        ("a", "张三"),
        ("b", "李四"),
        ("c", "王五"),
        ("d", "赵六"),
    ]

    agent_ids = []
    try:
        # 阶段 0：为每个 label 创建 agent（仅 default/memory-agent 预置，
        # 自定义 agent_id 需先注册，否则 chat 路由返回 404）
        for label, _ in labels_and_names:
            agent_ids.append(_create_test_agent(sim_actor, label))

        lock = threading.Lock()

        def send(agent_id: str, message: str):
            """线程安全包装：在 Lock 保护下调用同步 TestClient。"""
            with lock:
                return sim_actor.send_message(message, agent_id=agent_id)

        # 阶段 1：线程池并发发送"我叫X"
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for (label, name), agent_id in zip(labels_and_names, agent_ids):
                fut = executor.submit(send, agent_id, f"我叫{name}")
                futures[fut] = (label, name)
            for fut in as_completed(futures):
                label, name = futures[fut]
                resp = fut.result()
                assert resp["status"] == "success", (
                    f"agent {label} 并发发送失败: {resp!r}"
                )

        # 阶段 2：串行问"我叫什么"，断言每个 agent 看到自己的名字
        for (label, expected_name), agent_id in zip(labels_and_names, agent_ids):
            resp = sim_actor.send_message("我叫什么", agent_id=agent_id)
            assert resp["status"] == "success", (
                f"agent {label} 询问名字失败: {resp!r}"
            )
            assert expected_name in resp["response"], (
                f"agent {label} 应记住 {expected_name}，"
                f"实际: {resp['response']!r}"
            )
    finally:
        # 清理：删除所有创建的 agent，避免污染 agents.json
        for agent_id in agent_ids:
            _delete_test_agent(sim_actor, agent_id)


def test_sequential_sessions_no_crosstalk(sim_actor):
    """串行场景兜底：4 个 agent_id 顺序发送"我叫X"，再顺序问"我叫什么"，
    断言上下文按 agent_id 隔离，不串扰。

    此测试不依赖线程池，更稳定，用于验证"多会话不串扰"的核心断言
    在无并发干扰下成立。
    """
    labels_and_names = [
        ("seq-a", "张三"),
        ("seq-b", "李四"),
        ("seq-c", "王五"),
        ("seq-d", "赵六"),
    ]

    agent_ids = []
    try:
        for label, _ in labels_and_names:
            agent_ids.append(_create_test_agent(sim_actor, label))

        # 串行发送"我叫X"
        for (label, name), agent_id in zip(labels_and_names, agent_ids):
            resp = sim_actor.send_message(f"我叫{name}", agent_id=agent_id)
            assert resp["status"] == "success", (
                f"agent {label} 发送失败: {resp!r}"
            )

        # 串行问"我叫什么"
        for (label, expected_name), agent_id in zip(labels_and_names, agent_ids):
            resp = sim_actor.send_message("我叫什么", agent_id=agent_id)
            assert resp["status"] == "success", (
                f"agent {label} 询问失败: {resp!r}"
            )
            assert expected_name in resp["response"], (
                f"agent {label} 应记住 {expected_name}，"
                f"实际: {resp['response']!r}"
            )
    finally:
        for agent_id in agent_ids:
            _delete_test_agent(sim_actor, agent_id)
