"""
验证主聊天流工具调用后 LLM 能继续生成回复内容。
用法: python test_tool_call_verify.py "<测试消息>"
"""
import sys
import json
import urllib.request

URL = "http://127.0.0.1:8001/api/chat/stream"


def stream_chat(agent_id: str, message: str):
    payload = json.dumps({"agent_id": agent_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    events = []
    content_parts = []
    thinking_parts = []
    tool_calls = []
    tool_results = []

    with urllib.request.urlopen(req, timeout=120) as resp:
        buf = b""
        for chunk in iter(lambda: resp.read(1024), b""):
            buf += chunk
            while b"\n\n" in buf:
                raw, buf = buf.split(b"\n\n", 1)
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data: "):
                    continue
                payload_str = line[6:]
                try:
                    evt = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                events.append(etype)
                if etype == "content":
                    content_parts.append(evt.get("content", ""))
                elif etype == "thinking":
                    thinking_parts.append(evt.get("content", ""))
                elif etype == "tool_call":
                    tc = evt.get("tool_call", {})
                    fn = tc.get("function", {}).get("name") or tc.get("name", "")
                    args = tc.get("function", {}).get("arguments") or tc.get("arguments")
                    tool_calls.append({"name": fn, "arguments": args})
                elif etype == "tool_result":
                    tool_results.append({
                        "name": evt.get("tool_name"),
                        "result": evt.get("result"),
                    })
                elif etype == "error":
                    print(f"[ERROR EVENT] {evt.get('error')}")
                elif etype == "done":
                    pass

    return {
        "events_sequence": events,
        "content": "".join(content_parts),
        "thinking": "".join(thinking_parts),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
    }


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else "现在几点了？"
    agent_id = sys.argv[2] if len(sys.argv) > 2 else "default"

    print(f"=== 测试 Agent='{agent_id}' 消息='{message}' ===\n")
    result = stream_chat(agent_id, message)

    print(f"事件序列: {result['events_sequence']}")
    print(f"\n工具调用 ({len(result['tool_calls'])} 个):")
    for tc in result["tool_calls"]:
        print(f"  - {tc['name']}: {tc['arguments']}")
    print(f"\n工具结果 ({len(result['tool_results'])} 个):")
    for tr in result["tool_results"]:
        rs = json.dumps(tr["result"], ensure_ascii=False) if not isinstance(tr["result"], str) else tr["result"]
        if len(rs) > 200:
            rs = rs[:200] + "..."
        print(f"  - {tr['name']}: {rs}")
    print(f"\n思考内容 ({len(result['thinking'])} 字符): {result['thinking'][:200]}")
    print(f"\n最终回复内容 ({len(result['content'])} 字符):")
    print(result["content"])

    # 验证关键检查点
    print("\n=== 验证检查点 ===")
    checks = [
        ("工具调用被触发", len(result["tool_calls"]) > 0),
        ("工具结果已返回", len(result["tool_results"]) > 0),
        ("LLM 在工具调用后生成最终回复内容", len(result["content"]) > 0),
        ("最终回复内容不是默认兜底文案", result["content"] != "已完成工具调用。"),
    ]
    all_pass = True
    for name, passed in checks:
        marker = "✓" if passed else "✗"
        print(f"  {marker} {name}")
        if not passed:
            all_pass = False

    print(f"\n{'全部通过' if all_pass else '存在失败项'}")


if __name__ == "__main__":
    main()
