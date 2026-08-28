"""测试流式模式下的工具调用，并逐步增加消息复杂度以复现后端问题。

后端日志显示：16条消息（3个system）、stream=True、tool_call_chunks=0、finish_reason=stop
直接测试：1-2条消息、stream=False → 全部成功

逐步测试：
1. 简单消息 + stream=True
2. 多 system 消息 + stream=True
3. 完整后端消息结构 + stream=True
"""
import json
import os
import sys

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

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_memories",
        "description": "Search user memories by query",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
}


def run_streaming_test(name: str, messages: list, tools: list, enable_thinking: bool = True):
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"thinking={enable_thinking}, tools={len(tools)}, messages={len(messages)}")
    print(f"{'='*60}")

    body = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": True,
        "max_tokens": 2048,
        "temperature": 0.7,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    chunks = 0
    content_chars = 0
    reasoning_chars = 0
    tool_call_chunks = 0
    finish_reason = None
    first_content_preview = None
    first_tool_call_chunk = None
    raw_chunks_with_tool_call_tag = []

    try:
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            with client.stream("POST", VLLM_URL, json=body) as resp:
                if resp.status_code != 200:
                    print(f"HTTP {resp.status_code}: {resp.read().decode('utf-8', errors='replace')[:300]}")
                    return

                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    chunks += 1
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        choice = chunk["choices"][0]
                        delta = choice.get("delta", {})
                        fr = choice.get("finish_reason")
                        if fr:
                            finish_reason = fr

                        rc = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                        if rc and rc != "<pad>":
                            reasoning_chars += len(rc)

                        c = delta.get("content", "")
                        if c and c != "<pad>":
                            content_chars += len(c)
                            if first_content_preview is None:
                                first_content_preview = c[:80]
                            if "<|tool_call>" in c:
                                raw_chunks_with_tool_call_tag.append(c)

                        tcs = delta.get("tool_calls")
                        if tcs:
                            tool_call_chunks += 1
                            if first_tool_call_chunk is None:
                                first_tool_call_chunk = tcs[0]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    except Exception as e:
        print(f"异常: {e}")
        return

    print(f"chunks={chunks}, content_chars={content_chars}, reasoning_chars={reasoning_chars}")
    print(f"tool_call_chunks={tool_call_chunks}, finish_reason={finish_reason}")
    print(f"first_content_preview={repr(first_content_preview) if first_content_preview else None}")
    if first_tool_call_chunk:
        print(f"first_tool_call: {first_tool_call_chunk.get('function', {}).get('name', '')}")
    if raw_chunks_with_tool_call_tag:
        print(f"⚠️ 发现 {len(raw_chunks_with_tool_call_tag)} 个 chunk 的 content 包含 <|tool_call> 文本（parser 未提取为 tool_calls）")
        for i, c in enumerate(raw_chunks_with_tool_call_tag[:3]):
            print(f"  raw[{i}]: {c[:200]}")


def main():
    # 场景1: 简单消息 + stream=True
    run_streaming_test(
        "简单消息 + 流式",
        messages=[
            {"role": "system", "content": "你是天气助手。需要天气信息时请调用 get_weather 工具。"},
            {"role": "user", "content": "东京今天天气怎么样？"},
        ],
        tools=[WEATHER_TOOL],
    )

    # 场景2: 先回复再工具调用 + 流式
    run_streaming_test(
        "先回复再工具调用 + 流式",
        messages=[
            {"role": "system", "content": "你是记忆助手。当用户询问记忆时，先简短回复，然后调用 search_memories 工具搜索。"},
            {"role": "user", "content": "帮我找找关于上次测试的记忆"},
        ],
        tools=[SEARCH_TOOL],
    )

    # 场景3: 多个 system 消息 + 流式（模拟后端结构）
    run_streaming_test(
        "多 system 消息 + 流式",
        messages=[
            {"role": "system", "content": "你是 CXHMS 人格化记忆助手。基于用户对话和工具结果生成自然回复。"},
            {"role": "system", "content": "可用工具说明：search_memories 可搜索用户记忆；get_weather 可查询天气。根据用户需求选择合适工具。"},
            {"role": "system", "content": "回复要求：1) 使用中文 2) 简洁自然 3) 需要信息时主动调用工具"},
            {"role": "user", "content": "查一下东京的天气"},
        ],
        tools=[WEATHER_TOOL, SEARCH_TOOL],
    )

    # 场景4: 复杂对话历史 + 多 system + 流式（更接近后端实际请求）
    run_streaming_test(
        "复杂对话历史 + 多 system + 流式",
        messages=[
            {"role": "system", "content": "你是 CXHMS 人格化记忆助手。基于用户对话和工具结果生成自然回复。"},
            {"role": "system", "content": "可用工具说明：search_memories 可搜索用户记忆；get_weather 可查询天气。根据用户需求选择合适工具。"},
            {"role": "system", "content": "回复要求：1) 使用中文 2) 简洁自然 3) 需要信息时主动调用工具"},
            {"role": "user", "content": "你好，我想测试一下工具调用功能"},
            {"role": "assistant", "content": "好的，我来帮你测试工具调用功能。你想测试什么场景？"},
            {"role": "user", "content": "帮我查一下天气"},
            {"role": "assistant", "content": "好的，让我帮你查一下天气。请问你想查哪个城市的天气？"},
            {"role": "user", "content": "东京"},
        ],
        tools=[WEATHER_TOOL, SEARCH_TOOL],
    )


if __name__ == "__main__":
    main()
