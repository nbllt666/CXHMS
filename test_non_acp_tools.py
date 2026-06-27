"""
非 ACP 工具调用完整性测试脚本
测试所有非 ACP 工具能否被正确调用并返回结果

排除的 ACP 工具:
    acp_list_agents, acp_connect, acp_disconnect, acp_send_message,
    acp_create_group, acp_join_group, acp_leave_group
"""
import sys
import json
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Tuple

# 每个工具调用的超时时间（秒）
TOOL_TIMEOUT = 15

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# ACP 工具排除列表
ACP_TOOLS = {
    "acp_list_agents",
    "acp_connect",
    "acp_disconnect",
    "acp_send_message",
    "acp_create_group",
    "acp_join_group",
    "acp_leave_group",
}


# ---------------------------------------------------------------------------
# 步骤 1: 初始化工具注册表
# ---------------------------------------------------------------------------
def setup_tools() -> List[Tuple[str, bool, str]]:
    """初始化工具注册表，返回 (注册函数名, 是否成功, 消息) 列表"""
    registration_results: List[Tuple[str, bool, str]] = []

    # 1. 注册主模型工具
    try:
        from backend.core.tools.master_tools import register_master_tools

        register_master_tools()
        registration_results.append(("register_master_tools", True, "成功"))
    except Exception as e:
        registration_results.append(("register_master_tools", False, str(e)))

    # 2. 注册记忆工具 (memory_tools.py 存在语法错误，预期会失败)
    try:
        from backend.core.tools.memory_tools import register_memory_tools

        register_memory_tools()
        registration_results.append(("register_memory_tools", True, "成功"))
    except Exception as e:
        registration_results.append(("register_memory_tools", False, str(e)))

    # 3. 注册图工具
    try:
        from backend.core.tools.graph_tools import register_graph_tools

        count = register_graph_tools()
        registration_results.append(
            ("register_graph_tools", True, f"成功, 注册了 {count} 个工具")
        )

        # 图工具的 _get_store() 会尝试通过 backend.dependencies 创建图存储实例，
        # 可能连接数据库导致挂起。此处将其替换为直接返回 None，使所有图工具
        # 返回 "图存储未初始化" 错误，验证工具可被调用即可。
        from backend.core.tools import graph_tools as _gt

        _gt._get_store = lambda: None
    except Exception as e:
        registration_results.append(("register_graph_tools", False, str(e)))

    # 4. 注册助手工具
    try:
        from backend.core.tools.assistant_tools import register_assistant_tools

        register_assistant_tools()
        registration_results.append(("register_assistant_tools", True, "成功"))
    except Exception as e:
        registration_results.append(("register_assistant_tools", False, str(e)))

    # 5. 注册摘要工具
    try:
        from backend.core.tools.summary_tools import register_summary_tools

        register_summary_tools()
        registration_results.append(("register_summary_tools", True, "成功"))
    except Exception as e:
        registration_results.append(("register_summary_tools", False, str(e)))

    return registration_results


# ---------------------------------------------------------------------------
# 步骤 2: 准备测试用例
# ---------------------------------------------------------------------------
def get_builtin_test_cases() -> Dict[str, Dict[str, Any]]:
    """返回内置工具的测试用例（内置工具不通过注册表，直接调用）"""
    return {
        "calculator": {"expression": "2 + 3 * 4"},
        "datetime": {},
        "random": {"min": 1, "max": 100},
        "json_format": {"json_string": '{"name":"test","value":123}'},
    }


def _build_graph_test_cases() -> Dict[str, Dict[str, Any]]:
    """为 4 种图类型 × 14 种操作生成测试参数"""
    op_params = {
        "create_entity": {
            "name": "测试实体",
            "entity_type": "person",
            "properties": {"note": "测试"},
        },
        "create_relation": {
            "from_entity": "entity1_id",
            "to_entity": "entity2_id",
            "relation_type": "knows",
            "strength": 0.8,
        },
        "query_entities": {"entity_name_or_id": "测试实体", "depth": 1},
        "find_paths": {
            "from_entity": "entity1_id",
            "to_entity": "entity2_id",
            "max_depth": 3,
        },
        "search_related_memories": {
            "entity_name": "测试实体",
            "memory_query": "测试查询",
            "limit": 5,
        },
        "extract_entities": {"content": "张三和李四在讨论项目方案"},
        "merge_entities": {"entity1_id": "id1", "entity2_id": "id2"},
        "get_entity_summary": {"entity_name_or_id": "测试实体"},
        "update_entity": {"entity_id": "test_id", "properties": {"key": "value"}},
        "delete_entity": {"entity_id": "test_id"},
        "update_relation": {
            "from_entity": "e1",
            "to_entity": "e2",
            "relation_type": "knows",
            "strength": 0.5,
        },
        "delete_relation": {
            "from_entity": "e1",
            "to_entity": "e2",
            "relation_type": "knows",
        },
        "get_stats": {},
        "export": {"format": "json"},
    }

    cases: Dict[str, Dict[str, Any]] = {}
    for prefix in ("user", "thing", "concept", "event"):
        for op, params in op_params.items():
            cases[f"{prefix}_graph_{op}"] = params
    return cases


def get_registered_test_cases() -> Dict[str, Dict[str, Any]]:
    """返回所有注册工具的测试用例（不含 ACP 工具和内置工具）"""
    cases: Dict[str, Dict[str, Any]] = {}

    # --- 主模型工具 ---
    cases.update(
        {
            "write_long_term_memory": {
                "content": "测试记忆内容",
                "importance": 3,
            },
            "search_all_memories": {"query": "测试", "limit": 5},
            "call_assistant": {"message": "测试调用助手"},
            "set_alarm": {"seconds": 60, "message": "测试提醒"},
            "get_alarms": {},
            "cancel_alarm": {"alarm_id": "nonexistent_test_id"},
            "mono": {"content": "测试上下文保持"},
            "write_permanent_memory": {"content": "测试永久记忆"},
        }
    )

    # --- 图工具 (56 个) ---
    cases.update(_build_graph_test_cases())

    # --- 助手工具 ---
    cases.update(
        {
            "update_memory_node": {
                "memory_id": "99999",
                "new_content": "测试更新内容",
            },
            "search_memories": {"query": "测试", "limit": 5},
            "delete_memory": {"memory_id": "99999", "reason": "测试删除"},
            "merge_memories": {
                "memory_ids": ["99998", "99999"],
                "merged_content": "测试合并内容",
            },
            "clean_expired": {},
            "export_memories": {"format": "json"},
            "get_memory_stats": {},
            "search_by_time": {
                "start_time": "2024-01-01T00:00:00",
                "end_time": "2024-12-31T23:59:59",
            },
            "search_by_tag": {"tags": ["测试"]},
            "bulk_delete": {
                "memory_ids": ["99998", "99999"],
                "reason": "测试批量删除",
            },
            "restore_memory": {"memory_id": "99999"},
            "search_similar_memories": {"memory_id": "99999"},
            "get_chat_history": {"session_id": "test_session"},
            "get_similar_memories": {"content": "测试内容", "limit": 5},
            "get_memory_logs": {},
            "get_available_commands": {},
        }
    )

    # --- 摘要工具 ---
    cases.update(
        {
            "summarize_content": {
                "content": "这是一段需要摘要的测试内容，用于验证摘要工具能否被正确调用。"
            },
            "save_summary_memory": {
                "content": "测试摘要记忆",
                "importance": 5,
                "timestamp": "202606271200",
            },
            "get_session_messages": {"session_id": "test_session"},
            "clear_summary_context": {"session_id": "test_session"},
            "save_diary_entry": {
                "date": "2026-06-27",
                "title": "测试日记",
                "mood": "平静",
                "body": "这是一篇测试日记内容，用于验证日记保存工具。",
                "summarized_message_range": "0-5",
            },
        }
    )

    # --- 记忆工具 (memory_tools.py 有语法错误，save_memory 预期无法注册) ---
    cases.update(
        {
            "save_memory": {"content": "测试记忆"},
        }
    )

    # 过滤掉 ACP 工具
    return {k: v for k, v in cases.items() if k not in ACP_TOOLS}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _summarize_result(result: Any, max_len: int = 200) -> str:
    """生成结果摘要字符串"""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text
    except Exception:
        return str(result)[:max_len]


def _call_with_timeout(func, *args, timeout: float = TOOL_TIMEOUT, **kwargs):
    """在独立线程中调用 func，超时返回异常。超时后不等待线程结束。"""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutExpired:
        return {"success": False, "error": f"调用超时 (>{timeout}s)"}
    except Exception as e:
        return {"success": False, "error": f"异常: {type(e).__name__}: {e}"}
    finally:
        executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# 步骤 3: 运行测试
# ---------------------------------------------------------------------------
def run_tests() -> bool:
    """运行所有测试，返回是否全部通过"""
    print("=" * 90)
    print("非 ACP 工具调用完整性测试")
    print("=" * 90)

    # --- 注册工具 ---
    print("\n【步骤 1】注册工具\n")
    registration_results = setup_tools()
    for name, success, msg in registration_results:
        mark = "[OK]" if success else "[FAIL]"
        print(f"  {mark} {name}: {msg}")

    # --- 测试内置工具 ---
    print("\n【步骤 2】测试内置工具 (builtin)\n")
    builtin_cases = get_builtin_test_cases()
    builtin_results: List[Tuple[str, Dict, bool, str, str]] = []

    try:
        from backend.core.tools.builtin import call_builtin_tool
    except Exception as e:
        call_builtin_tool = None  # type: ignore
        print(f"  [ERROR] 无法导入 call_builtin_tool: {e}\n")

    if call_builtin_tool:
        for tool_name, params in builtin_cases.items():
            print(f"  --- {tool_name} ---")
            print(f"    参数: {json.dumps(params, ensure_ascii=False)}")
            try:
                result = _call_with_timeout(
                    call_builtin_tool, tool_name, params
                )
                if isinstance(result, dict) and "error" in result and "success" not in result:
                    # _call_with_timeout 捕获的异常/超时
                    status = "调用失败"
                    summary = result["error"]
                    builtin_results.append(
                        (tool_name, params, False, status, summary)
                    )
                    print(f"    结果: {status}")
                    print(f"    错误: {summary}")
                elif isinstance(result, dict):
                    inner_ok = result.get("success", False)
                    if inner_ok:
                        status = "调用成功 (执行成功)"
                    else:
                        status = "调用成功 (执行返回错误)"
                    summary = _summarize_result(result)
                    builtin_results.append(
                        (tool_name, params, True, status, summary)
                    )
                    print(f"    结果: {status}")
                    print(f"    摘要: {summary}")
                else:
                    status = "调用成功 (返回类型异常)"
                    summary = str(result)
                    builtin_results.append(
                        (tool_name, params, True, status, summary)
                    )
                    print(f"    结果: {status}")
            except Exception as e:
                error_msg = f"异常: {type(e).__name__}: {e}"
                builtin_results.append(
                    (tool_name, params, False, "调用失败", error_msg)
                )
                print(f"    结果: 调用失败")
                print(f"    错误: {error_msg}")
            print()

    # --- 测试注册的工具 ---
    print("\n【步骤 3】测试注册的工具 (master / graph / assistant / summary / memory)\n")
    from backend.core.tools.registry import tool_registry

    registered_cases = get_registered_test_cases()

    # 获取所有已注册工具名
    all_registered = {
        t.name for t in tool_registry.list_tools(enabled_only=False, include_builtin=True)
    }

    registered_results: List[Tuple[str, Dict, bool, str, str]] = []

    for tool_name, params in registered_cases.items():
        print(f"  --- {tool_name} ---")
        print(f"    参数: {json.dumps(params, ensure_ascii=False)}")

        if tool_name not in all_registered:
            status = "未注册"
            print(f"    结果: {status}")
            registered_results.append(
                (tool_name, params, False, status, "工具未注册")
            )
            print()
            continue

        try:
            result = _call_with_timeout(
                tool_registry.call_tool, tool_name, params
            )
            success = result.get("success", False)
            if success:
                inner_result = result.get("result", {})
                if isinstance(inner_result, dict) and "error" in inner_result:
                    status = "调用成功 (依赖错误)"
                else:
                    status = "调用成功 (执行成功)"
                summary = _summarize_result(inner_result)
            else:
                status = "调用失败"
                summary = result.get("error", "未知错误")

            print(f"    结果: {status}")
            print(f"    摘要: {summary}")
            registered_results.append(
                (tool_name, params, success, status, summary)
            )
        except Exception as e:
            error_msg = f"异常: {type(e).__name__}: {e}"
            print(f"    结果: 调用失败")
            print(f"    错误: {error_msg}")
            registered_results.append(
                (tool_name, params, False, "调用失败", error_msg)
            )
        print()

    # --- 检查是否有已注册但未测试的工具 ---
    builtin_names = set(builtin_cases.keys())
    tested_names = set(registered_cases.keys()) | builtin_names
    untested_registered = sorted(
        name for name in all_registered
        if name not in ACP_TOOLS and name not in tested_names
    )

    # --- 汇总报告 ---
    print("\n" + "=" * 90)
    print("测试报告汇总")
    print("=" * 90)

    all_results = builtin_results + registered_results

    # 表格输出
    print(f"\n{'#':>3}  {'工具名称':<40} {'调用状态':<28} {'结果摘要'}")
    print("-" * 120)
    for idx, (name, _params, success, status, summary) in enumerate(all_results, 1):
        mark = "[OK]" if success else "[FAIL]"
        short_summary = summary[:60] + "..." if len(summary) > 60 else summary
        print(f"{idx:>3}  {mark} {name:<35} {status:<28} {short_summary}")

    # 统计
    total = len(all_results)
    passed = sum(1 for _, _, success, _, _ in all_results if success)
    failed = total - passed

    print(f"\n{'=' * 90}")
    print("统计信息:")
    print(f"  测试工具总数: {total}")
    print(f"    内置工具:   {len(builtin_results)}")
    print(f"    注册工具:   {len(registered_results)}")
    print(f"  调用成功:     {passed}")
    print(f"  调用失败:     {failed}")
    if total > 0:
        print(f"  成功率:       {passed / total * 100:.1f}%")

    if untested_registered:
        print(f"\n  注意: 以下 {len(untested_registered)} 个已注册非 ACP 工具未在测试用例中覆盖:")
        for name in untested_registered:
            print(f"    - {name}")

    print(f"\n{'=' * 90}")
    return failed == 0


if __name__ == "__main__":
    all_passed = run_tests()
    sys.exit(0 if all_passed else 1)
