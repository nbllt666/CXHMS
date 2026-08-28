"""端到端 WebSocket 测试：验证后端完整链路和事件格式。

发送会触发工具调用的消息，检查：
1. WebSocket 连接是否正常
2. 是否返回结构化 tool_call 事件（而非 content 中的文本标签）
3. 多轮工具调用是否正常
"""
import asyncio
import json
import sys

import websockets


async def main():
    url = "ws://localhost:8001/ws/default?timeout=60"
    print(f"连接: {url}")
    try:
        async with websockets.connect(url) as ws:
            # 读取 connected 消息
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"[收到] {raw[:200]}")

            # 发送 chat 消息（触发 datetime 工具调用）
            msg = {
                "type": "chat",
                "message": "现在几点？用 datetime 工具告诉我当前时间，格式 YYYY-MM-DD HH:mm:ss",
            }
            print(f"\n[发送] {msg['message']}")
            await ws.send(json.dumps(msg))

            # 收集事件
            events = []
            tool_call_events = []
            content_events = []
            try:
                for _ in range(100):
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(raw)
                    etype = data.get("type")
                    events.append(etype)
                    if etype == "tool_call":
                        tool_call_events.append(data.get("tool_call"))
                        print(f"[tool_call] {json.dumps(data.get('tool_call'), ensure_ascii=False)[:200]}")
                    elif etype == "content":
                        content = data.get("content", "")
                        content_events.append(content)
                        # 检查是否有原始标签泄漏
                        if "<|tool_call>" in content:
                            print(f"[警告] content 含 <|tool_call> 标签: {content[:200]}")
                        else:
                            print(f"[content] {content[:100]}")
                    elif etype == "tool_start":
                        print(f"[tool_start] {data.get('tool_name')}")
                    elif etype == "tool_result":
                        print(f"[tool_result] {data.get('tool_name')} -> {str(data.get('result'))[:100]}")
                    elif etype == "done":
                        print(f"[done] session={data.get('session_id')}")
                        break
                    elif etype == "error":
                        print(f"[error] {data.get('error')}")
                        break
                    else:
                        print(f"[{etype}] {str(data)[:100]}")
            except asyncio.TimeoutError:
                print("\n[超时] 30秒无消息")

            print(f"\n=== 汇总 ===")
            print(f"事件序列: {events}")
            print(f"tool_call 事件数: {len(tool_call_events)}")
            print(f"content 事件数: {len(content_events)}")
            if tool_call_events:
                print(f"\n第一个 tool_call 结构:")
                print(json.dumps(tool_call_events[0], indent=2, ensure_ascii=False))
            full_content = "".join(content_events)
            print(f"\n完整 content: {full_content[:300]}")
            if "<|tool_call>" in full_content:
                print("[问题] content 中含 <|tool_call> 文本标签 —— vLLM 补丁可能未生效")
            else:
                print("[OK] content 中无 <|tool_call> 文本标签")
    except Exception as e:
        print(f"[错误] {type(e).__name__}: {e}")
        sys.exit(1)


asyncio.run(main())
