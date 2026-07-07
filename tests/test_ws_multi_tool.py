"""多轮工具调用测试：验证连续调用多个工具的完整流程。

测试场景：先查当前时间，再算 25*15，最后把结果保存到记忆。
预期：LLM 连续发起多个结构化 tool_call，每个工具执行后继续下一个。
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
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"[收到] {raw[:100]}")

            msg = {
                "type": "chat",
                "message": "帮我做三件事：1. 用 datetime 工具查当前时间 2. 用 calculator 工具计算 25*15 3. 用 write_long_term_memory 工具保存一条记忆：用户测试了多轮工具调用",
            }
            print(f"\n[发送] {msg['message'][:80]}...")
            await ws.send(json.dumps(msg))

            events = []
            tool_call_events = []
            content_events = []
            tool_start_count = 0
            tool_result_count = 0
            try:
                for _ in range(2000):
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(raw)
                    etype = data.get("type")
                    events.append(etype)
                    if etype == "tool_call":
                        tc = data.get("tool_call", {})
                        func = tc.get("function", {})
                        tool_call_events.append(func.get("name", "unknown"))
                        print(f"[tool_call] name={func.get('name')} args={func.get('arguments','')[:80]}")
                    elif etype == "content":
                        content = data.get("content", "")
                        content_events.append(content)
                        if "<|tool_call>" in content:
                            print(f"[警告] content 含 <|tool_call> 标签: {content[:100]}")
                        elif len(content) > 50:
                            print(f"[content] {content[:80]}...")
                    elif etype == "tool_start":
                        tool_start_count += 1
                        print(f"[tool_start] {data.get('tool_name')}")
                    elif etype == "tool_result":
                        tool_result_count += 1
                        print(f"[tool_result] {data.get('tool_name')} -> {str(data.get('result'))[:80]}")
                    elif etype == "thinking":
                        print(f"[thinking] {data.get('content','')[:80]}")
                    elif etype == "done":
                        print(f"[done] session={data.get('session_id')}")
                        break
                    elif etype == "error":
                        print(f"[error] {data.get('error')}")
                        break
                    elif etype == "session":
                        print(f"[session] {data.get('session_id')}")
                    else:
                        print(f"[{etype}] {str(data)[:80]}")
            except asyncio.TimeoutError:
                print("\n[超时] 60秒无消息")

            print(f"\n=== 汇总 ===")
            print(f"事件序列: {events[:30]}...")
            print(f"tool_call 数: {len(tool_call_events)} -> {tool_call_events}")
            print(f"tool_start 数: {tool_start_count}")
            print(f"tool_result 数: {tool_result_count}")
            print(f"content 数: {len(content_events)}")
            full_content = "".join(content_events)
            print(f"\n完整回复: {full_content[:300]}")
            if "<|tool_call>" in full_content:
                print("[问题] content 中含 <|tool_call> 文本标签")
            else:
                print("[OK] content 中无 <|tool_call> 文本标签")
            if len(tool_call_events) >= 2:
                print(f"[OK] 多轮工具调用成功: {len(tool_call_events)} 个工具调用")
            elif len(tool_call_events) == 1:
                print(f"[部分] 只有 1 个工具调用，未触发多轮")
            else:
                print(f"[问题] 无工具调用")
    except Exception as e:
        print(f"[错误] {type(e).__name__}: {e}")
        sys.exit(1)


asyncio.run(main())
