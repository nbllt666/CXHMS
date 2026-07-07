import httpx
import json

url = "http://localhost:8002/v1/chat/completions"
body = {
    "model": "gemma4-e4b",
    "messages": [
        {"role": "user", "content": "现在几点？用 datetime 工具告诉我当前时间，格式 YYYY-MM-DD HH:mm:ss"}
    ],
    "stream": True,
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "datetime",
                "description": "获取当前日期时间",
                "parameters": {
                    "type": "object",
                    "properties": {"format": {"type": "string", "description": "时间格式"}},
                    "required": ["format"],
                },
            },
        }
    ],
    "tool_choice": "auto",
}

acc = {}
with httpx.Client(timeout=60) as c:
    with c.stream("POST", url, json=body) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                d = line[6:]
                if d == "[DONE]":
                    break
                try:
                    ch = json.loads(d)
                    delta = ch["choices"][0].get("delta", {})
                    tcs = delta.get("tool_calls")
                    if tcs:
                        for tc in tcs:
                            idx = tc.get("index", 0)
                            if idx not in acc:
                                acc[idx] = {"id": tc.get("id", ""), "name": "", "args": ""}
                            f = tc.get("function", {})
                            if f.get("name"):
                                acc[idx]["name"] += f["name"]
                            if f.get("arguments"):
                                acc[idx]["args"] += f["arguments"]
                except Exception as e:
                    print("err:", e)

print("完整拼接结果:")
for i in sorted(acc):
    entry = acc[i]
    print("  [{}] id={!r} name={!r} args={!r}".format(i, entry["id"], entry["name"], entry["args"]))
