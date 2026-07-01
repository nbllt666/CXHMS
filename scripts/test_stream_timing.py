"""流式聊天计时测试 - 收集 3 次请求数据。"""
import time
import httpx
import json

def test_stream_once(client, req_num):
    """单次流式测试。"""
    body = {"message": "hi", "agent_id": "default"}
    t0 = time.monotonic()
    first_event_time = None
    first_content_time = None
    done_time = None
    event_count = 0
    with client.stream("POST", "http://localhost:8001/api/chat/stream", json=body, timeout=60.0) as resp:
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
                        print(f"  REQ{req_num} 首内容: {int(first_content_time*1000)}ms")
                    elif data.get("type") == "session":
                        print(f"  REQ{req_num} Session: {int((t1-t0)*1000)}ms")
                    elif data.get("type") == "done":
                        done_time = t1 - t0
                        print(f"  REQ{req_num} Done: {int(done_time*1000)}ms")
                except json.JSONDecodeError:
                    pass
    total_time = time.monotonic() - t0
    print(f"  REQ{req_num} 总时间: {int(total_time*1000)}ms, 事件数: {event_count}")
    return first_event_time, first_content_time, done_time, total_time

# 预热
print("预热...")
with httpx.Client(timeout=30.0, trust_env=False) as client:
    client.post("http://localhost:8001/api/chat/stream", json={"message": "hi", "agent_id": "default"})
print("预热完成")

# 3 次测试
print("\n--- 流式计时测试 ---")
with httpx.Client(timeout=60.0, trust_env=False) as client:
    for i in range(3):
        print(f"\nREQ{i+1}:")
        test_stream_once(client, i+1)

print("\n测试完成。请查看后端日志 c:\CXHMS\logs\app.log 中最新的 [STREAM_TIMING] 行。")
