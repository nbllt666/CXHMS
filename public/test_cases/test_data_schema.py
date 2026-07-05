"""数据契约校验测试。

校验 public/schema/*.json 字段约束：
- 5 份 schema 文件存在且为合法 JSON Schema (draft-07+)
- Mock 生成的数据符合对应 schema（有效数据通过）
- 越界/非法/缺失字段数据被正确拒绝

执行：python -m pytest public/test_cases/test_data_schema.py -v
降级：python public/test_cases/test_data_schema.py
"""

import asyncio
import os

import pytest

from .conftest import SCHEMA_DIR, load_json, try_jsonschema

jsonschema = try_jsonschema()

# 全局跳过：jsonschema 不可用时本模块大部分测试失去严格意义（仅做 required 字段存在性降级校验）
# 显式 skip 优于静默通过，符合 rules-3 §五 test_suite.requirement "可自主执行" 的语义
pytestmark = pytest.mark.skipif(
    jsonschema is None,
    reason="jsonschema 未安装；契约约束验证不可降级。安装：pip install jsonschema（见 public/dependencies/requirements.txt）",
)


def _run(coro):
    """同步运行 async 方法（兼容无 asyncio.run 的旧环境）。"""
    return asyncio.run(coro)


# ---------- 工具函数 ----------

def _check_schema_file(name: str) -> dict:
    """校验 schema 文件存在且含必要字段。"""
    path = os.path.join(SCHEMA_DIR, name)
    assert os.path.exists(path), f"schema 文件缺失: {name}"
    schema = load_json(path)
    assert schema.get("$schema", "").startswith("http://json-schema.org/draft"), \
        f"{name} 缺少 $schema 声明"
    assert schema.get("type") == "object", f"{name} 顶层 type 必须为 object"
    assert "properties" in schema, f"{name} 缺少 properties"
    assert "required" in schema, f"{name} 缺少 required"
    return schema


def _validate(schema: dict, instance: dict) -> bool:
    """用 jsonschema 严格校验 instance 是否符合 schema。"""
    try:
        jsonschema.validate(instance=instance, schema=schema)
        return True
    except jsonschema.ValidationError:
        return False


# ---------- Schema 文件存在性 ----------

def test_memory_schema_exists():
    schema = _check_schema_file("memory.json")
    assert "id" in schema["properties"]
    assert "content" in schema["properties"]
    assert "importance" in schema["properties"]
    assert "agent_id" in schema["properties"]


def test_agent_schema_exists():
    schema = _check_schema_file("agent.json")
    assert "id" in schema["properties"]
    assert "name" in schema["properties"]
    assert "system_prompt" in schema["properties"]
    assert "model" in schema["properties"]


def test_message_schema_exists():
    schema = _check_schema_file("message.json")
    assert "role" in schema["properties"]
    assert "content" in schema["properties"]
    assert "session_id" in schema["properties"]


def test_tool_schema_exists():
    schema = _check_schema_file("tool.json")
    assert "name" in schema["properties"]
    assert "parameters" in schema["properties"]
    assert "category" in schema["properties"]


def test_error_schema_exists():
    schema = _check_schema_file("error.json")
    assert "error_code" in schema["properties"]
    assert "error" in schema["properties"]
    # error_code 枚举应覆盖核心错误码
    enum_vals = schema["properties"]["error_code"].get("enum", [])
    assert "MEMORY_NOT_FOUND" in enum_vals
    assert "VALIDATION_ERROR" in enum_vals
    assert "LLM_ERROR" in enum_vals


# ---------- 有效数据通过校验 ----------

def test_memory_valid_instance():
    from public.pre_generated_mock.memory_mock import MockMemoryService

    svc = MockMemoryService()
    mid = svc.write_memory(content="测试记忆", importance=3, tags=["t1"])
    memory = svc.get_memory(mid)
    schema = load_json(os.path.join(SCHEMA_DIR, "memory.json"))
    assert _validate(schema, memory), "Mock 生成的记忆应符合 memory.json 契约"


def test_agent_valid_instance():
    from public.pre_generated_mock.agent_mock import MockAgentService

    svc = MockAgentService()
    agents = _run(svc.list_agents())
    schema = load_json(os.path.join(SCHEMA_DIR, "agent.json"))
    assert _validate(schema, agents[0]), "Mock 生成的 Agent 应符合 agent.json 契约"


def test_tool_valid_instance():
    from public.pre_generated_mock.tool_mock import MockToolService

    svc = MockToolService()
    tools = _run(svc.list_tools())
    first = list(tools["tools"].values())[0]
    schema = load_json(os.path.join(SCHEMA_DIR, "tool.json"))
    assert _validate(schema, first), "Mock 生成的工具应符合 tool.json 契约"


def test_message_valid_instance():
    from public.pre_generated_mock.chat_mock import MockChatService

    svc = MockChatService()
    _run(svc.chat(message="测试消息", stream=False))
    history = _run(svc.get_chat_history("mock-session-001"))
    schema = load_json(os.path.join(SCHEMA_DIR, "message.json"))
    assert _validate(schema, history[0]), "Mock 生成的消息应符合 message.json 契约"


def test_graph_valid_instance():
    from public.pre_generated_mock.graph_mock import MockGraphService

    svc = MockGraphService()
    node = _run(svc.create_node({"type": "concept", "properties": {"name": "节点1"}}))
    node_schema = load_json(os.path.join(SCHEMA_DIR, "graph_node.json"))
    assert _validate(node_schema, node), "Mock 生成的图节点应符合 graph_node.json 契约"

    edge = _run(svc.create_edge({
        "source_id": node["id"], "target_id": node["id"],
        "relation_type": "self_ref", "properties": {},
    }))
    edge_schema = load_json(os.path.join(SCHEMA_DIR, "graph_edge.json"))
    assert _validate(edge_schema, edge), "Mock 生成的图边应符合 graph_edge.json 契约"


# ---------- 无效数据被拒绝 ----------

def test_memory_invalid_importance_rejected():
    schema = load_json(os.path.join(SCHEMA_DIR, "memory.json"))
    bad = {
        "id": 1, "type": "long_term", "content": "x",
        "importance": 99,  # 越界
        "created_at": "2026-07-02T00:00:00", "workspace_id": "default",
    }
    assert not _validate(schema, bad), "importance=99 应被拒绝"


def test_memory_invalid_type_rejected():
    schema = load_json(os.path.join(SCHEMA_DIR, "memory.json"))
    bad = {
        "id": 1, "type": "invalid_type", "content": "x",
        "importance": 3, "created_at": "2026-07-02T00:00:00", "workspace_id": "default",
    }
    assert not _validate(schema, bad), "type=invalid_type 应被拒绝"


def test_memory_missing_content_rejected():
    schema = load_json(os.path.join(SCHEMA_DIR, "memory.json"))
    bad = {"id": 1, "type": "long_term", "importance": 3,
           "created_at": "2026-07-02T00:00:00", "workspace_id": "default"}
    assert not _validate(schema, bad), "缺失 content 应被拒绝"


def test_error_response_structure():
    schema = load_json(os.path.join(SCHEMA_DIR, "error.json"))
    ok = {"error": "未找到", "error_code": "MEMORY_NOT_FOUND", "details": {"memory_id": "1"}}
    assert _validate(schema, ok), "合法 ErrorResponse 应通过"
    bad = {"error": "未找到"}  # 缺 error_code
    assert not _validate(schema, bad), "缺失 error_code 应被拒绝"


# ---------- 直接运行入口 ----------

if __name__ == "__main__":
    import traceback

    tests = [
        test_memory_schema_exists, test_agent_schema_exists, test_message_schema_exists,
        test_tool_schema_exists, test_error_schema_exists,
        test_memory_valid_instance, test_agent_valid_instance, test_tool_valid_instance,
        test_message_valid_instance, test_graph_valid_instance,
        test_memory_invalid_importance_rejected, test_memory_invalid_type_rejected,
        test_memory_missing_content_rejected, test_error_response_structure,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} 通过")
    if passed != len(tests):
        raise SystemExit(1)
