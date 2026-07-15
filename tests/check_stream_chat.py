"""直接验证 stream-chat 实际响应格式。"""
import requests

BASE = "http://localhost:8001/api/v1"

print("=== stream-chat 原始响应（不解析 SSE）===")
r = requests.post(
    f"{BASE}/workspace/default/stream-chat",
    json={"message": "回复两个字:你好", "mode": "chat"},
    stream=True,
    timeout=30,
)
print(f"status={r.status_code}")
print(f"content-type={r.headers.get('content-type')}")
chunks_raw = []
for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
    if chunk:
        chunks_raw.append(chunk)
        print(f"  chunk[{len(chunks_raw)-1}]={chunk!r}")
print(f"\n拼接结果: {''.join(chunks_raw)!r}")
print(f"共 {len(chunks_raw)} 个原始 chunk")
