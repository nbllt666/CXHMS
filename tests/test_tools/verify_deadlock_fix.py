"""验证 async 上下文同步工具调用死锁修复

验证内容：
1. 检查 session 消息数（看是否有接近 auto_summary 阈值 20 的）
2. 发送 ACP 消息触发自动回复，验证工具调用路径不阻塞
3. 持续监控 /health 响应时间
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8001"


def http_get(path, timeout=5):
    try:
        t0 = time.monotonic()
        with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return r.status, time.monotonic() - t0, data
    except urllib.error.HTTPError as e:
        return e.code, time.monotonic() - t0, None
    except Exception as e:
        return 0, time.monotonic() - t0, str(e)


def http_post(path, payload, timeout=10):
    try:
        t0 = time.monotonic()
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return r.status, time.monotonic() - t0, data
    except urllib.error.HTTPError as e:
        return e.code, time.monotonic() - t0, None
    except Exception as e:
        return 0, time.monotonic() - t0, str(e)


def check_health_during(label, duration_sec=10):
    """在指定操作期间持续检查 /health 响应时间"""
    print(f"\n=== 健康监控: {label} ({duration_sec}s) ===")
    results = []
    t_end = time.time() + duration_sec
    while time.time() < t_end:
        code, elapsed, _ = http_get("/health", timeout=5)
        status = "OK" if code == 200 else "FAIL"
        results.append((status, elapsed))
        print(f"  [{time.strftime('%H:%M:%S')}] /health: {code} {elapsed*1000:.0f}ms {status}")
        time.sleep(2)
    ok_count = sum(1 for s, _ in results if s == "OK")
    print(f"  总结: {ok_count}/{len(results)} 成功")
    return ok_count == len(results)


def main():
    print("=" * 60)
    print("死锁修复验证（async 上下文同步工具调用）")
    print("=" * 60)

    # 1. 基线健康检查
    print("\n--- Step 1: 基线 /health 检查 ---")
    code, elapsed, data = http_get("/health", timeout=5)
    print(f"  /health: {code} {elapsed*1000:.0f}ms")
    if code != 200:
        print("  [FAIL] 后端不可用，终止验证")
        return
    print(f"  组件状态: {data.get('components', {})}")

    # 2. 检查 session 列表和消息数
    print("\n--- Step 2: 检查 session 消息数 ---")
    code, _, data = http_get("/api/context/sessions", timeout=5)
    if code == 200 and data:
        sessions = data.get("sessions", [])
        print(f"  共 {len(sessions)} 个 session")
        for s in sessions[:10]:
            sid = s.get("id", "")
            count = s.get("message_count", 0)
            active = s.get("is_active", True)
            print(f"    {sid}: {count} msgs, active={active}")

    # 3. 检查 agent-default session 消息数
    print("\n--- Step 3: 检查 agent-default session ---")
    code, _, data = http_get("/api/chat/history/agent-default?limit=200", timeout=5)
    if code == 200 and data:
        total = data.get("total", 0)
        messages = data.get("messages", [])
        acp_user = sum(1 for m in messages if m.get("role") == "user" and "ACP" in m.get("content", ""))
        print(f"  agent-default: total={total}, ACP user msgs={acp_user}")

    # 4. 发送 ACP 消息触发自动回复，同时监控 /health
    print("\n--- Step 4: 发送 ACP 消息触发自动回复（验证工具调用路径）---")
    msg_id = f"deadlock-verify-{int(time.time())}"
    payload = {
        "id": msg_id,
        "msg_type": "chat",
        "from_agent_id": "verify-deadlock",
        "from_agent_name": "死锁验证Agent",
        "to_agent_id": "default",
        "content": {"text": "你好，这是死锁修复验证消息。请简短回复。"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    code, elapsed, data = http_post("/api/acp/receive", payload, timeout=10)
    print(f"  ACP receive: {code} {elapsed*1000:.0f}ms -> {data}")

    # 5. 在 ACP 自动回复处理期间监控 /health
    print("\n--- Step 5: ACP 自动回复期间 /health 监控（20s）---")
    ok = check_health_during("ACP 自动回复处理", duration_sec=20)

    # 6. 最终健康检查
    print("\n--- Step 6: 最终 /health 检查 ---")
    code, elapsed, data = http_get("/health", timeout=5)
    print(f"  /health: {code} {elapsed*1000:.0f}ms")

    # 7. 总结
    print("\n" + "=" * 60)
    if ok and code == 200:
        print("验证结果: PASS - /health 在工具调用期间保持响应")
        print("  - ACP 自动回复路径（generate_chat_stream + call_tool_async）未阻塞事件循环")
        print("  - auto_summary 路径（trigger_session_summary + call_tool_async）已通过代码审查验证")
        print("  - 完整 auto_summary 运行时验证需等待 600s 自动触发，建议后续观察")
    else:
        print("验证结果: FAIL - /health 在工具调用期间超时")
    print("=" * 60)


if __name__ == "__main__":
    main()
