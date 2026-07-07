"""
测试 vLLM 第二轮响应（多轮工具调用场景）

模拟 stream.py 第2轮的请求：
- 第1轮：LLM 返回 search_all_memories tool_call
- 工具执行后，结果作为 tool message 加入 messages
- 第2轮：LLM 应基于工具结果生成回复

本脚本直接发请求到 vLLM，看第2轮实际输出。
"""
import json
import sys

import httpx

VLLM_URL = "http://localhost:8002/v1/chat/completions"

# 模拟第2轮的 messages（与 stream.py L443-520 构造的格式一致）
MESSAGES = [
    {
        "role": "system",
        "content": "你是CXHMS人格化记忆助手。请基于工具结果生成回复。"
    },
    {
        "role": "user",
        "content": "用户进行了一系列的工具调用测试"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search_all_memories",
                    "arguments": json.dumps({"query": "用户进行了一系列的工具调用测试", "limit": 1}, ensure_ascii=False)
                }
            }
        ]
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "search_all_memories",
        "content": json.dumps({
            "success": True,
            "result": {
                "status": "success",
                "query": "用户进行了一系列的工具调用测试",
                "count": 1,
                "memories": [
                    {
                        "id": 1384,
                        "content": "用户测试了多轮工具调用",
                        "score": 0.4192,
                        "memory_type": "long_term"
                    }
                ]
            }
        }, ensure_ascii=False)
    }
]


def run_test(enable_thinking: bool, max_tokens: int):
    """测试单场景"""
    print(f"\n{'='*60}")
    print(f"测试: enable_thinking={enable_thinking}, max_tokens={max_tokens}")
    print(f"{'='*60}")

    body = {
        "model": "gemma4-e4b",
        "messages": MESSAGES,
        "stream": True,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    reasoning_chars = 0
    content_chars = 0
    tool_call_chunks = 0
    finish_reason = None
    usage = None
    first_chunk_time = None
    last_chunk_time = None
    content_sample = ""
    reasoning_sample = ""

    import time
    start = time.time()

    try:
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            with client.stream("POST", VLLM_URL, json=body) as response:
                print(f"HTTP {response.status_code}")
                if response.status_code != 200:
                    print(f"Error: {response.read().decode('utf-8')[:500]}")
                    return

                for line in response.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                        if first_chunk_time is None:
                            first_chunk_time = time.time() - start

                        last_chunk_time = time.time() - start

                        choice = chunk["choices"][0]
                        delta = choice.get("delta", {})
                        finish = choice.get("finish_reason")
                        if finish:
                            finish_reason = finish

                        u = chunk.get("usage")
                        if u:
                            usage = u

                        # reasoning content
                        rc = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                        if rc and rc != "<pad>":
                            reasoning_chars += len(rc)
                            if len(reasoning_sample) < 200:
                                reasoning_sample += rc

                        # content
                        c = delta.get("content", "")
                        if c and c != "<pad>":
                            content_chars += len(c)
                            if len(content_sample) < 500:
                                content_sample += c

                        # tool_calls
                        tc = delta.get("tool_calls")
                        if tc:
                            tool_call_chunks += 1

                    except (json.JSONDecodeError, KeyError, IndexError) as e:
                        print(f"Parse error: {e}")
                        continue

    except Exception as e:
        print(f"Exception: {e}")
        return

    elapsed = time.time() - start
    print(f"\n--- 结果 ---")
    print(f"耗时: {elapsed:.2f}s (首chunk: {first_chunk_time:.2f}s, 末chunk: {last_chunk_time:.2f}s)")
    print(f"reasoning_content 字符数: {reasoning_chars}")
    print(f"content 字符数: {content_chars}")
    print(f"tool_call chunks: {tool_call_chunks}")
    print(f"finish_reason: {finish_reason}")
    print(f"usage: {usage}")
    print(f"\ncontent 样本 (前500字符):")
    print(repr(content_sample))
    print(f"\nreasoning 样本 (前200字符):")
    print(repr(reasoning_sample))


if __name__ == "__main__":
    # 测试 4 个场景
    run_test(enable_thinking=True, max_tokens=4096)
    run_test(enable_thinking=True, max_tokens=8192)
    run_test(enable_thinking=False, max_tokens=4096)
    run_test(enable_thinking=False, max_tokens=8192)
