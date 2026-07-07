"""
触发后端 /chat/stream 接口，捕获实际工具调用场景的完整响应。
后端已添加详细日志，可对比 vLLM 直接测试结果。
"""
import json
import time

import httpx

BACKEND_URL = "http://localhost:8001/api/chat/stream"

# 多种触发消息，确保至少有一个能触发工具调用
TEST_MESSAGES = [
    "我们之前聊过什么？",
    "搜索一下我之前的记忆",
    "帮我看看我有什么记忆",
]


def trigger(message: str):
    print(f"\n========== 测试消息: {message!r} ==========")
    body = {
        "message": message,
        "agent_id": "default",
        "stream": True,
    }
    t0 = time.monotonic()
    events = []
    try:
        with httpx.Client(timeout=180.0, trust_env=False) as client:
            with client.stream("POST", BACKEND_URL, json=body) as resp:
                print(f"  HTTP {resp.status_code}")
                if resp.status_code != 200:
                    print(f"  Error: {resp.read()[:300]}")
                    return
                for line in resp.iter_lines():
                    if not line:
                        continue
                    # SSE 格式：data: {...}
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            print("  [DONE]")
                            break
                        try:
                            evt = json.loads(data)
                            events.append(evt)
                            evt_type = evt.get("type", "?")
                            # 简要打印事件
                            if evt_type == "tool_call":
                                tc = evt.get("tool_call", {})
                                fn = tc.get("function", {})
                                print(f"  [{len(events)}] tool_call: {fn.get('name')} args={fn.get('arguments', '')[:80]!r}")
                            elif evt_type == "tool_result":
                                print(f"  [{len(events)}] tool_result: {evt.get('tool_name')}")
                            elif evt_type == "thinking":
                                content = evt.get("content", "")
                                # 只打印 thinking 摘要
                                if len(content) < 80:
                                    print(f"  [{len(events)}] thinking: {content!r}")
                            elif evt_type == "content":
                                content = evt.get("content", "")
                                print(f"  [{len(events)}] content: {content!r}")
                            elif evt_type == "done":
                                print(f"  [{len(events)}] done: session={evt.get('session_id')}")
                            elif evt_type == "error":
                                print(f"  [{len(events)}] ERROR: {evt.get('error') or evt.get('content')}")
                            else:
                                print(f"  [{len(events)}] {evt_type}: {str(evt)[:100]}")
                        except json.JSONDecodeError:
                            print(f"  raw: {line[:200]}")
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  总耗时: {elapsed:.0f}ms, 事件数: {len(events)}")
        # 统计
        tool_calls = [e for e in events if e.get("type") == "tool_call"]
        contents = [e for e in events if e.get("type") == "content"]
        thinkings = [e for e in events if e.get("type") == "thinking"]
        print(f"  统计: tool_calls={len(tool_calls)}, content_events={len(contents)}, thinking_events={len(thinkings)}")
    except Exception as e:
        print(f"  异常: {e}")


for msg in TEST_MESSAGES:
    trigger(msg)
    time.sleep(2)

print("\n========== 测试完成 ==========")
print("请查看后端日志获取详细 stream_chat 调试信息：")
print(f"  tail -f C:\\Users\\NBLLT666\\AppData\\Local\\Temp\\trae-agent-toolhost\\jobs\\job-a59a17db38bb4f2c9720d15f7b7aca53\\output.log")
