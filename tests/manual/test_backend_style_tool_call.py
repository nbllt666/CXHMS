"""
直接测试 vLLM，模拟后端的消息结构（3 个 system prompt + 历史消息 + tools）
用于复现"模型生成回复后无法工具调用"的失败场景。

测试目标：
1. 简单 2 消息场景（baseline，应成功）
2. 后端风格多 system 场景（3 system + history + user）
3. 流式模式
"""
import json
import sys
import time
from pathlib import Path

import httpx

VLLM_URL = "http://localhost:8002/v1/chat/completions"
MODEL = "gemma4-e4b"

# 后端实际的 system prompts（简化版）
MAIN_HIDDEN_SYSTEM_PROMPT = """<role>
你是 CXHMS 智能助手系统的核心模型。你的职责是理解用户需求并提供准确、有帮助的回复。
</role>

<instruction>
你可以使用系统提供的工具来帮助用户。工具已通过 API 自动注册，你无需在回复中描述或列举工具。
当需要执行操作时，必须通过 function calling 机制调用工具，不要在文本中输出工具调用标记（如 <execute_tool>）。
直接调用对应的函数即可，系统会自动执行并返回结果。
</instruction>

<rules>
1. 用中文回答用户问题
2. 当用户分享个人信息时，主动使用 write_long_term_memory 保存
3. 当用户询问之前聊过的内容时，使用 search_all_memories 搜索
4. 当需要设置提醒时，使用 set_alarm，注意 seconds 参数单位是秒
5. 当记忆管理任务较复杂时，使用 call_assistant 委托给记忆管理模型
6. 不要编造不存在的工具或功能
7. 绝对不要在回复文本中输出 <execute_tool> 或类似标记，必须通过 function calling 调用工具
</rules>"""

AGENT_SYSTEM_PROMPT = """你是 CXHMS 主助手。你正在与用户进行多轮对话。
你可以使用工具来帮助用户管理记忆、搜索信息、设置提醒等。
请根据用户需求选择合适的工具，或直接回复。
当前时间：2026-07-06 22:30"""

MEMORY_CONTEXT = """相关记忆:
- 用户名是小明
- 用户喜欢编程和阅读
- 用户是一名软件工程师
- 用户住在上海"""

# 简化的工具定义
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_all_memories",
            "description": "搜索用户的记忆库。当用户询问之前聊过的内容、过往的记录时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"},
                    "limit": {"type": "integer", "description": "返回结果数量", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_long_term_memory",
            "description": "将信息保存到长期记忆库。当用户分享个人信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要保存的内容"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "设置提醒闹钟。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "提醒标题"},
                    "seconds": {"type": "integer", "description": "提醒时间（秒）"},
                },
                "required": ["title", "seconds"],
            },
        },
    },
]


def test_non_streaming(name: str, messages: list, tools: list = None, tool_choice="auto"):
    """非流式测试"""
    print(f"\n===== {name} =====")
    body = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": 1024,
        "temperature": 0.7,
        "tool_choice": tool_choice,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    if tools:
        body["tools"] = tools

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            resp = client.post(VLLM_URL, json=body)
            elapsed = (time.monotonic() - t0) * 1000
            if resp.status_code != 200:
                print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
                return
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            tool_calls = msg.get("tool_calls", [])
            finish = choice.get("finish_reason")

            print(f"  耗时: {elapsed:.0f}ms, finish={finish}")
            print(f"  content({len(content)}): {repr(content[:200])}")
            print(f"  reasoning({len(reasoning)}): {repr(reasoning[:200])}")
            print(f"  tool_calls: {len(tool_calls)}")
            for tc in tool_calls:
                fn = tc.get("function", {})
                print(f"    -> {fn.get('name')}: {fn.get('arguments', '')[:100]}")
    except Exception as e:
        print(f"  异常: {e}")


def test_streaming(name: str, messages: list, tools: list = None, tool_choice="auto"):
    """流式测试"""
    print(f"\n===== {name} (流式) =====")
    body = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.7,
        "tool_choice": tool_choice,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    if tools:
        body["tools"] = tools

    t0 = time.monotonic()
    content_buf = []
    reasoning_buf = []
    tool_call_chunks = 0
    finish_reason = None
    raw_special_chunks = []  # 含 <| 或 tool_call 的原始 delta

    try:
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            with client.stream("POST", VLLM_URL, json=body) as resp:
                if resp.status_code != 200:
                    print(f"  HTTP {resp.status_code}: {resp.read()[:300]}")
                    return
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
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

                        # 检测特殊 token
                        delta_str = json.dumps(delta, ensure_ascii=False)
                        if ("<|" in delta_str or "tool_call" in delta_str or "channel" in delta_str) and len(raw_special_chunks) < 20:
                            raw_special_chunks.append(delta)

                        rc = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                        if rc and rc != "<pad>":
                            reasoning_buf.append(rc)
                        c = delta.get("content", "")
                        if c and c != "<pad>":
                            content_buf.append(c)
                        tc = delta.get("tool_calls")
                        if tc:
                            tool_call_chunks += 1
                    except json.JSONDecodeError:
                        continue

        elapsed = (time.monotonic() - t0) * 1000
        content_text = "".join(content_buf)
        reasoning_text = "".join(reasoning_buf)
        print(f"  耗时: {elapsed:.0f}ms, finish={finish_reason}")
        print(f"  content({len(content_text)}): {repr(content_text[:300])}")
        print(f"  reasoning({len(reasoning_text)}): {repr(reasoning_text[:300])}")
        print(f"  tool_call_chunks: {tool_call_chunks}")
        print(f"  含特殊 token 的 chunks: {len(raw_special_chunks)}")
        for i, d in enumerate(raw_special_chunks[:10]):
            print(f"    [{i}] {d}")
    except Exception as e:
        print(f"  异常: {e}")


# 测试 1：baseline 简单场景（应成功）
test_non_streaming(
    "测试1：简单场景（非流式）",
    messages=[
        {"role": "user", "content": "搜索我之前关于编程的记忆"},
    ],
    tools=TOOLS,
)

# 测试 1b：baseline 流式
test_streaming(
    "测试1b：简单场景（流式）",
    messages=[
        {"role": "user", "content": "搜索我之前关于编程的记忆"},
    ],
    tools=TOOLS,
)

# 测试 2：后端风格 - 3 system + memory + history + user（非流式）
backend_messages = [
    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    {"role": "system", "content": MAIN_HIDDEN_SYSTEM_PROMPT},
    {"role": "system", "content": MEMORY_CONTEXT},
    # 模拟历史消息
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！很高兴见到你。有什么我可以帮助你的吗？"},
    {"role": "user", "content": "我今天想搜索一些记忆"},
    {"role": "assistant", "content": "好的，我可以帮你搜索记忆。请告诉我你想搜索什么内容？"},
    {"role": "user", "content": "我想找之前关于 Python 的对话"},
    {"role": "assistant", "content": "好的，让我帮你搜索一下关于 Python 的记忆。"},
    {"role": "user", "content": "搜到了吗？"},
    {"role": "assistant", "content": "已为你搜索了相关记忆。还有什么需要帮助的吗？"},
    {"role": "user", "content": "我们之前聊过什么？"},
]
test_non_streaming(
    "测试2：后端风格 3 system + history（非流式）",
    messages=backend_messages,
    tools=TOOLS,
)

# 测试 2b：后端风格流式
test_streaming(
    "测试2b：后端风格 3 system + history（流式）",
    messages=backend_messages,
    tools=TOOLS,
)

# 测试 3：只保留 1 个 system prompt（去掉冗余）
test_streaming(
    "测试3：单 system prompt（流式）",
    messages=[
        {"role": "system", "content": MAIN_HIDDEN_SYSTEM_PROMPT},
        {"role": "user", "content": "我们之前聊过什么？"},
    ],
    tools=TOOLS,
)

# 测试 4：纯 user 消息 + tools（无 system）
test_streaming(
    "测试4：无 system（流式）",
    messages=[
        {"role": "user", "content": "我们之前聊过什么？"},
    ],
    tools=TOOLS,
)

# 测试 5：tool_choice=required 强制工具调用
test_streaming(
    "测试5：tool_choice=required（流式）",
    messages=backend_messages,
    tools=TOOLS,
    tool_choice="required",
)

print("\n===== 测试完成 =====")
