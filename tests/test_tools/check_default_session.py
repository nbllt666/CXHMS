"""Quick check: query agent-default session history before/after ACP send."""
import json
import sys
import urllib.request


def fetch_history(session_id: str = "agent-default"):
    url = f"http://localhost:8001/api/chat/history/{session_id}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"[ERR] fetch {session_id}: {e}")
        return None

    if isinstance(data, dict):
        msgs = data.get("messages") or data.get("data", {}).get("messages") or []
    else:
        msgs = data
    return msgs


def show(tag: str, msgs):
    print(f"=== {tag} ===")
    if msgs is None:
        print("  (no data)")
        return
    print(f"Total: {len(msgs)}")
    for m in msgs[-5:]:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, dict):
            content = content.get("text") or str(content)
        ctype = m.get("content_type", "")
        src = (m.get("metadata") or {}).get("source", "")
        print(f"  [{role}/{ctype}/{src}] {str(content)[:100]}")


if __name__ == "__main__":
    session = sys.argv[1] if len(sys.argv) > 1 else "agent-default"
    msgs = fetch_history(session)
    show(session, msgs)
