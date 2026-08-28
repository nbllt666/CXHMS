"""直接测试 vLLM 流式响应格式，检查是否返回 delta.tool_calls"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx


async def test_vllm_streaming():
    """测试 vLLM 流式响应是否返回结构化 tool_calls"""
    url = "http://localhost:8002/v1/chat/completions"

    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "数学计算器",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式",
                        }
                    },
                    "required": ["expression"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "datetime",
                "description": "获取当前日期时间",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "日期格式，如 YYYY-MM-DD HH:mm:ss",
                        }
                    },
                },
            },
        },
    ]

    # 测试1：带 tool_choice=auto
    request_body = {
        "model": "gemma4-e4b",
        "messages": [
            {"role": "system", "content": "你是一个助手，可以调用工具。"},
            {"role": "user", "content": "用 datetime 工具获取当前时间，格式 YYYY-MM-DD HH:mm:ss"},
        ],
        "stream": True,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 512,
    }

    print("=" * 70)
    print("测试1: tool_choice=auto")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        async with client.stream("POST", url, json=request_body) as response:
            print(f"HTTP {response.status_code}")
            if response.status_code != 200:
                error_text = await response.aread()
                print(f"Error: {error_text.decode('utf-8', errors='replace')[:500]}")
                return

            chunk_count = 0
            has_tool_calls = False
            has_content_tool_tag = False
            async for line in response.aiter_lines():
                if line:
                    decoded = line if isinstance(line, str) else line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data = decoded[6:]
                        if data == "[DONE]":
                            print("\n[DONE]")
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})

                            if "tool_calls" in delta:
                                has_tool_calls = True
                                print(f"\n[CHUNK {chunk_count}] delta.tool_calls: {json.dumps(delta['tool_calls'], ensure_ascii=False)}")
                            elif "content" in delta and delta["content"]:
                                content = delta["content"]
                                if "<|tool_call>" in content or "<tool_call|>" in content:
                                    has_content_tool_tag = True
                                if chunk_count < 5 or has_content_tool_tag:
                                    print(f"[CHUNK {chunk_count}] content: {repr(content[:80])}")
                            elif "reasoning_content" in delta and delta["reasoning_content"]:
                                print(f"[CHUNK {chunk_count}] reasoning: {repr(delta['reasoning_content'][:60])}")

                            chunk_count += 1
                        except json.JSONDecodeError:
                            continue

    print()
    print(f"总 chunks: {chunk_count}")
    print(f"有 delta.tool_calls: {has_tool_calls}")
    print(f"有 content 中含 <|tool_call> 标签: {has_content_tool_tag}")

    # 测试2：带 tool_choice=required
    print()
    print("=" * 70)
    print("测试2: tool_choice=required")
    print("=" * 70)

    request_body2 = dict(request_body)
    request_body2["tool_choice"] = "required"

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        async with client.stream("POST", url, json=request_body2) as response:
            print(f"HTTP {response.status_code}")
            if response.status_code != 200:
                error_text = await response.aread()
                print(f"Error: {error_text.decode('utf-8', errors='replace')[:500]}")
                return

            chunk_count = 0
            has_tool_calls = False
            has_content_tool_tag = False
            async for line in response.aiter_lines():
                if line:
                    decoded = line if isinstance(line, str) else line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data = decoded[6:]
                        if data == "[DONE]":
                            print("\n[DONE]")
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})

                            if "tool_calls" in delta:
                                has_tool_calls = True
                                print(f"\n[CHUNK {chunk_count}] delta.tool_calls: {json.dumps(delta['tool_calls'], ensure_ascii=False)}")
                            elif "content" in delta and delta["content"]:
                                content = delta["content"]
                                if "<|tool_call>" in content or "<tool_call|>" in content:
                                    has_content_tool_tag = True
                                if chunk_count < 5 or has_content_tool_tag:
                                    print(f"[CHUNK {chunk_count}] content: {repr(content[:80])}")

                            chunk_count += 1
                        except json.JSONDecodeError:
                            continue

    print()
    print(f"总 chunks: {chunk_count}")
    print(f"有 delta.tool_calls: {has_tool_calls}")
    print(f"有 content 中含 <|tool_call> 标签: {has_content_tool_tag}")


if __name__ == "__main__":
    asyncio.run(test_vllm_streaming())
