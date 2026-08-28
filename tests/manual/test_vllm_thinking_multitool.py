"""直接测试 vLLM：enable_thinking=True + 多工具请求，对比不同 max_tokens。

诊断假设：thinking 内容耗尽 max_tokens=4096 预算，导致 <|tool_call> 标签未输出。
"""
import json
import time

import httpx

URL = "http://localhost:8002/v1/chat/completions"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "datetime",
            "description": "获取当前日期时间",
            "parameters": {
                "type": "object",
                "properties": {"format": {"type": "string"}},
                "required": ["format"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "数学计算",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_long_term_memory",
            "description": "写入长期记忆",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    },
]

MESSAGES = [
    {
        "role": "user",
        "content": "帮我做三件事：1. 用 datetime 工具查当前时间 2. 用 calculator 工具计算 25*15 3. 用 write_long_term_memory 工具保存一条记忆：用户测试了多轮工具调用",
    }
]


def run_test(max_tokens: int, enable_thinking: bool):
    body = {
        "model": "gemma4-e4b",
        "messages": MESSAGES,
        "stream": True,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    reasoning_chars = 0
    content_chars = 0
    content_buffer = ""
    has_tool_call_tag = False
    structured_tool_calls = {}
    finish_reason = None
    usage = None
    chunk_count = 0
    start = time.time()

    with httpx.Client(timeout=300) as c:
        with c.stream("POST", URL, json=body) as r:
            if r.status_code != 200:
                print(f"  HTTP {r.status_code}: {r.text[:200]}")
                return
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                d = line[6:]
                if d == "[DONE]":
                    break
                try:
                    ch = json.loads(d)
                    chunk_count += 1
                    choice = ch["choices"][0]
                    delta = choice.get("delta", {})
                    fr = choice.get("finish_reason")
                    if fr:
                        finish_reason = fr
                    if ch.get("usage"):
                        usage = ch["usage"]
                    rc = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                    if rc and rc != "<pad>":
                        reasoning_chars += len(rc)
                    ct = delta.get("content", "")
                    if ct and ct != "<pad>":
                        content_chars += len(ct)
                        content_buffer += ct
                        if "<|tool_call>" in ct:
                            has_tool_call_tag = True
                    tcs = delta.get("tool_calls")
                    if tcs:
                        for tc in tcs:
                            idx = tc.get("index", 0)
                            if idx not in structured_tool_calls:
                                structured_tool_calls[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": "",
                                    "args": "",
                                }
                            f = tc.get("function", {})
                            if f.get("name"):
                                structured_tool_calls[idx]["name"] += f["name"]
                            if f.get("arguments"):
                                structured_tool_calls[idx]["args"] += f["arguments"]
                except Exception as e:
                    print(f"  parse err: {e}")

    elapsed = time.time() - start
    print(f"\n=== max_tokens={max_tokens}, enable_thinking={enable_thinking} ===")
    print(f"  耗时: {elapsed:.1f}s, chunks: {chunk_count}")
    print(f"  finish_reason: {finish_reason}")
    print(f"  reasoning_content 长度: {reasoning_chars} 字符")
    print(f"  content 长度: {content_chars} 字符")
    print(f"  content 含 <|tool_call> 标签: {has_tool_call_tag}")
    print(f"  结构化 tool_calls: {len(structured_tool_calls)} 个")
    for i in sorted(structured_tool_calls):
        tc = structured_tool_calls[i]
        print(f"    [{i}] name={tc['name']!r} args={tc['args'][:80]!r}")
    if usage:
        print(f"  usage: {usage}")
    if content_buffer:
        print(f"  content 预览: {content_buffer[:150]!r}")


if __name__ == "__main__":
    print("诊断 1: enable_thinking=False, max_tokens=4096 (基线)")
    run_test(max_tokens=4096, enable_thinking=False)

    print("\n诊断 2: enable_thinking=True, max_tokens=4096 (复现问题)")
    run_test(max_tokens=4096, enable_thinking=True)

    print("\n诊断 3: enable_thinking=True, max_tokens=8192")
    run_test(max_tokens=8192, enable_thinking=True)

    print("\n诊断 4: enable_thinking=True, max_tokens=16384")
    run_test(max_tokens=16384, enable_thinking=True)
