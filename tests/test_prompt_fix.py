"""测试 system prompt 修改是否解决了工具调用失败问题。
重点验证之前失败的"搜索一下我之前的记忆"是否能触发 tool_call。
"""
import json
import time

import httpx

BACKEND_URL = "http://localhost:8001/api/chat/stream"

# 重点测试：之前失败的模糊查询
TEST_MESSAGES = [
    "搜索一下我之前的记忆",  # 之前失败：tool_calls=0
    "帮我看看记忆里有什么",  # 类似模糊查询
    "我想知道之前聊过什么",  # 类似模糊查询
]


def trigger(message: str):
    print(f"\n========== 测试: {message!r} ==========")
    body = {
        "message": message,
        "agent_id": "default",
        "stream": True,
    }
    t0 = time.monotonic()
    tool_call_count = 0
    content_text = []
    thinking_text = []
    try:
        with httpx.Client(timeout=180.0, trust_env=False) as client:
            with client.stream("POST", BACKEND_URL, json=body) as resp:
                if resp.status_code != 200:
                    print(f"  HTTP {resp.status_code}: {resp.read()[:200]}")
                    return
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        evt = json.loads(data)
                        evt_type = evt.get("type", "?")
                        if evt_type == "tool_call":
                            tool_call_count += 1
                            tc = evt.get("tool_call", {})
                            fn = tc.get("function", {})
                            print(f"  [tool_call] {fn.get('name')}: {fn.get('arguments', '')[:80]!r}")
                        elif evt_type == "content":
                            content_text.append(evt.get("content", ""))
                        elif evt_type == "thinking":
                            thinking_text.append(evt.get("content", ""))
                        elif evt_type == "done":
                            break
                        elif evt_type == "error":
                            print(f"  [ERROR] {evt}")
                            return
                    except json.JSONDecodeError:
                        pass
        elapsed = (time.monotonic() - t0) * 1000
        full_content = "".join(content_text)
        full_thinking = "".join(thinking_text)
        # 结果
        status = "✓ 成功" if tool_call_count > 0 else "✗ 失败"
        print(f"  结果: {status}, tool_calls={tool_call_count}, 耗时={elapsed:.0f}ms")
        print(f"  content ({len(full_content)} chars): {full_content[:200]!r}")
        if not tool_call_count:
            # 失败时打印 thinking 帮助分析
            print(f"  thinking ({len(full_thinking)} chars): {full_thinking[:300]!r}")
    except Exception as e:
        print(f"  异常: {e}")


for msg in TEST_MESSAGES:
    trigger(msg)
    time.sleep(2)

print("\n========== 测试完成 ==========")
