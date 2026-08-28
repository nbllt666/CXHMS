"""验证 tool_choice 缺失是否是工具调用失败的根因。

后端代码没有设置 tool_choice，而 vLLM 默认行为可能不触发工具调用。
对比测试：
1. 设置 tool_choice=auto
2. 不设置 tool_choice（复现后端行为）
3. 设置 tool_choice=none（对照）
"""
import json
import os

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
            "properties": {"location": {"type": "string", "description": "City name"}},
            "required": ["location"],
        },
    },
}

MESSAGES = [
    {"role": "system", "content": "你是 CXHMS 人格化记忆助手。基于用户对话和工具结果生成自然回复。"},
    {"role": "system", "content": "可用工具说明：get_weather 可查询天气。根据用户需求选择合适工具。"},
    {"role": "system", "content": "回复要求：1) 使用中文 2) 简洁自然 3) 需要信息时主动调用工具"},
    {"role": "user", "content": "查一下东京的天气"},
]


def run_test(name: str, set_tool_choice: bool = True, tool_choice_value: str = "auto"):
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"{'='*60}")

    body = {
        "model": MODEL,
        "messages": MESSAGES,
        "tools": [WEATHER_TOOL],
        "stream": False,
        "max_tokens": 2048,
        "temperature": 0.7,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    if set_tool_choice:
        body["tool_choice"] = tool_choice_value

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
            content = msg.get("content") or ""
            tcs = msg.get("tool_calls") or []

            print(f"tool_choice in request: {'set=' + repr(body.get('tool_choice')) if 'tool_choice' in body else 'NOT SET'}")
            print(f"finish_reason: {finish}")
            print(f"content (len={len(content)}): {content[:200]}")
            print(f"tool_calls count: {len(tcs)}")
            for i, tc in enumerate(tcs):
                print(f"  tool_call[{i}]: {tc.get('function', {}).get('name')} args={tc.get('function', {}).get('arguments')}")

    except Exception as e:
        print(f"异常: {e}")


def main():
    # 场景1: tool_choice=auto（基线）
    run_test("tool_choice=auto", set_tool_choice=True, tool_choice_value="auto")

    # 场景2: 不设置 tool_choice（复现后端行为）
    run_test("tool_choice 未设置（复现后端）", set_tool_choice=False)

    # 场景3: tool_choice=none（对照）
    run_test("tool_choice=none（对照）", set_tool_choice=True, tool_choice_value="none")


if __name__ == "__main__":
    main()
