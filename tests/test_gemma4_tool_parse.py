"""测试 gemma4 工具调用解析修复"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置环境变量，确保使用真实 vLLM
os.environ.pop("CXHMS_SIMULATION", None)

from backend.core.llm.client import VLLMClient
from backend.core.chat.stream import generate_chat_stream, ChatStreamState


async def test_parse_gemma4_tool_call():
    """测试 _parse_gemma4_tool_call 修复"""
    client = VLLMClient(host="http://localhost:8002", model="gemma4-e4b")

    test_cases = [
        # 简单表达式
        ('<|tool_call>call:calculator{expression:<|"|>25 * 15<|"|>}<tool_call|>', "calculator"),
        # 日期时间格式（之前会破坏的正则）
        ('<|tool_call>call:datetime{format:<|"|>YYYY-MM-DD HH:mm:ss<|"|>}<tool_call|>', "datetime"),
        # 多参数
        ('<|tool_call>call:datetime{format:<|"|>YYYY-MM-DD HH:mm:ss<|"|>,timezone:<|"|>Asia/Shanghai<|"|>}<tool_call|>', "datetime"),
        # 无参数工具
        ('<|tool_call>call:search_all_memories{}<tool_call|>', "search_all_memories"),
    ]

    print("=" * 70)
    print("测试 _parse_gemma4_tool_call 修复")
    print("=" * 70)

    all_passed = True
    for text, expected_name in test_cases:
        result = client._parse_gemma4_tool_call(text)
        if result is None:
            print(f"[FAIL] {expected_name}: 返回 None")
            all_passed = False
            continue

        name = result["function"]["name"]
        args = result["function"]["arguments"]

        # 验证 name
        if name != expected_name:
            print(f"[FAIL] {expected_name}: name={name}")
            all_passed = False
            continue

        # 验证 args 是合法 JSON
        import json
        try:
            parsed = json.loads(args)
            print(f"[PASS] {name}: args={parsed}")
        except json.JSONDecodeError as e:
            print(f"[FAIL] {name}: args 不是合法 JSON: {args}, 错误: {e}")
            all_passed = False

    return all_passed


async def test_real_tool_call():
    """测试真实 vLLM 工具调用流程（多轮）"""
    print()
    print("=" * 70)
    print("测试真实 vLLM 多轮工具调用")
    print("=" * 70)

    client = VLLMClient(host="http://localhost:8002", model="gemma4-e4b")

    # 简单工具列表
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "数学计算器",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式",
                        }
                    },
                    "required": ["expression"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "datetime",
                "description": "获取当前日期时间",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "日期格式，如 YYYY-MM-DD HH:mm:ss",
                        }
                    },
                },
            },
        },
    ]

    messages = [
        {"role": "system", "content": "你是一个助手，可以调用工具。"},
        {"role": "user", "content": "请用 datetime 工具获取当前时间，格式 YYYY-MM-DD HH:mm:ss"},
    ]

    state = ChatStreamState()

    print("\n--- 调用 generate_chat_stream ---")
    round_count = 0
    async for event in generate_chat_stream(
        llm=client,
        messages=messages,
        agent_config={"temperature": 0.7, "max_tokens": 1024},
        tools=tools,
        session_id="test-session",
        state=state,
    ):
        event_type = event.get("type")
        if event_type == "content":
            print(f"[CONTENT] {event.get('content', '')[:100]}")
        elif event_type == "thinking":
            print(f"[THINKING] {event.get('content', '')[:80]}")
        elif event_type == "tool_call":
            tc = event.get("tool_call", {})
            print(f"[TOOL_CALL] name={tc.get('function', {}).get('name')}, args={tc.get('function', {}).get('arguments')}")
        elif event_type == "tool_start":
            print(f"[TOOL_START] {event.get('tool_name')}")
        elif event_type == "tool_result":
            print(f"[TOOL_RESULT] {event.get('tool_name')}: {str(event.get('result'))[:100]}")
        elif event_type == "done":
            print(f"[DONE] session={event.get('session_id')}")
        elif event_type == "error":
            print(f"[ERROR] {event.get('error')}")
        elif event_type == "cancelled":
            print(f"[CANCELLED]")
        else:
            print(f"[{event_type}] {event}")

        round_count += 1
        if round_count > 100:
            print("[BREAK] 事件过多，中断")
            break

    print()
    print(f"--- 最终状态 ---")
    print(f"accumulated_response: {state.accumulated_response[:200]}")
    print(f"tool_calls 数量: {len(state.tool_calls)}")
    for tc in state.tool_calls:
        print(f"  - {tc.get('name')}: args={tc.get('arguments')}, result={str(tc.get('result'))[:80]}")

    return len(state.tool_calls) > 0


async def main():
    parse_ok = await test_parse_gemma4_tool_call()

    if not parse_ok:
        print("\n[ABORT] 解析测试失败，不进行真实调用测试")
        return

    real_ok = await test_real_tool_call()

    print()
    print("=" * 70)
    print(f"测试结果: 解析={'PASS' if parse_ok else 'FAIL'}, 真实调用={'PASS' if real_ok else 'FAIL'}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
