"""Inspect agent-default messages - show role/source/tool_calls for each."""
import json
import urllib.request

url = "http://localhost:8001/api/chat/history/agent-default"
with urllib.request.urlopen(url, timeout=180) as r:
    data = json.loads(r.read())

msgs = data.get("messages", data) if isinstance(data, dict) else data
print(f"Total: {len(msgs)}")
print("-" * 80)
for i, m in enumerate(msgs):
    role = m.get("role", "?")
    meta = m.get("metadata") or {}
    src = meta.get("source", "")
    tool_calls = meta.get("tool_calls") or []
    content = str(m.get("content", ""))
    print(f"[{i}] role={role} src={src} tools={len(tool_calls)}")
    print(f"     content: {content[:100]}")
    if tool_calls:
        for tc in tool_calls:
            name = tc.get("name", "?")
            args = tc.get("arguments", {})
            print(f"     tool_call: {name}, args={json.dumps(args, ensure_ascii=False)[:100]}")
    print()
