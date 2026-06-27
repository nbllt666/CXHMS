"""测试 json_format 工具通过 WebSocket 调用"""
import asyncio
import json
import websockets


async def main():
    url = "ws://127.0.0.1:8001/ws/default?timeout=60"
    message = '请格式化这个JSON: {"name":"test","value":42}'

    print(f"连接: {url}")
    print(f"消息: {message}\n")

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "chat", "message": message}))

        tool_calls = []
        tool_results = []
        content_parts = []

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
            except asyncio.TimeoutError:
                print("[超时]")
                break

            data = json.loads(raw)
            etype = data.get("type")

            if etype == "tool_call":
                tc = data.get("tool_call", {})
                fn = tc.get("function", {}).get("name") or tc.get("name", "")
                args = tc.get("function", {}).get("arguments") or tc.get("arguments")
                tool_calls.append({"name": fn, "arguments": args})
                print(f"  [tool_call] {fn}: {args}")
            elif etype == "tool_start":
                print(f"  [tool_start] {data.get('tool_name')}")
            elif etype == "tool_result":
                tool_results.append(data.get("tool_name"))
                rs = json.dumps(data.get("result"), ensure_ascii=False)
                if len(rs) > 200:
                    rs = rs[:200] + "..."
                print(f"  [tool_result] {data.get('tool_name')}: {rs}")
            elif etype == "content":
                content_parts.append(data.get("content", ""))
            elif etype == "done":
                print(f"\n  [done]")
                break
            elif etype == "error":
                print(f"\n  [error] {data.get('error')}")
                break

    content = "".join(content_parts)
    print(f"\n回复内容 ({len(content)} 字符): {content}")

    print(f"\n=== 检查点 ===")
    checks = [
        ("json_format 工具被触发", any(tc["name"] == "json_format" for tc in tool_calls)),
        ("工具结果已返回", len(tool_results) > 0),
        ("LLM 生成最终回复", len(content) > 0),
    ]
    all_pass = True
    for name, passed in checks:
        print(f"  {'✓' if passed else '✗'} {name}")
        if not passed:
            all_pass = False
    print(f"\n{'全部通过' if all_pass else '存在失败项'}")


if __name__ == "__main__":
    asyncio.run(main())
