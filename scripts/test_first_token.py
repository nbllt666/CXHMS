"""测试首包延迟（first token latency）- 正确端点。"""
import time
import httpx
import json

def test_vllm_stream():
    """vLLM 直连流式首包测试（多次）。"""
    body = {
        "model": "gemma4-e4b",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 30,
        "stream": True,
    }

    with httpx.Client(timeout=60.0, trust_env=False) as client:
        for i in range(3):
            t0 = time.monotonic()
            first_token_time = None
            total_tokens = 0
            with client.stream("POST", "http://localhost:8002/v1/chat/completions", json=body) as resp:
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            total_tokens += 1
                            if first_token_time is None:
                                first_token_time = time.monotonic() - t0
                total_time = time.monotonic() - t0
            print(f"vLLM REQ{i+1}: 首包={int(first_token_time*1000)}ms, 总={int(total_time*1000)}ms")

def test_backend_stream():
    """后端流式测试（正确端点 /api/chat/stream）。"""
    body = {"message": "hi", "agent_id": "default"}
    with httpx.Client(timeout=60.0, trust_env=False) as client:
        t0 = time.monotonic()
        first_event_time = None
        first_content_time = None
        event_count = 0
        with client.stream("POST", "http://localhost:8001/api/chat/stream", json=body) as resp:
            for line in resp.iter_lines():
                t1 = time.monotonic()
                if line and line.startswith("data: "):
                    event_count += 1
                    if first_event_time is None:
                        first_event_time = t1 - t0
                    data_str = line[6:]
                    try:
                        data = json.loads(data_str)
                        if data.get("type") == "content" and first_content_time is None:
                            first_content_time = t1 - t0
                            print(f"  首内容: {int(first_content_time*1000)}ms")
                        elif data.get("type") == "session":
                            print(f"  Session: {int((t1-t0)*1000)}ms")
                        elif data.get("type") == "done":
                            print(f"  Done: {int((t1-t0)*1000)}ms")
                    except json.JSONDecodeError:
                        pass
        total_time = time.monotonic() - t0
        print(f"后端流式: 首事件={int(first_event_time*1000) if first_event_time else 'N/A'}ms, 总={int(total_time*1000)}ms")
        print(f"  事件数: {event_count}")

print("=" * 50)
print("首包延迟测试")
print("=" * 50)

# 预热
print("\n预热...")
with httpx.Client(timeout=10.0, trust_env=False) as client:
    client.post("http://localhost:8002/v1/chat/completions", json={
        "model": "gemma4-e4b",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "stream": False,
    })
    client.post("http://localhost:8001/api/chat/stream", json={
        "message": "hi",
        "agent_id": "default",
    })
print("预热完成")

print("\n--- vLLM 直连流式 ---")
test_vllm_stream()

print("\n--- 后端流式 (/api/chat/stream) ---")
test_backend_stream()