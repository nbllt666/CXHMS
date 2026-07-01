import json, urllib.request

body = json.dumps({
    "model": "gemma4-e4b",
    "messages": [{"role": "user", "content": "What is 2+2? Think step by step."}],
    "max_tokens": 300,
    "stream": False
}).encode()

req = urllib.request.Request(
    "http://localhost:8002/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode())

print("=== CHOICES[0].MESSAGE ===")
msg = data["choices"][0]["message"]
print(json.dumps(msg, indent=2, ensure_ascii=False))
print()
print("=== KEYS ===", list(msg.keys()))
print("=== HAS reasoning_content ===", "reasoning_content" in msg)
print("=== HAS reasoning ===", "reasoning" in msg)
