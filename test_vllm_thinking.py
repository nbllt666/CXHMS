import json, urllib.request

body = json.dumps({
    "model": "gemma4-e4b",
    "messages": [{"role": "user", "content": "What is 2+2? Think step by step."}],
    "max_tokens": 600,
    "stream": False,
    "chat_template_kwargs": {"enable_thinking": True}
}).encode()

req = urllib.request.Request(
    "http://localhost:8002/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=40) as resp:
    data = json.loads(resp.read().decode())

content = data["choices"][0]["message"].get("content", "")
print("=== FULL CONTENT (repr) ===")
print(repr(content))
print()
print("=== 'final' positions ===", [i for i in range(len(content)) if content[i:i+6] == "final\n"])
print("=== 'thought' positions ===", [i for i in range(len(content)) if content[i:i+8] == "thought\n"])
