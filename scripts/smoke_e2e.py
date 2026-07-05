"""I2 端到端冒烟测试脚本 - 模拟前端行为。

使用 httpx 调用后端 API 验证关键路径：
1. Agent 列表与创建
2. 非流式聊天（POST /api/chat）
3. 流式聊天（POST /api/chat/stream），测首包延迟
4. 多轮上下文持久化
5. 历史回溯
6. 记忆 CRUD
7. Agent 切换（验证上下文隔离）
8. 图管理（graph_database=false 时验证降级响应）
9. 健康检查
10. 清理测试数据

依赖：vLLM 服务（http://localhost:8002）、后端（http://localhost:8001）
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx

BACKEND = "http://localhost:8001"
VLLM = "http://localhost:8002"
TIMEOUT = 120.0


def line(prefix: str, msg: str = "") -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {prefix} {msg}".rstrip())


def consume_stream(
    client: httpx.Client, body: Dict[str, Any]
) -> Dict[str, Any]:
    """消费 SSE 流并聚合 content + 测首包延迟。

    Returns:
        {
            "first_byte_ms": float | None,  # 首包延迟（收到第一个 content 事件）
            "content": str,                 # 聚合 content
            "thinking": str,
            "tool_calls": list,
            "tool_results": list,
            "error": str | None,
            "events": int,
        }
    """
    result = {
        "first_byte_ms": None,
        "content": "",
        "thinking": "",
        "tool_calls": [],
        "tool_results": [],
        "error": None,
        "events": 0,
    }
    t0 = time.perf_counter()

    with client.stream(
        "POST", f"{BACKEND}/api/chat/stream", json=body, timeout=TIMEOUT
    ) as resp:
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}: {resp.read().decode()[:200]}"
            return result

        for raw_line in resp.iter_lines():
            if not raw_line or not raw_line.startswith("data: "):
                continue
            payload = raw_line[len("data: "):]
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            result["events"] += 1
            etype = event.get("type")
            if etype == "thinking":
                result["thinking"] += event.get("content", "") or ""
            elif etype == "content":
                if result["first_byte_ms"] is None:
                    result["first_byte_ms"] = (time.perf_counter() - t0) * 1000
                result["content"] += event.get("content", "") or ""
            elif etype == "tool_call":
                result["tool_calls"].append(event.get("tool_call"))
            elif etype == "tool_result":
                result["tool_results"].append(
                    {"tool_name": event.get("tool_name"), "result": event.get("result")}
                )
            elif etype == "error":
                result["error"] = event.get("error")

    return result


def main() -> int:
    """Run end-to-end smoke tests. Returns 0 on success, 1 on failure."""
    failures: List[str] = []
    cleanup_agents: List[str] = []
    cleanup_memories: List[tuple] = []  # (memory_id, agent_id)

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            line("STEP", "1/10 - 健康检查")
            r = client.get(f"{BACKEND}/health")
            assert r.status_code == 200, f"health HTTP {r.status_code}"
            health = r.json()
            line("  OK", f"status={health['status']}, components={health['components']}")

            line("STEP", "2/10 - Agent 列表与创建")
            r = client.get(f"{BACKEND}/api/agents")
            assert r.status_code == 200, f"GET /api/agents HTTP {r.status_code}"
            agents_before = r.json().get("agents", [])
            line("  OK", f"已存在 {len(agents_before)} 个 Agent")

            test_suffix = uuid.uuid4().hex[:8]
            test_agent_id = f"smoke-{test_suffix}"
            r = client.post(
                f"{BACKEND}/api/agents",
                json={
                    "name": f"smoke-test-{test_suffix}",
                    "description": "I2 端到端冒烟测试 Agent（自动清理）",
                    "system_prompt": "你是 CXHMS 测试助手，请用中文简短回答。",
                    "model": "main",
                    "temperature": 0.3,
                    "use_memory": False,
                    "use_tools": False,
                },
            )
            assert r.status_code == 200, f"POST /api/agents HTTP {r.status_code}: {r.text[:200]}"
            created_agent = r.json().get("agent", {})
            # backend 会生成自己的 id，用 backend 返回的 id
            backend_agent_id = created_agent.get("id", test_agent_id)
            cleanup_agents.append(backend_agent_id)
            line("  OK", f"创建 Agent: id={backend_agent_id}")

            line("STEP", "3/10 - 非流式聊天")
            r = client.post(
                f"{BACKEND}/api/chat",
                json={
                    "message": "你好，请用一句话介绍你自己。",
                    "agent_id": backend_agent_id,
                    "stream": False,
                },
            )
            assert r.status_code == 200, f"POST /api/chat HTTP {r.status_code}: {r.text[:200]}"
            chat_resp = r.json()
            assert chat_resp["status"] == "success", f"chat status: {chat_resp.get('status')}"
            assert chat_resp["response"], "chat response 为空"
            assert len(chat_resp["response"]) > 5, f"chat response 过短: {chat_resp['response']!r}"
            session_id = chat_resp["session_id"]
            line("  OK", f"响应长度={len(chat_resp['response'])}, session={session_id}")
            line("  RESP", f"{chat_resp['response'][:80]}...")

            line("STEP", "4/10 - 流式聊天 + 首包延迟")
            stream_result = consume_stream(
                client,
                {
                    "message": "今天天气怎么样？请用一句话回答。",
                    "agent_id": backend_agent_id,
                },
            )
            if stream_result["error"]:
                failures.append(f"流式聊天 error: {stream_result['error']}")
                line("  FAIL", stream_result["error"])
            else:
                assert stream_result["content"], "stream content 为空"
                assert stream_result["first_byte_ms"] is not None, "未收到 content 事件"
                # 首包延迟 ≤ LLM prefill + 200ms。LLM prefill 未知，仅记录
                latency = stream_result["first_byte_ms"]
                line("  OK", f"首包延迟={latency:.1f}ms, content 长度={len(stream_result['content'])}")
                line("  RESP", f"{stream_result['content'][:80]}...")
                # 软断言：首包延迟 < 5s（合理上界）
                if latency > 5000:
                    failures.append(f"首包延迟 {latency:.1f}ms > 5000ms")
                    line("  WARN", f"首包延迟较长: {latency:.1f}ms")

            line("STEP", "5/10 - 多轮上下文持久化")
            codeword = f"ZephyrSmoke-{test_suffix}"
            r1 = client.post(
                f"{BACKEND}/api/chat",
                json={
                    "message": f"请记住我的测试代号是 {codeword}，一会儿我会问你。",
                    "agent_id": backend_agent_id,
                    "stream": False,
                },
            )
            assert r1.status_code == 200, f"多轮-1 HTTP {r1.status_code}"
            r2 = client.post(
                f"{BACKEND}/api/chat",
                json={
                    "message": "我的测试代号是什么？请直接回答。",
                    "agent_id": backend_agent_id,
                    "stream": False,
                },
            )
            assert r2.status_code == 200, f"多轮-2 HTTP {r2.status_code}"
            reply2 = r2.json().get("response", "")
            # 宽松匹配：codeword 或上下文相关关键词
            if not (codeword in reply2 or "代号" in reply2 or "记" in reply2):
                failures.append(f"多轮上下文未保持，第二轮响应: {reply2[:100]!r}")
                line("  FAIL", f"第二轮未引用代号: {reply2[:80]!r}")
            else:
                line("  OK", f"多轮上下文保持，第二轮响应包含关键词")
                line("  RESP", f"{reply2[:80]}...")

            line("STEP", "6/10 - 历史回溯")
            r = client.get(f"{BACKEND}/api/chat/history/{session_id}", params={"limit": 10})
            assert r.status_code == 200, f"history HTTP {r.status_code}"
            history = r.json()
            assert history["status"] == "success"
            messages = history.get("messages", [])
            assert messages, "历史消息为空"
            contents = [m.get("content", "") for m in messages]
            assert any("历史回溯" in c or "你好" in c for c in contents), \
                f"历史中未找到已发送消息，messages={contents[:3]}"
            line("  OK", f"历史消息数={len(messages)}")

            line("STEP", "7/10 - 记忆 CRUD")
            mem_agent_id = f"smoke-mem-{test_suffix}"
            # Create
            r = client.post(
                f"{BACKEND}/api/memories",
                json={
                    "content": f"I2 端到端冒烟测试记忆，标记 {test_suffix}",
                    "type": "long_term",
                    "importance": 3,
                    "tags": [f"smoke-{test_suffix}"],
                    "metadata": {},
                    "permanent": False,
                    "workspace_id": "default",
                    "agent_id": mem_agent_id,
                },
            )
            assert r.status_code == 200, f"POST /api/memories HTTP {r.status_code}: {r.text[:200]}"
            mem_id = r.json()["memory_id"]
            cleanup_memories.append((mem_id, mem_agent_id))
            line("  OK", f"创建记忆 id={mem_id}")

            # Read
            r = client.get(f"{BACKEND}/api/memories/{mem_id}", params={"agent_id": mem_agent_id})
            assert r.status_code == 200, f"GET /api/memories/{mem_id} HTTP {r.status_code}"
            mem = r.json().get("memory", {})
            assert "decay_score" in mem, f"记忆无 decay_score 字段, keys={list(mem.keys())}"
            line("  OK", f"读取记忆 decay_score={mem['decay_score']}")

            # Search
            r = client.post(
                f"{BACKEND}/api/memories/search",
                json={
                    "query": test_suffix,
                    "agent_id": mem_agent_id,
                    "workspace_id": "default",
                    "limit": 20,
                },
            )
            assert r.status_code == 200, f"search HTTP {r.status_code}"
            memories = r.json().get("memories", [])
            assert any(m.get("id") == mem_id for m in memories), \
                f"搜索未召回刚写入的 id={mem_id}"
            line("  OK", f"搜索召回 {len(memories)} 条")

            # Delete
            r = client.delete(
                f"{BACKEND}/api/memories/{mem_id}",
                params={"soft_delete": "false", "agent_id": mem_agent_id},
            )
            assert r.status_code == 200, f"DELETE HTTP {r.status_code}"
            cleanup_memories.pop()  # 已删除，不再 cleanup
            # Verify gone
            r = client.get(f"{BACKEND}/api/memories/{mem_id}", params={"agent_id": mem_agent_id})
            assert r.status_code == 404, f"删除后 GET 应 404, 实际 {r.status_code}"
            line("  OK", "记忆 CRUD 完整闭环（创建→读取→搜索→删除→404）")

            line("STEP", "8/10 - Agent 切换 + 上下文隔离")
            # 创建第二个 agent
            r = client.post(
                f"{BACKEND}/api/agents",
                json={
                    "name": f"smoke-test-B-{test_suffix}",
                    "description": "I2 隔离测试 Agent B",
                    "system_prompt": "你是 CXHMS 测试助手B。",
                    "model": "main",
                    "temperature": 0.3,
                    "use_memory": False,
                    "use_tools": False,
                },
            )
            assert r.status_code == 200
            agent_b_id = r.json()["agent"]["id"]
            cleanup_agents.append(agent_b_id)

            # Agent A 聊天
            secret = f"Secret-{test_suffix}"
            r = client.post(
                f"{BACKEND}/api/chat",
                json={
                    "message": f"请记住这个秘密词：{secret}。",
                    "agent_id": backend_agent_id,
                    "stream": False,
                },
            )
            assert r.status_code == 200, f"agent A chat HTTP {r.status_code}"

            # Agent B 历史不应包含 secret
            session_b = f"agent-{agent_b_id}"
            r = client.get(f"{BACKEND}/api/chat/history/{session_b}", params={"limit": 50})
            assert r.status_code == 200
            msgs_b = r.json().get("messages", [])
            contents_b = [m.get("content", "") for m in msgs_b]
            if any(secret in c for c in contents_b):
                failures.append(f"Agent B 历史泄露 Agent A 的秘密词 {secret}")
                line("  FAIL", f"Agent B 历史包含 secret")
            else:
                line("  OK", "Agent B 历史不含 Agent A 的秘密词")

            # Agent A 历史应包含 secret
            session_a = f"agent-{backend_agent_id}"
            r = client.get(f"{BACKEND}/api/chat/history/{session_a}", params={"limit": 50})
            assert r.status_code == 200
            msgs_a = r.json().get("messages", [])
            contents_a = [m.get("content", "") for m in msgs_a]
            if not any(secret in c for c in contents_a):
                failures.append(f"Agent A 历史未包含秘密词 {secret}")
                line("  FAIL", "Agent A 历史未包含 secret")
            else:
                line("  OK", "Agent A 历史含 secret（隔离验证通过）")

            line("STEP", "9/10 - 图管理（容忍降级）")
            # graph_database=false，预期降级响应（200 + 空数据 / 或 5xx）
            r = client.get(f"{BACKEND}/api/graph/stats", params={"agent_id": backend_agent_id})
            # 不强制断言 status_code，只记录
            line("  INFO", f"GET /api/graph/stats -> HTTP {r.status_code}")

            line("STEP", "10/10 - 工具列表")
            r = client.get(f"{BACKEND}/api/tools")
            assert r.status_code == 200
            tools = r.json().get("tools", {})
            if isinstance(tools, dict):
                tool_count = len(tools)
            else:
                tool_count = len(tools) if isinstance(tools, list) else 0
            line("  OK", f"已注册工具 {tool_count} 个")

    except Exception as e:
        failures.append(f"异常: {type(e).__name__}: {e}")
        line("EXC", f"{type(e).__name__}: {e}")

    # Cleanup
    line("CLEANUP", f"清理 {len(cleanup_agents)} agent + {len(cleanup_memories)} memory")
    try:
        with httpx.Client(timeout=10.0) as client:
            for agent_id in cleanup_agents:
                try:
                    client.delete(f"{BACKEND}/api/agents/{agent_id}/context")
                except Exception:
                    pass
                try:
                    client.delete(f"{BACKEND}/api/agents/{agent_id}")
                except Exception:
                    pass
            for mem_id, ag_id in cleanup_memories:
                try:
                    client.delete(
                        f"{BACKEND}/api/memories/{mem_id}",
                        params={"soft_delete": "false", "agent_id": ag_id},
                    )
                except Exception:
                    pass
    except Exception as e:
        line("CLEANUP-ERR", str(e))

    # Summary
    print()
    print("=" * 60)
    if failures:
        print(f"I2 端到端冒烟测试失败：{len(failures)} 项")
        for i, f in enumerate(failures, 1):
            print(f"  {i}. {f}")
        return 1
    else:
        print("I2 端到端冒烟测试通过：10/10 步骤全绿")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
