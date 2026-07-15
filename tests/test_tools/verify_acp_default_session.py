"""Verify ACP message injection into agent-default session.

Steps:
1. Query agent-default session message count (baseline)
2. POST /api/acp/receive to simulate receiving an ACP message
3. Wait 2s for injection to complete
4. Query agent-default session again — expect +1 system message with source=acp_external
5. Wait up to 30s for auto-reply — expect +1 assistant message with source=acp_auto_reply
"""
import json
import time
import urllib.request


BASE = "http://localhost:8001"


def fetch_messages(session_id: str = "agent-default"):
    url = f"{BASE}/api/chat/history/{session_id}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        if isinstance(data, dict):
            return data.get("messages") or []
        return data
    except Exception as e:
        print(f"[ERR] fetch {session_id}: {e}")
        return None


def send_acp_receive():
    """Simulate receiving an ACP message from an external agent."""
    payload = {
        "id": f"verify-{int(time.time())}",
        "msg_type": "chat",
        "from_agent_id": "verify-test-agent",
        "from_agent_name": "验证测试Agent",
        "to_agent_id": "cxhms_agent_001",
        "to_group_id": None,
        "content": {"text": "验证消息：测试 ACP 消息是否注入到 agent-default session"},
        "metadata": {"from_host": "127.0.0.1", "from_port": 9999},
    }
    req = urllib.request.Request(
        f"{BASE}/api/acp/receive",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[ERR] send ACP receive: {e}")
        return None


def find_acp_messages(msgs):
    """Find ACP-injected messages in the list."""
    acp_external = []
    acp_reply = []
    for m in msgs:
        meta = m.get("metadata") or {}
        src = meta.get("source", "")
        if src == "acp_external":
            acp_external.append(m)
        elif src == "acp_auto_reply":
            acp_reply.append(m)
    return acp_external, acp_reply


if __name__ == "__main__":
    print("=== Step 1: Baseline ===")
    before = fetch_messages("agent-default")
    if before is None:
        print("[FAIL] Cannot fetch agent-default history — backend may be hung")
        exit(1)
    before_ext, before_reply = find_acp_messages(before)
    print(f"  Total messages: {len(before)}")
    print(f"  ACP external (system): {len(before_ext)}")
    print(f"  ACP auto-reply (assistant): {len(before_reply)}")

    print("\n=== Step 2: Send ACP message via /api/acp/receive ===")
    result = send_acp_receive()
    if result is None:
        print("[FAIL] Cannot send ACP receive request")
        exit(1)
    print(f"  Response: {json.dumps(result, ensure_ascii=False)[:120]}")

    print("\n=== Step 3: Wait 2s for injection ===")
    time.sleep(2)

    print("\n=== Step 4: Check agent-default for injected system message ===")
    after_inj = fetch_messages("agent-default")
    if after_inj is None:
        print("[FAIL] Cannot fetch agent-default after injection")
        exit(1)
    after_ext, _ = find_acp_messages(after_inj)
    print(f"  Total messages: {len(after_inj)}")
    print(f"  ACP external (system): {len(after_ext)}")

    if len(after_ext) > len(before_ext):
        print("[OK] ACP system message injected into agent-default!")
        latest = after_ext[-1]
        content = latest.get("content", "")
        print(f"  Latest ACP message: {str(content)[:100]}")
    else:
        print("[FAIL] No new ACP system message found in agent-default")

    print("\n=== Step 5: Poll for auto-reply (up to 30s) ===")
    found_reply = False
    for attempt in range(6):
        time.sleep(5)
        after_reply = fetch_messages("agent-default")
        if after_reply is None:
            print(f"  poll {attempt+1}/6: fetch failed")
            continue
        _, replies = find_acp_messages(after_reply)
        print(f"  poll {attempt+1}/6: ACP replies={len(replies)}")
        if len(replies) > len(before_reply):
            found_reply = True
            latest_reply = replies[-1]
            content = latest_reply.get("content", "")
            print(f"[OK] Auto-reply found in agent-default: {str(content)[:100]}")
            break

    if not found_reply:
        print("[WARN] No auto-reply found in agent-default (LLM may be slow/unavailable)")

    print("\n=== Summary ===")
    final = fetch_messages("agent-default")
    if final is not None:
        final_ext, final_reply = find_acp_messages(final)
        print(f"  agent-default total: {len(final)}")
        print(f"  ACP system messages: {len(final_ext)} (was {len(before_ext)})")
        print(f"  ACP auto-replies: {len(final_reply)} (was {len(before_reply)})")
        if len(final_ext) > len(before_ext):
            print("[VERDICT] FIX VERIFIED: ACP messages now appear in agent-default session")
        else:
            print("[VERDICT] FIX NOT WORKING: ACP messages still missing from agent-default")
