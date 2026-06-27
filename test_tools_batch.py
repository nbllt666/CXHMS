"""
批量测试非 ACP 工具：通过直接调用 stream_chat 函数避免命令行参数转义问题。
每个测试用例检查：工具调用被触发 + LLM 生成最终回复内容（非默认兜底）。
"""
import json
import urllib.request

URL = "http://127.0.0.1:8001/api/chat/stream"


def stream_chat(agent_id: str, message: str):
    payload = json.dumps({"agent_id": agent_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    content_parts, thinking_parts, tool_calls, tool_results = [], [], [], []
    with urllib.request.urlopen(req, timeout=180) as resp:
        buf = b""
        for chunk in iter(lambda: resp.read(1024), b""):
            buf += chunk
            while b"\n\n" in buf:
                raw, buf = buf.split(b"\n\n", 1)
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data: "):
                    continue
                try:
                    evt = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                if etype == "content":
                    content_parts.append(evt.get("content", ""))
                elif etype == "thinking":
                    thinking_parts.append(evt.get("content", ""))
                elif etype == "tool_call":
                    tc = evt.get("tool_call", {})
                    fn = tc.get("function", {}).get("name") or tc.get("name", "")
                    args = tc.get("function", {}).get("arguments") or tc.get("arguments")
                    tool_calls.append({"name": fn, "arguments": args})
                elif etype == "tool_result":
                    tool_results.append({"name": evt.get("tool_name"), "result": evt.get("result")})
    return {
        "content": "".join(content_parts),
        "thinking": "".join(thinking_parts),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
    }


# 测试用例: (用例名, agent_id, 消息, 期望触发的工具名集合)
TEST_CASES = [
    # === builtin 工具 ===
    ("json_format", "default", '请把这个 JSON 格式化: {"name":"cxhms","version":1}', {"json_format"}),
    ("datetime", "default", "现在几点了", {"datetime"}),
    ("calculator", "default", "帮我计算 1234 * 56 + 789 等于多少", {"calculator"}),
    ("random", "default", "帮我生成一个 1 到 100 之间的随机数", {"random"}),
    # === master 工具 ===
    ("write_long_term_memory", "default", "请记住我的名字是小明，今年25岁，是一名软件工程师", {"write_long_term_memory"}),
    ("search_all_memories", "default", "你之前知道我叫什么名字吗？请搜索一下记忆", {"search_all_memories"}),
    ("set_alarm", "default", "请 5 秒后提醒我喝水", {"set_alarm"}),
    ("write_permanent_memory", "default", "请永久保存这条信息：用户偏好使用深色主题", {"write_permanent_memory"}),
    ("mono", "default", "请记住这个重要信息：项目截止日期是下周五", {"mono"}),
    # === memory agent 工具（通过 memory-agent 触发） ===
    ("memory_agent_search", "memory-agent", "请搜索所有包含'小明'的记忆", {"search_memories"}),
    ("memory_agent_stats", "memory-agent", "请告诉我记忆库的统计信息", {"get_memory_stats"}),
]


def main():
    results = []
    for name, agent_id, message, expected_tools in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"测试: {name} (agent={agent_id})")
        print(f"消息: {message}")
        print(f"期望工具: {expected_tools}")
        print("=" * 60)
        try:
            r = stream_chat(agent_id, message)
        except Exception as e:
            print(f"  ✗ 调用失败: {e}")
            results.append((name, False, f"调用异常: {e}"))
            continue

        triggered = {tc["name"] for tc in r["tool_calls"]}
        has_content = len(r["content"]) > 0
        is_fallback = r["content"] == "已完成工具调用。"
        has_tool_result = len(r["tool_results"]) > 0

        print(f"触发工具: {triggered}")
        print(f"工具结果数: {len(r['tool_results'])}")
        print(f"思考内容长度: {len(r['thinking'])}")
        print(f"回复内容长度: {len(r['content'])}")
        print(f"回复内容: {r['content'][:200]}")

        checks = [
            ("触发期望工具", bool(triggered & expected_tools) or (triggered and expected_tools)),
            ("工具结果已返回", has_tool_result),
            ("LLM 生成最终回复", has_content),
            ("非默认兜底文案", not is_fallback),
        ]
        all_pass = True
        for label, ok in checks:
            mark = "✓" if ok else "✗"
            print(f"  {mark} {label}")
            if not ok:
                all_pass = False
        results.append((name, all_pass, "" if all_pass else "存在失败项"))

    # 汇总
    print(f"\n{'='*60}")
    print("汇总")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, note in results:
        print(f"  {'✓' if ok else '✗'} {name}: {note if note else '通过'}")
    print(f"\n通过率: {passed}/{total}")


if __name__ == "__main__":
    main()
