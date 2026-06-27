"""
WebSocket 聊天端到端测试：验证工具调用通过 WebSocket 正确触发。
用法: python test_ws_chat.py "<消息>" [agent_id]
"""
import sys
import json
import asyncio
import urllib.request

# 使用 websockets 库（如果可用），否则用 websocket-client
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


def get_ws_url(agent_id: str, timeout: int = 60) -> str:
    base = "ws://127.0.0.1:8001"
    return f"{base}/ws/{agent_id}?timeout={timeout}"


async def test_with_websockets(agent_id: str, message: str):
    url = get_ws_url(agent_id)
    print(f"连接 WebSocket: {url}")

    events = []
    content_parts = []
    thinking_parts = []
    tool_calls = []
    tool_results = []

    async with websockets.connect(url) as ws:
        # 发送聊天消息
        await ws.send(json.dumps({"type": "chat", "message": message}))
        print(f"已发送: {message}\n")

        # 接收消息
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
            except asyncio.TimeoutError:
                print("[超时等待响应]")
                break

            data = json.loads(raw)
            etype = data.get("type")
            events.append(etype)

            if etype == "content":
                content_parts.append(data.get("content", ""))
            elif etype == "thinking":
                thinking_parts.append(data.get("content", ""))
            elif etype == "tool_call":
                tc = data.get("tool_call", {})
                fn = tc.get("function", {}).get("name") or tc.get("name", "")
                args = tc.get("function", {}).get("arguments") or tc.get("arguments")
                tool_calls.append({"name": fn, "arguments": args})
                print(f"  [tool_call] {fn}: {args}")
            elif etype == "tool_start":
                print(f"  [tool_start] {data.get('tool_name')}")
            elif etype == "tool_result":
                tool_results.append({"name": data.get("tool_name"), "result": data.get("result")})
                rs = json.dumps(data.get("result"), ensure_ascii=False)
                if len(rs) > 150:
                    rs = rs[:150] + "..."
                print(f"  [tool_result] {data.get('tool_name')}: {rs}")
            elif etype == "content":
                print(f"  [content] {data.get('content', '')[:80]}")
            elif etype == "done":
                print(f"\n  [done] session={data.get('session_id')}")
                break
            elif etype == "error":
                print(f"\n  [error] {data.get('error')}")
                break
            elif etype == "cancelled":
                print(f"\n  [cancelled]")
                break
            elif etype == "session":
                print(f"  [session] {data.get('session_id')}")
            elif etype == "pong":
                pass
            else:
                print(f"  [{etype}] {json.dumps(data, ensure_ascii=False)[:100]}")

    return {
        "events": events,
        "content": "".join(content_parts),
        "thinking": "".join(thinking_parts),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
    }


def test_with_urllib_fallback(agent_id: str, message: str):
    """如果没有 websockets 库，回退到 SSE 端点测试（验证共享逻辑）"""
    print("websockets 库不可用，回退到 SSE 端点测试（验证共享逻辑）...\n")
    url = "http://127.0.0.1:8001/api/chat/stream"
    payload = json.dumps({"agent_id": agent_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

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
                try:
                    evt = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                events.append(etype)
                if etype == "content":
                    content_parts.append(evt.get("content", ""))
                    print(f"  [content] {evt.get('content', '')[:80]}")
                elif etype == "thinking":
                    thinking_parts.append(evt.get("content", ""))
                elif etype == "tool_call":
                    tc = evt.get("tool_call", {})
                    fn = tc.get("function", {}).get("name") or tc.get("name", "")
                    args = tc.get("function", {}).get("arguments") or tc.get("arguments")
                    tool_calls.append({"name": fn, "arguments": args})
                    print(f"  [tool_call] {fn}: {args}")
                elif etype == "tool_start":
                    print(f"  [tool_start] {evt.get('tool_name')}")
                elif etype == "tool_result":
                    tool_results.append({"name": evt.get("tool_name"), "result": evt.get("result")})
                    rs = json.dumps(evt.get("result"), ensure_ascii=False)
                    if len(rs) > 150:
                        rs = rs[:150] + "..."
                    print(f"  [tool_result] {evt.get('tool_name')}: {rs}")
                elif etype == "done":
                    print(f"\n  [done]")
                elif etype == "error":
                    print(f"\n  [error] {evt.get('error')}")

    return {
        "events": events,
        "content": "".join(content_parts),
        "thinking": "".join(thinking_parts),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
    }


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else "现在几点了"
    agent_id = sys.argv[2] if len(sys.argv) > 2 else "default"

    print(f"=== WebSocket 测试: agent='{agent_id}' message='{message}' ===\n")

    if HAS_WEBSOCKETS:
        result = asyncio.run(test_with_websockets(agent_id, message))
    else:
        result = test_with_urllib_fallback(agent_id, message)

    print(f"\n{'='*50}")
    print(f"事件序列: {result['events']}")
    print(f"工具调用 ({len(result['tool_calls'])} 个): {result['tool_calls']}")
    print(f"工具结果 ({len(result['tool_results'])} 个)")
    print(f"思考内容 ({len(result['thinking'])} 字符)")
    print(f"回复内容 ({len(result['content'])} 字符): {result['content'][:200]}")

    print(f"\n=== 验证检查点 ===")
    checks = [
        ("工具调用被触发", len(result["tool_calls"]) > 0),
        ("工具结果已返回", len(result["tool_results"]) > 0),
        ("LLM 生成最终回复", len(result["content"]) > 0),
        ("非默认兜底文案", result["content"] != "已完成工具调用。"),
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
