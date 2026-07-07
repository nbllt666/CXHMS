"""直接测试 vLLM 工具调用能力——排除后端干扰，验证模型是否能生成 <|tool_call> token。

测试场景：
1. 简单工具调用（weather）
2. 先回复再调用工具（search）—— 复现用户报告的"生成回复后无法工具调用"场景
3. 多工具场景
"""
import json
import os
import sys

# 清除代理环境变量，避免 502
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(k, None)

import httpx

VLLM_URL = "http://localhost:8002/v1/chat/completions"
MODEL = "gemma4-e4b"

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
            },
            "required": ["location"],
        },
    },
}

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_memories",
        "description": "Search user memories by query",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    },
}


def run_test(name: str, messages: list, tools: list, enable_thinking: bool = True):
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"thinking={enable_thinking}, tools={len(tools)}")
    print(f"{'='*60}")

    body = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
        "max_tokens": 2048,
        "temperature": 0.7,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    try:
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            resp = client.post(VLLM_URL, json=body)
            if resp.status_code != 200:
                print(f"HTTP {resp.status_code}: {resp.text[:300]}")
                return

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            finish = choice.get("finish_reason")
            usage = data.get("usage", {})

            print(f"finish_reason: {finish}")
            print(f"usage: {usage}")
            print(f"content (len={len(msg.get('content') or '')}): {(msg.get('content') or '')[:300]}")
            print(f"reasoning (len={len(msg.get('reasoning_content') or '')}): {(msg.get('reasoning_content') or '')[:300]}")
            tcs = msg.get("tool_calls") or []
            print(f"tool_calls count: {len(tcs)}")
            for i, tc in enumerate(tcs):
                print(f"  tool_call[{i}]: {tc.get('function', {}).get('name')} args={tc.get('function', {}).get('arguments')}")

            # 检查 content 中是否包含 <|tool_call> 文本
            content = msg.get("content") or ""
            if "<|tool_call>" in content:
                print(f"⚠️ content 中包含 <|tool_call> 文本（parser 未提取）")
                print(f"   content 片段: {content[:500]}")

    except Exception as e:
        print(f"异常: {e}")


def main():
    # 场景1: 简单工具调用
    run_test(
        "简单工具调用（weather）",
        messages=[
            {"role": "system", "content": "你是天气助手。需要天气信息时请调用 get_weather 工具。"},
            {"role": "user", "content": "东京今天天气怎么样？"},
        ],
        tools=[WEATHER_TOOL],
    )

    # 场景2: 先回复再调用工具——复现用户报告的场景
    run_test(
        "先回复再工具调用（search）",
        messages=[
            {"role": "system", "content": "你是记忆助手。当用户询问记忆时，先简短回复，然后调用 search_memories 工具搜索。"},
            {"role": "user", "content": "帮我找找关于上次测试的记忆"},
        ],
        tools=[SEARCH_TOOL],
    )

    # 场景3: 多工具场景
    run_test(
        "多工具场景",
        messages=[
            {"role": "system", "content": "你可以查询天气和搜索记忆。根据用户需求选择合适工具。"},
            {"role": "user", "content": "查一下巴黎天气，再搜一下我关于巴黎的记忆"},
        ],
        tools=[WEATHER_TOOL, SEARCH_TOOL],
    )

    # 场景4: 关闭 thinking
    run_test(
        "关闭 thinking 的工具调用",
        messages=[
            {"role": "system", "content": "你是天气助手。需要天气信息时请调用 get_weather 工具。"},
            {"role": "user", "content": "东京今天天气怎么样？"},
        ],
        tools=[WEATHER_TOOL],
        enable_thinking=False,
    )


if __name__ == "__main__":
    main()
