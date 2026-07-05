"""数据契约校验测试（G4 批次 G-3）。

校验 public/schema/*.json 字段约束，对应 rules-3 §一 数据契约。

覆盖要求（spec tasks.md Task G4）：
    - 每个 schema 至少 1 个 positive + 2 个 negative 用例
    - 字段约束（required、type、enum、minimum/maximum、default）逐项断言

约束：
    - public/ 受保护，本测试只读不写
    - 不依赖 backend 实现，纯契约校验
    - 使用 jsonschema 库（已安装 4.26.0）做 draft-07 校验
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import jsonschema
import pytest

# --------------------------------------------------------------------------- #
# 路径锚点（rules-0 §三：用 os.path.dirname(os.path.abspath(__file__)) 解析）
# --------------------------------------------------------------------------- #
_PUBLIC_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "public" / "schema"

# 7 个核心数据契约（与 spec D6 [V] 一致）
_SCHEMA_NAMES: List[str] = [
    "memory",
    "agent",
    "message",
    "tool",
    "error",
    "graph_node",
    "graph_edge",
]


# --------------------------------------------------------------------------- #
# 公共 fixtures
# --------------------------------------------------------------------------- #


def _load_schema(name: str) -> Dict[str, Any]:
    """加载 schema 文件（受保护只读）。"""
    path = _PUBLIC_SCHEMA_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(params=_SCHEMA_NAMES)
def schema_name(request) -> str:
    """参数化 schema 名称（7 个）。"""
    return request.param


@pytest.fixture
def schema(schema_name) -> Dict[str, Any]:
    """加载对应 schema dict。"""
    return _load_schema(schema_name)


# --------------------------------------------------------------------------- #
# 通用契约结构断言（所有 schema 共有）
# --------------------------------------------------------------------------- #


class TestSchemaStructure:
    """每个 schema 必须满足的结构性约束（rules-3 §一 强制要求）。"""

    def test_schema_file_is_valid_json(self, schema_name):
        """schema 文件本身是合法 JSON。"""
        path = _PUBLIC_SCHEMA_DIR / f"{schema_name}.json"
        assert path.exists(), f"schema 文件不存在：{path}"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), f"{schema_name}.json 顶层非 object"

    def test_schema_is_valid_draft07(self, schema):
        """schema 本身是合法 JSON Schema draft-07。"""
        jsonschema.Draft7Validator.check_schema(schema)

    def test_schema_declares_draft07(self, schema, schema_name):
        """schema 显式声明 $schema 为 draft-07+。"""
        assert "$schema" in schema, f"{schema_name} 缺少 $schema 声明"
        assert "draft-07" in schema["$schema"], f"{schema_name} $schema 非 draft-07"

    def test_schema_has_id(self, schema, schema_name):
        """schema 含 $id 唯一标识（rules-3 §一 字段描述无歧义）。"""
        assert "$id" in schema, f"{schema_name} 缺少 $id"
        assert schema["$id"].startswith("https://"), (
            f"{schema_name} $id 必须为 https URL：{schema['$id']}"
        )

    def test_schema_has_title_and_description(self, schema, schema_name):
        """schema 含 title 与 description（rules-3 §一 字段描述无歧义）。"""
        assert "title" in schema and schema["title"], f"{schema_name} 缺少 title"
        assert "description" in schema and schema["description"], (
            f"{schema_name} 缺少 description"
        )

    def test_schema_has_required_array(self, schema, schema_name):
        """schema 显式声明 required 数组（rules-3 §一 必填性）。"""
        assert "required" in schema, f"{schema_name} 缺少 required"
        assert isinstance(schema["required"], list), f"{schema_name} required 非数组"
        assert len(schema["required"]) > 0, f"{schema_name} required 为空"

    def test_schema_disallows_additional_properties(self, schema, schema_name):
        """schema 显式 additionalProperties: false（rules-3 §一 防止字段漂移）。"""
        assert schema.get("additionalProperties") is False, (
            f"{schema_name} 必须声明 additionalProperties: false"
        )

    def test_schema_properties_have_description(self, schema, schema_name):
        """每个 property 含 description（rules-3 §一 字段描述无歧义）。"""
        props = schema.get("properties", {})
        for prop_name, prop_def in props.items():
            if isinstance(prop_def, dict):
                # 嵌套 $ref 的属性可能没有 description，跳过
                if "$ref" in prop_def:
                    continue
                assert "description" in prop_def, (
                    f"{schema_name}.{prop_name} 缺少 description"
                )

    def test_schema_required_fields_are_subset_of_properties(
        self, schema, schema_name
    ):
        """required 字段必须在 properties 中声明。"""
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        missing = required - props
        assert not missing, (
            f"{schema_name} required 字段未在 properties 声明：{missing}"
        )


# --------------------------------------------------------------------------- #
# 各 schema 的 positive / negative 用例数据
# --------------------------------------------------------------------------- #
# 每个 schema 提供：1 个合法样本 + 多个非法样本（覆盖 required 缺失、类型错误、
# enum 违规、minimum/maximum 越界、additionalProperties 拒绝）

_VALID_SAMPLES: Dict[str, Dict[str, Any]] = {
    "memory": {
        "id": 1,
        "type": "long_term",
        "content": "测试记忆内容",
        "importance": 3,
        "created_at": "2026-07-05T10:00:00Z",
        "workspace_id": "default",
        # 可选字段
        "agent_id": "default",
        "tags": ["test", "schema"],
        "metadata": {"source": "unit-test"},
        "importance_score": 0.6,
        "permanent": False,
        "decay_type": "exponential",
        "reactivation_count": 0,
        "emotion_score": 0.0,
        "psychological_age": 1.0,
        "source": "user",
        "is_deleted": False,
        "vector_id": None,
        "updated_at": None,
        "archived_at": None,
    },
    "agent": {
        "id": "test-agent",
        "name": "测试 Agent",
        "model": "main",
        "system_prompt": "你是测试 Agent",
        "description": "测试用",
        "temperature": 0.7,
        "max_tokens": 0,
        "use_memory": True,
        "use_tools": True,
        "memory_scene": "chat",
        "decay_model": "exponential",
        "vision_enabled": False,
        "is_default": False,
        "created_at": "2026-07-05T10:00:00Z",
        "updated_at": None,
    },
    "message": {
        "id": "msg-001",
        "session_id": "session-001",
        "role": "user",
        "content": "你好",
        "content_type": "text",
        "thinking": None,
        "tool_calls": None,
        "metadata": {},
        "tokens": 0,
        "timestamp": "2026-07-05T10:00:00Z",
        "created_at": "2026-07-05T10:00:00Z",
        "is_deleted": False,
    },
    "tool": {
        "name": "calculator",
        "description": "计算器工具",
        "parameters": {"type": "object", "properties": {}},
        "category": "builtin",
        "type": "builtin",
        "enabled": True,
        "version": "1.0.0",
        "tags": ["math"],
        "examples": ["1+1=2"],
        "icon": None,
        "config": None,
        "status": "active",
    },
    "error": {
        "error": "测试错误",
        "error_code": "VALIDATION_ERROR",
        "details": {"field": "name"},
        "http_status": 400,
    },
    "graph_node": {
        "id": "node-001",
        "type": "concept",
        "properties": {"name": "测试节点"},
        "text_content": "测试内容",
        "vector_id": None,
        "created_at": "2026-07-05T10:00:00Z",
        "updated_at": None,
        "agent_id": "default",
    },
    "graph_edge": {
        "id": "edge-001",
        "source_id": "node-001",
        "target_id": "node-002",
        "relation_type": "related_to",
        "properties": {},
        "text_content": None,
        "vector_id": None,
        "created_at": "2026-07-05T10:00:00Z",
        "agent_id": "default",
    },
}


def _negative_cases(schema_name: str) -> List[Tuple[str, Dict[str, Any]]]:
    """为每个 schema 生成 negative 样本（覆盖各类约束违反）。

    返回 [(case_id, sample), ...]；case_id 描述违反类型。
    每个 schema 至少 2 个 negative（实际提供 4-5 个）。
    """
    valid = dict(_VALID_SAMPLES[schema_name])

    if schema_name == "memory":
        return [
            (
                "missing_required_id",
                {k: v for k, v in valid.items() if k != "id"},
            ),
            ("missing_required_type", {k: v for k, v in valid.items() if k != "type"}),
            (
                "type_wrong_value",
                {**valid, "type": "INVALID_TYPE"},
            ),
            ("importance_out_of_range", {**valid, "importance": 10}),
            ("importance_wrong_type", {**valid, "importance": "3"}),
            ("content_too_short", {**valid, "content": ""}),
            ("additional_property_rejected", {**valid, "unknown_field": "x"}),
        ]

    if schema_name == "agent":
        return [
            ("missing_required_id", {k: v for k, v in valid.items() if k != "id"}),
            (
                "missing_required_name",
                {k: v for k, v in valid.items() if k != "name"},
            ),
            ("model_invalid_enum", {**valid, "model": "INVALID_SLOT"}),
            ("temperature_out_of_range", {**valid, "temperature": 3.0}),
            ("id_empty_string", {**valid, "id": ""}),
            ("additional_property_rejected", {**valid, "extra": "x"}),
        ]

    if schema_name == "message":
        return [
            ("missing_required_role", {k: v for k, v in valid.items() if k != "role"}),
            (
                "missing_required_session_id",
                {k: v for k, v in valid.items() if k != "session_id"},
            ),
            ("role_invalid_enum", {**valid, "role": "robot"}),
            ("tokens_negative", {**valid, "tokens": -1}),
            ("additional_property_rejected", {**valid, "extra": "x"}),
        ]

    if schema_name == "tool":
        return [
            ("missing_required_name", {k: v for k, v in valid.items() if k != "name"}),
            (
                "missing_required_parameters",
                {k: v for k, v in valid.items() if k != "parameters"},
            ),
            ("name_invalid_pattern", {**valid, "name": "123invalid"}),
            ("category_invalid_enum", {**valid, "category": "unknown"}),
            ("status_invalid_enum", {**valid, "status": "pending"}),
            ("additional_property_rejected", {**valid, "extra": "x"}),
        ]

    if schema_name == "error":
        return [
            ("missing_required_error", {k: v for k, v in valid.items() if k != "error"}),
            (
                "missing_required_error_code",
                {k: v for k, v in valid.items() if k != "error_code"},
            ),
            ("error_code_invalid_enum", {**valid, "error_code": "UNKNOWN_CODE"}),
            ("http_status_out_of_range", {**valid, "http_status": 999}),
            ("error_empty_string", {**valid, "error": ""}),
            ("additional_property_rejected", {**valid, "extra": "x"}),
        ]

    if schema_name == "graph_node":
        return [
            ("missing_required_id", {k: v for k, v in valid.items() if k != "id"}),
            (
                "missing_required_type",
                {k: v for k, v in valid.items() if k != "type"},
            ),
            (
                "missing_required_agent_id",
                {k: v for k, v in valid.items() if k != "agent_id"},
            ),
            ("id_empty_string", {**valid, "id": ""}),
            ("type_empty_string", {**valid, "type": ""}),
            ("additional_property_rejected", {**valid, "extra": "x"}),
        ]

    if schema_name == "graph_edge":
        return [
            ("missing_required_source_id", {k: v for k, v in valid.items() if k != "source_id"}),
            (
                "missing_required_target_id",
                {k: v for k, v in valid.items() if k != "target_id"},
            ),
            (
                "missing_required_relation_type",
                {k: v for k, v in valid.items() if k != "relation_type"},
            ),
            ("source_id_empty_string", {**valid, "source_id": ""}),
            ("additional_property_rejected", {**valid, "extra": "x"}),
        ]

    return []


# --------------------------------------------------------------------------- #
# Per-schema positive / negative 校验
# --------------------------------------------------------------------------- #


class TestSchemaSamples:
    """每个 schema 的合法样本通过 + 非法样本失败。"""

    def test_valid_sample_passes(self, schema, schema_name):
        """合法样本通过 schema 校验（每个 schema 至少 1 个 positive）。"""
        sample = _VALID_SAMPLES[schema_name]
        jsonschema.validate(sample, schema)

    @pytest.mark.parametrize(
        "case_id, sample",
        _negative_cases("memory"),
    )
    def test_memory_negative(self, case_id, sample):
        schema = _load_schema("memory")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    @pytest.mark.parametrize(
        "case_id, sample",
        _negative_cases("agent"),
    )
    def test_agent_negative(self, case_id, sample):
        schema = _load_schema("agent")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    @pytest.mark.parametrize(
        "case_id, sample",
        _negative_cases("message"),
    )
    def test_message_negative(self, case_id, sample):
        schema = _load_schema("message")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    @pytest.mark.parametrize(
        "case_id, sample",
        _negative_cases("tool"),
    )
    def test_tool_negative(self, case_id, sample):
        schema = _load_schema("tool")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    @pytest.mark.parametrize(
        "case_id, sample",
        _negative_cases("error"),
    )
    def test_error_negative(self, case_id, sample):
        schema = _load_schema("error")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    @pytest.mark.parametrize(
        "case_id, sample",
        _negative_cases("graph_node"),
    )
    def test_graph_node_negative(self, case_id, sample):
        schema = _load_schema("graph_node")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    @pytest.mark.parametrize(
        "case_id, sample",
        _negative_cases("graph_edge"),
    )
    def test_graph_edge_negative(self, case_id, sample):
        schema = _load_schema("graph_edge")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)


# --------------------------------------------------------------------------- #
# 字段约束逐项断言（required / type / enum / minimum / maximum / default）
# --------------------------------------------------------------------------- #


class TestFieldConstraints:
    """逐项断言每类字段约束（rules-3 §一 required_fields 全覆盖）。"""

    def test_memory_required_fields(self):
        schema = _load_schema("memory")
        required = set(schema["required"])
        expected = {"id", "type", "content", "importance", "created_at", "workspace_id"}
        assert expected.issubset(required), (
            f"memory.required 缺少：{expected - required}"
        )

    def test_memory_type_enum_constraint(self):
        schema = _load_schema("memory")
        type_prop = schema["properties"]["type"]
        assert type_prop["type"] == "string"
        assert "permanent" in type_prop["enum"]
        assert "long_term" in type_prop["enum"]
        assert "short_term" in type_prop["enum"]

    def test_memory_importance_min_max(self):
        schema = _load_schema("memory")
        imp = schema["properties"]["importance"]
        assert imp["type"] == "integer"
        assert imp["minimum"] == 1
        assert imp["maximum"] == 5

    def test_memory_importance_score_default(self):
        schema = _load_schema("memory")
        score = schema["properties"]["importance_score"]
        assert score["type"] == "number"
        assert score["default"] == 0.6
        assert score["minimum"] == 0
        assert score["maximum"] == 1

    def test_memory_decay_type_default(self):
        schema = _load_schema("memory")
        decay = schema["properties"]["decay_type"]
        assert decay["default"] == "exponential"
        assert "exponential" in decay["enum"]
        assert "ebbinghaus" in decay["enum"]

    def test_memory_permanent_default(self):
        schema = _load_schema("memory")
        assert schema["properties"]["permanent"]["default"] is False

    def test_memory_content_minlength(self):
        schema = _load_schema("memory")
        content = schema["properties"]["content"]
        assert content["type"] == "string"
        assert content["minLength"] == 1

    def test_agent_required_fields(self):
        schema = _load_schema("agent")
        required = set(schema["required"])
        expected = {"id", "name", "model", "system_prompt"}
        assert expected.issubset(required), (
            f"agent.required 缺少：{expected - required}"
        )

    def test_agent_model_enum(self):
        schema = _load_schema("agent")
        model = schema["properties"]["model"]
        assert set(model["enum"]) == {"main", "summary", "memory"}

    def test_agent_temperature_range(self):
        schema = _load_schema("agent")
        temp = schema["properties"]["temperature"]
        assert temp["type"] == "number"
        assert temp["minimum"] == 0
        assert temp["maximum"] == 2
        assert temp["default"] == 0.7

    def test_agent_memory_scene_enum(self):
        schema = _load_schema("agent")
        scene = schema["properties"]["memory_scene"]
        assert set(scene["enum"]) == {"chat", "task", "first_interaction"}
        assert scene["default"] == "chat"

    def test_message_required_fields(self):
        schema = _load_schema("message")
        required = set(schema["required"])
        expected = {"id", "session_id", "role", "content"}
        assert expected.issubset(required)

    def test_message_role_enum(self):
        schema = _load_schema("message")
        role = schema["properties"]["role"]
        assert set(role["enum"]) == {"user", "assistant", "system", "tool"}

    def test_message_content_type_enum(self):
        schema = _load_schema("message")
        ct = schema["properties"]["content_type"]
        assert set(ct["enum"]) == {"text", "json", "image", "tool_call"}
        assert ct["default"] == "text"

    def test_message_tokens_minimum(self):
        schema = _load_schema("message")
        tokens = schema["properties"]["tokens"]
        assert tokens["type"] == "integer"
        assert tokens["minimum"] == 0
        assert tokens["default"] == 0

    def test_tool_required_fields(self):
        schema = _load_schema("tool")
        required = set(schema["required"])
        expected = {"name", "description", "parameters"}
        assert expected.issubset(required)

    def test_tool_name_pattern(self):
        schema = _load_schema("tool")
        name = schema["properties"]["name"]
        assert name["pattern"] == "^[a-zA-Z_][a-zA-Z0-9_]*$"

    def test_tool_category_enum(self):
        schema = _load_schema("tool")
        cat = schema["properties"]["category"]
        assert set(cat["enum"]) == {"builtin", "custom", "mcp", "native", "general"}
        assert cat["default"] == "general"

    def test_tool_status_enum(self):
        schema = _load_schema("tool")
        status = schema["properties"]["status"]
        assert set(status["enum"]) == {"active", "inactive"}

    def test_error_required_fields(self):
        schema = _load_schema("error")
        required = set(schema["required"])
        assert required == {"error", "error_code"}

    def test_error_code_enum(self):
        schema = _load_schema("error")
        codes = schema["properties"]["error_code"]["enum"]
        # 抽样验证关键错误码（rules-3 §一 error_codes 必须包含核心错误）
        must_have = {
            "INTERNAL_ERROR",
            "DATABASE_ERROR",
            "VALIDATION_ERROR",
            "MEMORY_NOT_FOUND",
            "LLM_ERROR",
            "TOOL_ERROR",
            "AGENT_NOT_FOUND",
        }
        assert must_have.issubset(set(codes)), (
            f"error.error_code 缺少核心码：{must_have - set(codes)}"
        )

    def test_error_http_status_range(self):
        schema = _load_schema("error")
        http = schema["properties"]["http_status"]
        assert http["minimum"] == 100
        assert http["maximum"] == 599

    def test_graph_node_required_fields(self):
        schema = _load_schema("graph_node")
        required = set(schema["required"])
        expected = {"id", "type", "agent_id"}
        assert expected.issubset(required)

    def test_graph_node_defaults(self):
        schema = _load_schema("graph_node")
        assert schema["properties"]["text_content"]["default"] is None
        assert schema["properties"]["vector_id"]["default"] is None
        assert schema["properties"]["agent_id"]["default"] == "default"

    def test_graph_edge_required_fields(self):
        schema = _load_schema("graph_edge")
        required = set(schema["required"])
        expected = {"id", "source_id", "target_id", "relation_type", "agent_id"}
        assert expected.issubset(required)

    def test_graph_edge_minlength_constraints(self):
        schema = _load_schema("graph_edge")
        for field in ("id", "source_id", "target_id", "relation_type"):
            assert schema["properties"][field]["minLength"] == 1

    def test_graph_edge_defaults(self):
        schema = _load_schema("graph_edge")
        assert schema["properties"]["text_content"]["default"] is None
        assert schema["properties"]["vector_id"]["default"] is None
        assert schema["properties"]["agent_id"]["default"] == "default"
