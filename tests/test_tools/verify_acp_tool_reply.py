"""Verify ACP auto-reply uses tool-call pipeline (refactored).

Checks:
1. Baseline message count in agent-default
2. POST /api/acp/receive to inject ACP message
3. Verify injected message has role=user (not system)
4. Wait up to 60s for auto-reply:
   - Check assistant message exists
   - Check metadata.tool_calls for acp_send_message usage
"""
import json
import time
import urllib.request


BASE = "http://localhost:8001"


def fetch_messages(session_id: str = "agent-default"):
    url = f"{BASE}/api/chat/history/{session_id}"
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            data = json.loads(r.read())
        if isinstance(data, dict):
            return data.get("messages") or []
        return data
    except Exception as e:
        print(f"[ERR] fetch {session_id}: {e}")
        return None


def send_acp_receive():
    payload = {
        "id": f"verify-tool-{int(time.time())}",
        "msg_type": "chat",
        "from_agent_id": "verify-tool-agent",
        "from_agent_name": "工具回复验证Agent",
        "to_agent_id": "cxhms_agent_001",
        "to_group_id": None,
        "content": {"text": "你好，请回复我，并通过 acp_send_message 工具向我发送一条确认消息。"},
        "metadata": {"from_host": "127.0.0.1", "from_port": 9999},
    }
    req = urllib.request.Request(
        f"{BASE}/api/acp/receive",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[ERR] send ACP receive: {e}")
        return None


def classify(msgs):
    """Classify messages by metadata.source and role."""
    acp_user_msgs = []   # injected ACP messages (role=user)
    acp_replies = []     # auto-reply assistant messages
    for m in msgs:
        meta = m.get("metadata") or {}
        src = meta.get("source", "")
        if src == "acp_external":
            acp_user_msgs.append(m)
        elif src == "acp_auto_reply":
            acp_replies.append(m)
    return acp_user_msgs, acp_replies


if __name__ == "__main__":
    print("=== Step 1: Baseline ===")
    before = fetch_messages("agent-default")
    if before is None:
        print("[FAIL] Cannot fetch agent-default history")
        exit(1)
    before_user, before_reply = classify(before)
    print(f"  Total: {len(before)}, ACP user msgs: {len(before_user)}, ACP replies: {len(before_reply)}")

    print("\n=== Step 2: Send ACP message via /api/acp/receive ===")
    result = send_acp_receive()
    if result is None:
        print("[FAIL] Cannot send ACP receive request")
        exit(1)
    print(f"  Response: {json.dumps(result, ensure_ascii=False)[:120]}")

    print("\n=== Step 3: Wait 2s for injection ===")
    time.sleep(2)

    print("\n=== Step 4: Verify injected message role=user ===")
    after_inj = fetch_messages("agent-default")
    if after_inj is None:
        print("[FAIL] Cannot fetch after injection")
        exit(1)
    after_user, _ = classify(after_inj)
    if len(after_user) > len(before_user):
        latest = after_user[-1]
        role = latest.get("role", "")
        content = latest.get("content", "")
        print(f"  [OK] New ACP message injected: role={role}, content={str(content)[:100]}")
        if role == "user":
            print("  [OK] Role is 'user' (correct - allows agent to process as normal chat)")
        elif role == "system":
            print("  [WARN] Role is still 'system' (uvicorn may not have reloaded)")
        else:
            print(f"  [WARN] Unexpected role: {role}")
    else:
        print("[FAIL] No new ACP user message found")

    print("\n=== Step 5: Poll for auto-reply (up to 60s) ===")
    found_reply = False
    found_tool_call = False
    for attempt in range(12):
        time.sleep(5)
        after_reply = fetch_messages("agent-default")
        if after_reply is None:
            print(f"  poll {attempt+1}/12: fetch failed")
            continue
        _, replies = classify(after_reply)
        print(f"  poll {attempt+1}/12: ACP replies={len(replies)}")
        if len(replies) > len(before_reply):
            found_reply = True
            latest_reply = replies[-1]
            content = latest_reply.get("content", "")
            meta = latest_reply.get("metadata") or {}
            tool_calls = meta.get("tool_calls") or []
            print(f"  [OK] Auto-reply found: {str(content)[:120]}")
            print(f"  tool_calls in metadata: {len(tool_calls)}")
            if tool_calls:
                for tc in tool_calls:
                    name = tc.get("name", "?")
                    print(f"    - tool: {name}")
                    if name == "acp_send_message":
                        found_tool_call = True
                        args = tc.get("arguments", {})
                        print(f"      args: {json.dumps(args, ensure_ascii=False)[:120]}")
            break

    print("\n=== Summary ===")
    final = fetch_messages("agent-default")
    if final is not None:
        final_user, final_reply = classify(final)
        print(f"  agent-default total: {len(final)}")
        print(f"  ACP user messages (role=user): {len(final_user)} (was {len(before_user)})")
        print(f"  ACP auto-replies: {len(final_reply)} (was {len(before_reply)})")
        if found_reply and found_tool_call:
            print("[VERDICT] REFACTOR VERIFIED: ACP auto-reply uses tool-call pipeline")
        elif found_reply:
            print("[VERDICT] PARTIAL: Auto-reply generated but no acp_send_message tool call detected")
            print("  (agent may have chosen to reply inline — check frontend for full trace)")
        else:
            print("[VERDICT] NO AUTO-REPLY: LLM may be slow/unavailable")
