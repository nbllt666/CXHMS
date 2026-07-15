"""AnythingLLM 兼容 API 契约校验测试。

校验 public/schema/anythingllm_workspace.json 和 openai_chat_completion.json：
- schema 文件存在且为合法 JSON Schema (draft-07+)
- 有效数据符合 schema
- 越界/非法/缺失字段数据被拒绝
- 接口存根 anythingllm_service.pyi 存在且包含 11 个函数签名

执行：python -m pytest public/test_cases/test_anythingllm_contract.py -v
降级：python public/test_cases/test_anythingllm_contract.py
"""

import os

import pytest

from .conftest import SCHEMA_DIR, STUB_DIR, load_json, try_jsonschema

jsonschema = try_jsonschema()

pytestmark = pytest.mark.skipif(
    jsonschema is None,
    reason="jsonschema 未安装；契约约束验证不可降级。安装：pip install jsonschema",
)


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
    jsonschema.validate(instance=instance, schema=schema)
    return True


def _validate_raises(schema: dict, instance: dict) -> bool:
    """断言 instance 不符合 schema。"""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=instance, schema=schema)
    return True


# ---------- anythingllm_workspace.json 契约校验 ----------

class TestAnythingLLMWorkspaceSchema:
    """workspace 数据契约校验。"""

    def test_schema_file_exists_and_valid(self):
        """schema 文件存在且为合法 JSON Schema。"""
        schema = _check_schema_file("anythingllm_workspace.json")
        assert schema["title"] == "AnythingLLMWorkspace"
        assert "id" in schema["properties"]
        assert "name" in schema["properties"]
        assert "slug" in schema["properties"]
        assert "createdAt" in schema["properties"]

    def test_valid_workspace_minimal(self):
        """有效 workspace（仅必填字段）通过校验。"""
        schema = _check_schema_file("anythingllm_workspace.json")
        workspace = {
            "id": "default",
            "name": "默认助手",
            "slug": "default",
            "createdAt": 1719500000000,
        }
        assert _validate(schema, workspace)

    def test_valid_workspace_full(self):
        """有效 workspace（含可选字段）通过校验。"""
        schema = _check_schema_file("anythingllm_workspace.json")
        workspace = {
            "id": "default",
            "name": "默认助手",
            "slug": "default",
            "createdAt": "2026-07-14T10:00:00",
            "settings": {
                "model": "main",
                "temperature": 0.7,
                "system_prompt": "你是一个有帮助的AI助手。",
            },
            "embedCount": 0,
        }
        assert _validate(schema, workspace)

    def test_missing_required_field_rejected(self):
        """缺失必填字段被拒绝。"""
        schema = _check_schema_file("anythingllm_workspace.json")
        # 缺 slug
        invalid = {"id": "default", "name": "默认助手", "createdAt": 1719500000000}
        assert _validate_raises(schema, invalid)

    def test_empty_name_rejected(self):
        """空 name 被拒绝（minLength: 1）。"""
        schema = _check_schema_file("anythingllm_workspace.json")
        invalid = {
            "id": "default",
            "name": "",
            "slug": "default",
            "createdAt": 1719500000000,
        }
        assert _validate_raises(schema, invalid)

    def test_negative_embedcount_rejected(self):
        """负 embedCount 被拒绝。"""
        schema = _check_schema_file("anythingllm_workspace.json")
        invalid = {
            "id": "default",
            "name": "默认助手",
            "slug": "default",
            "createdAt": 1719500000000,
            "embedCount": -1,
        }
        assert _validate_raises(schema, invalid)

    def test_temperature_out_of_range_rejected(self):
        """settings.temperature 超出 [0,2] 被拒绝。"""
        schema = _check_schema_file("anythingllm_workspace.json")
        invalid = {
            "id": "default",
            "name": "默认助手",
            "slug": "default",
            "createdAt": 1719500000000,
            "settings": {"temperature": 3.5},
        }
        assert _validate_raises(schema, invalid)


# ---------- openai_chat_completion.json 契约校验 ----------

class TestOpenAIChatCompletionSchema:
    """OpenAI ChatCompletion 响应契约校验。"""

    def test_schema_file_exists_and_valid(self):
        """schema 文件存在且为合法 JSON Schema。"""
        schema = _check_schema_file("openai_chat_completion.json")
        assert schema["title"] == "OpenAIChatCompletion"
        for field in ["id", "object", "created", "model", "choices", "usage"]:
            assert field in schema["properties"], f"缺少 {field}"

    def test_valid_completion(self):
        """有效 ChatCompletion 响应通过校验。"""
        schema = _check_schema_file("openai_chat_completion.json")
        completion = {
            "id": "chatcmpl-abc123",
            "object": "chat.completion",
            "created": 1719500000,
            "model": "main",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "你好！"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        assert _validate(schema, completion)

    def test_invalid_id_pattern_rejected(self):
        """id 不以 chatcmpl- 开头被拒绝。"""
        schema = _check_schema_file("openai_chat_completion.json")
        invalid = {
            "id": "wrong-prefix",
            "object": "chat.completion",
            "created": 1719500000,
            "model": "main",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "你好！"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        assert _validate_raises(schema, invalid)

    def test_invalid_object_value_rejected(self):
        """object 非 chat.completion 被拒绝。"""
        schema = _check_schema_file("openai_chat_completion.json")
        invalid = {
            "id": "chatcmpl-abc",
            "object": "text.completion",
            "created": 1719500000,
            "model": "main",
            "choices": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        assert _validate_raises(schema, invalid)

    def test_empty_choices_rejected(self):
        """choices 为空数组被拒绝（minItems: 1）。"""
        schema = _check_schema_file("openai_chat_completion.json")
        invalid = {
            "id": "chatcmpl-abc",
            "object": "chat.completion",
            "created": 1719500000,
            "model": "main",
            "choices": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        assert _validate_raises(schema, invalid)

    def test_missing_usage_rejected(self):
        """缺失 usage 被拒绝。"""
        schema = _check_schema_file("openai_chat_completion.json")
        invalid = {
            "id": "chatcmpl-abc",
            "object": "chat.completion",
            "created": 1719500000,
            "model": "main",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "你好！"},
                    "finish_reason": "stop",
                }
            ],
        }
        assert _validate_raises(schema, invalid)


# ---------- 接口存根校验 ----------

class TestAnythingLLMServiceStub:
    """anythingllm_service.pyi 接口存根校验。"""

    def test_stub_file_exists(self):
        """存根文件存在。"""
        path = os.path.join(STUB_DIR, "anythingllm_service.pyi")
        assert os.path.exists(path), "anythingllm_service.pyi 不存在"

    def test_stub_contains_11_signatures(self):
        """存根包含 11 个函数签名（verify_api_key + 11 端点方法）。

        注：verify_api_key 是认证依赖，不计入 11 端点。11 端点方法为：
        auth, list_models, chat_completions, list_workspaces, create_workspace,
        get_workspace, update_workspace, delete_workspace, workspace_chat,
        workspace_stream_chat, workspace_chats
        """
        path = os.path.join(STUB_DIR, "anythingllm_service.pyi")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 11 个端点方法名
        expected_methods = [
            "def auth(",
            "def list_models(",
            "def chat_completions(",
            "def list_workspaces(",
            "def create_workspace(",
            "def get_workspace(",
            "def update_workspace(",
            "def delete_workspace(",
            "def workspace_chat(",
            "def workspace_stream_chat(",
            "def workspace_chats(",
        ]
        for method in expected_methods:
            assert method in content, f"存根缺少方法签名: {method}"

    def test_stub_contains_verify_api_key(self):
        """存根包含 verify_api_key 认证依赖。"""
        path = os.path.join(STUB_DIR, "anythingllm_service.pyi")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "def verify_api_key(" in content, "存根缺少 verify_api_key"

    def test_stub_is_zero_implementation(self):
        """存根仅含签名，无实现逻辑（每个方法体为 ...）。"""
        path = os.path.join(STUB_DIR, "anythingllm_service.pyi")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # 不应含 return 语句（除 docstring 中的描述）
        import re
        # 检查所有 async def 后跟的是 ... 而非实际逻辑
        method_blocks = re.findall(r"async def \w+\([^)]*\)[^:]*:.*?(?=\n    async def|\nclass|\Z)", content, re.DOTALL)
        for block in method_blocks:
            # 方法体应仅含 docstring 和 ...
            assert "..." in block, f"方法块缺少 ... 标记:\n{block[:200]}"
