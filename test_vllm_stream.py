import json, urllib.request

body = json.dumps({
    "model": "gemma4-e4b",
    "messages": [{"role": "user", "content": "What is 2+2? Think step by step."}],
    "max_tokens": 800,
    "stream": True,
    "chat_template_kwargs": {"enable_thinking": True}
}).encode()

req = urllib.request.Request(
    "http://localhost:8002/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST"
)
full_content = ""
with urllib.request.urlopen(req, timeout=60) as resp:
    for line in resp:
        line = line.decode().strip()
        if not line or not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        chunk = json.loads(data_str)
        delta = chunk["choices"][0].get("delta", {})
        content = delta.get("content", "")
        if content:
            full_content += content

print("=== FULL CONTENT ===")
print(full_content)
print()
print("=== 'final' found at ===", full_content.find("final"))
print("=== 'thought' found at ===", full_content.find("thought"))
print("=== last 200 chars ===")
print(repr(full_content[-200:]))
