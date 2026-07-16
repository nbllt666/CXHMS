"""RADIX-Lite 三层契约测试套件。

对应 rules-3 三层契约可验证性要求 (v6 新增 §五)。
覆盖数据契约 / 接口契约 / 配置契约三层 rubric + 契约一致性检查。

运行方式：
    $env:PYTHONPATH = "."; python tests/contract/radix_contract_test.py

或通过 pytest：
    pytest tests/contract/radix_contract_test.py -v

约束：
    - public/ 受保护，本测试只读不写
    - 不依赖 backend 实现，纯契约校验
    - 使用 jsonschema 库做 draft-07 校验
    - 使用 ast 解析 .pyi 存根验证签名

@version 1.0.0
@see .trae/specs/add-management-agent-radix/spec.md
@see .trae/specs/add-management-agent-radix/checklist.md
"""

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema
import pytest

# --------------------------------------------------------------------------- #
# 路径锚点（rules-0 §三：用 os.path.dirname(os.path.abspath(__file__)) 解析）
# --------------------------------------------------------------------------- #
_THIS_FILE = os.path.abspath(__file__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_PUBLIC_DIR = Path(_PROJECT_ROOT) / "public"
_SCHEMA_DIR = _PUBLIC_DIR / "schema"
_INTERFACE_STUB_DIR = _PUBLIC_DIR / "interface_stub"
_CONFIG_TEMPLATE_DIR = _PUBLIC_DIR / "config_template"

# 6 个数据契约 schema 文件
SCHEMA_FILES = {
    "distillation_session": _SCHEMA_DIR / "distillation_session.schema.json",
    "multimodal_artifact": _SCHEMA_DIR / "multimodal_artifact.schema.json",
    "template_registry": _SCHEMA_DIR / "template_registry.schema.json",
    "storage_decision": _SCHEMA_DIR / "storage_decision.schema.json",
    "distillation_log": _SCHEMA_DIR / "distillation_log.schema.json",
    "agent_config_v2": _SCHEMA_DIR / "agent_config_v2.schema.json",
}

# 6 个接口契约 .pyi 文件
STUB_FILES = {
    "distillation_service": _INTERFACE_STUB_DIR / "distillation_service.pyi",
    "template_engine": _INTERFACE_STUB_DIR / "template_engine.pyi",
    "multimodal_pipeline": _INTERFACE_STUB_DIR / "multimodal_pipeline.pyi",
    "decision_core": _INTERFACE_STUB_DIR / "decision_core.pyi",
    "memory_manager_v2": _INTERFACE_STUB_DIR / "memory_manager_v2.pyi",
    "agent_tools_v2": _INTERFACE_STUB_DIR / "agent_tools_v2.pyi",
}

# 配置契约文件
CONFIG_FILE = _CONFIG_TEMPLATE_DIR / "radix_config.json"


# --------------------------------------------------------------------------- #
# 公共加载辅助
# --------------------------------------------------------------------------- #


def _load_json(path: Path) -> Dict[str, Any]:
    """加载 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_stub_text(name: str) -> str:
    """加载 .pyi 存根文本。"""
    with open(STUB_FILES[name], "r", encoding="utf-8") as f:
        return f.read()


def _parse_stub(name: str) -> ast.Module:
    """解析 .pyi 存根为 AST。"""
    return ast.parse(_load_stub_text(name), filename=str(STUB_FILES[name]))


def _get_classes(tree: ast.Module) -> Dict[str, ast.ClassDef]:
    """提取模块级类定义。"""
    classes = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = node
    return classes


def _get_methods(class_def: ast.ClassDef) -> Dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    """提取类中的方法定义。"""
    methods = {}
    for node in class_def.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods[node.name] = node
    return methods


def _get_method_params(method: ast.AsyncFunctionDef | ast.FunctionDef) -> List[str]:
    """提取方法的参数名列表（含 self/cls）。"""
    params = []
    for arg in method.args.args:
        params.append(arg.arg)
    return params


# ============================================================================ #
# 一、数据契约 rubric（6 个 schema）
# ============================================================================ #


class TestDataContractSchema:
    """数据契约 rubric：6 个 schema 均为合法 JSON Schema draft-07+。"""

    @pytest.mark.parametrize("schema_name", list(SCHEMA_FILES.keys()))
    def test_schema_file_exists(self, schema_name: str):
        """schema 文件存在。"""
        assert SCHEMA_FILES[schema_name].exists(), f"{SCHEMA_FILES[schema_name]} 不存在"

    @pytest.mark.parametrize("schema_name", list(SCHEMA_FILES.keys()))
    def test_schema_is_valid_draft07(self, schema_name: str):
        """schema 为合法 JSON Schema draft-07+。"""
        schema = _load_json(SCHEMA_FILES[schema_name])
        assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#", \
            f"{schema_name} $schema 不是 draft-07"
        assert "$id" in schema, f"{schema_name} 缺少 $id"
        assert "title" in schema, f"{schema_name} 缺少 title"
        assert "description" in schema, f"{schema_name} 缺少 description"
        assert "required" in schema, f"{schema_name} 缺少 required"
        assert "properties" in schema, f"{schema_name} 缺少 properties"

    @pytest.mark.parametrize("schema_name", list(SCHEMA_FILES.keys()))
    def test_schema_has_error_codes(self, schema_name: str):
        """schema 含 definitions.error_codes（rules-3 §1.2）。"""
        schema = _load_json(SCHEMA_FILES[schema_name])
        assert "definitions" in schema, f"{schema_name} 缺少 definitions"
        assert "error_codes" in schema["definitions"], \
            f"{schema_name} 缺少 definitions.error_codes"
        error_codes = schema["definitions"]["error_codes"]["properties"]
        assert len(error_codes) > 0, f"{schema_name} error_codes 为空"

    @pytest.mark.parametrize("schema_name", list(SCHEMA_FILES.keys()))
    def test_schema_has_exceptions(self, schema_name: str):
        """schema 含 definitions.exceptions（rules-3 §1.2）。"""
        schema = _load_json(SCHEMA_FILES[schema_name])
        assert "exceptions" in schema["definitions"], \
            f"{schema_name} 缺少 definitions.exceptions"
        exceptions = schema["definitions"]["exceptions"]["properties"]
        assert len(exceptions) > 0, f"{schema_name} exceptions 为空"


class TestDistillationSessionSchema:
    """distillation_session.schema 字段 rubric。"""

    def test_required_fields(self):
        """必需字段完整。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        required = schema["required"]
        for field in ["session_id", "source_type", "state", "template_id",
                      "max_turns", "ask_user_on_ambiguity", "turns", "created_at", "is_finalized"]:
            assert field in required, f"distillation_session 缺少必需字段 {field}"

    def test_state_enum_7_states(self):
        """state 枚举含 7 状态机 + 2 终态 = 9 个状态。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        states = schema["properties"]["state"]["enum"]
        expected = ["S_INIT", "S_PREREAD", "S_QUESTION", "S_REFLECT",
                    "S_CROSSVALIDATE", "S_EXTRACT", "S_STORAGE_DECISION",
                    "S_FINALIZE", "S_REJECT"]
        assert states == expected, f"state 枚举不匹配: {states}"

    def test_source_type_enum(self):
        """source_type 枚举含 4 种数据源。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        sources = schema["properties"]["source_type"]["enum"]
        assert "text" in sources
        assert "character_card" in sources
        assert "image" in sources
        assert "conversation_log" in sources

    def test_session_id_uuid_pattern(self):
        """session_id 为 UUID v4 格式。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        pattern = schema["properties"]["session_id"]["pattern"]
        assert "8-4-4-4-12" in pattern or "[0-9a-fA-F]" in pattern

    def test_max_turns_range(self):
        """max_turns 范围 1-6。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        props = schema["properties"]["max_turns"]
        assert props["minimum"] == 1
        assert props["maximum"] == 6


class TestMultimodalArtifactSchema:
    """multimodal_artifact.schema 字段 rubric。"""

    def test_required_fields(self):
        schema = _load_json(SCHEMA_FILES["multimodal_artifact"])
        required = schema["required"]
        for field in ["artifact_id", "type", "source", "text_content",
                      "confidence", "vision_degraded", "created_at"]:
            assert field in required, f"multimodal_artifact 缺少必需字段 {field}"

    def test_type_enum_3_modalities(self):
        """type 枚举含 3 模态（去音视频）。"""
        schema = _load_json(SCHEMA_FILES["multimodal_artifact"])
        types = schema["properties"]["type"]["enum"]
        assert types == ["text", "character_card", "image"], f"type 枚举不匹配: {types}"

    def test_confidence_range(self):
        """confidence 范围 0-1。"""
        schema = _load_json(SCHEMA_FILES["multimodal_artifact"])
        props = schema["properties"]["confidence"]
        assert props["minimum"] == 0
        assert props["maximum"] == 1

    def test_vision_degraded_default(self):
        """vision_degraded 默认 false。"""
        schema = _load_json(SCHEMA_FILES["multimodal_artifact"])
        assert schema["properties"]["vision_degraded"]["default"] is False


class TestTemplateRegistrySchema:
    """template_registry.schema 字段 rubric。"""

    def test_required_fields(self):
        schema = _load_json(SCHEMA_FILES["template_registry"])
        required = schema["required"]
        for field in ["template_id", "name", "category", "frontmatter",
                      "body", "created_at", "updated_at"]:
            assert field in required, f"template_registry 缺少必需字段 {field}"

    def test_category_enum(self):
        """category 枚举 preset / custom。"""
        schema = _load_json(SCHEMA_FILES["template_registry"])
        categories = schema["properties"]["category"]["enum"]
        assert categories == ["preset", "custom"]

    def test_frontmatter_workflow_mode(self):
        """frontmatter.workflow_mode 枚举 single_turn / multi_turn。"""
        schema = _load_json(SCHEMA_FILES["template_registry"])
        fm = schema["properties"]["frontmatter"]["properties"]
        modes = fm["workflow_mode"]["enum"]
        assert modes == ["single_turn", "multi_turn"]

    def test_frontmatter_expected_turns_range(self):
        """frontmatter.expected_turns 范围 1-6。"""
        schema = _load_json(SCHEMA_FILES["template_registry"])
        fm = schema["properties"]["frontmatter"]["properties"]
        et = fm["expected_turns"]
        assert et["minimum"] == 1
        assert et["maximum"] == 6

    def test_render_result_definition(self):
        """definitions.render_result 含 rendered_prompt / workflow_definition / expected_turns。"""
        schema = _load_json(SCHEMA_FILES["template_registry"])
        rr = schema["definitions"]["render_result"]["properties"]
        assert "rendered_prompt" in rr
        assert "workflow_definition" in rr
        assert "expected_turns" in rr


class TestStorageDecisionSchema:
    """storage_decision.schema 字段 rubric。"""

    def test_required_fields(self):
        schema = _load_json(SCHEMA_FILES["storage_decision"])
        required = schema["required"]
        for field in ["decision_id", "session_id", "decision_point", "location",
                      "reason", "quality_score", "created_at"]:
            assert field in required, f"storage_decision 缺少必需字段 {field}"

    def test_decision_point_enum_6(self):
        """decision_point 枚举含 6 决策点。"""
        schema = _load_json(SCHEMA_FILES["storage_decision"])
        dps = schema["properties"]["decision_point"]["enum"]
        expected = ["D1_LOCATION", "D2_METADATA", "D3_ASK_USER",
                    "D4_REDISTILL", "D5_CROSS_VALIDATE", "D6_REJECT"]
        assert dps == expected, f"decision_point 枚举不匹配: {dps}"

    def test_location_enum_3(self):
        """location 枚举 memories / permanent_memories / rejected。"""
        schema = _load_json(SCHEMA_FILES["storage_decision"])
        locations = schema["properties"]["location"]["enum"]
        assert locations == ["memories", "permanent_memories", "rejected"]

    def test_rubric_snapshot_fields(self):
        """rubric_snapshot 含 4 必需阈值。"""
        schema = _load_json(SCHEMA_FILES["storage_decision"])
        rs = schema["properties"]["rubric_snapshot"]["properties"]
        for field in ["importance_threshold_permanent", "quality_reject_threshold",
                      "max_redistill_turns", "ask_user_confidence_threshold"]:
            assert field in rs, f"rubric_snapshot 缺少 {field}"


class TestDistillationLogSchema:
    """distillation_log.schema 字段 rubric。"""

    def test_required_fields(self):
        schema = _load_json(SCHEMA_FILES["distillation_log"])
        required = schema["required"]
        for field in ["log_id", "session_id", "decision_point", "input",
                      "rubric_snapshot", "final_decision", "timestamp"]:
            assert field in required, f"distillation_log 缺少必需字段 {field}"

    def test_decision_point_enum_6(self):
        """decision_point 枚举与 storage_decision 一致。"""
        schema = _load_json(SCHEMA_FILES["distillation_log"])
        dps = schema["properties"]["decision_point"]["enum"]
        expected = ["D1_LOCATION", "D2_METADATA", "D3_ASK_USER",
                    "D4_REDISTILL", "D5_CROSS_VALIDATE", "D6_REJECT"]
        assert dps == expected

    def test_final_decision_action_enum(self):
        """final_decision.action 枚举含 6 动作。"""
        schema = _load_json(SCHEMA_FILES["distillation_log"])
        actions = schema["properties"]["final_decision"]["properties"]["action"]["enum"]
        for a in ["store", "ask_user", "redistill", "cross_validate", "reject", "skip"]:
            assert a in actions, f"final_decision.action 缺少 {a}"


class TestAgentConfigV2Schema:
    """agent_config_v2.schema 字段 rubric。"""

    def test_required_fields(self):
        schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        required = schema["required"]
        for field in ["agent_id", "name", "tools_config", "decision_rubric",
                      "distillation_enabled"]:
            assert field in required, f"agent_config_v2 缺少必需字段 {field}"

    def test_tools_config_8_tools(self):
        """tools_config 含 8 工具默认启用。"""
        schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        tc = schema["properties"]["tools_config"]["properties"]
        for tool in ["add_agent", "update_agent", "delete_agent",
                     "start_distillation", "advance_distillation", "finalize_distillation",
                     "render_template", "decide_storage"]:
            assert tool in tc, f"tools_config 缺少工具 {tool}"
            assert tc[tool]["default"] is True, f"工具 {tool} 默认未启用"

    def test_decision_rubric_required_fields(self):
        """decision_rubric 含 4 必需阈值。"""
        schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        dr = schema["properties"]["decision_rubric"]
        for field in ["importance_threshold_permanent", "quality_reject_threshold",
                      "max_redistill_turns", "ask_user_confidence_threshold"]:
            assert field in dr["required"], f"decision_rubric 缺少必需字段 {field}"

    def test_distillation_enabled_default_false(self):
        """distillation_enabled 默认 false。"""
        schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        assert schema["properties"]["distillation_enabled"]["default"] is False

    def test_legacy_parser_enabled_default_true(self):
        """legacy_parser_enabled 默认 true（回退开关）。"""
        schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        assert schema["properties"]["legacy_parser_enabled"]["default"] is True


# ============================================================================ #
# 二、接口契约 rubric（6 个 .pyi 存根）
# ============================================================================ #


class TestInterfaceStubExistence:
    """接口契约 rubric：6 个 .pyi 存根文件存在且可解析。"""

    @pytest.mark.parametrize("stub_name", list(STUB_FILES.keys()))
    def test_stub_file_exists(self, stub_name: str):
        """存根文件存在。"""
        assert STUB_FILES[stub_name].exists(), f"{STUB_FILES[stub_name]} 不存在"

    @pytest.mark.parametrize("stub_name", list(STUB_FILES.keys()))
    def test_stub_parseable(self, stub_name: str):
        """存根可被 ast 解析。"""
        tree = _parse_stub(stub_name)
        assert isinstance(tree, ast.Module), f"{stub_name} 解析失败"

    @pytest.mark.parametrize("stub_name", list(STUB_FILES.keys()))
    def test_stub_has_class(self, stub_name: str):
        """存根定义了主类。"""
        tree = _parse_stub(stub_name)
        classes = _get_classes(tree)
        expected_classes = {
            "distillation_service": "DistillationService",
            "template_engine": "TemplateEngine",
            "multimodal_pipeline": "MultimodalPipeline",
            "decision_core": "DecisionCore",
            "memory_manager_v2": "MemoryManagerV2",
            "agent_tools_v2": "AgentToolsV2",
        }
        expected = expected_classes[stub_name]
        assert expected in classes, f"{stub_name} 缺少类 {expected}"


class TestDistillationServiceStub:
    """distillation_service.pyi 方法签名 rubric。"""

    def test_4_api_methods(self):
        """定义 4 个 API 端点方法。"""
        tree = _parse_stub("distillation_service")
        cls = _get_classes(tree)["DistillationService"]
        methods = _get_methods(cls)
        for m in ["start_distillation", "advance_distillation",
                  "finalize_distillation", "get_session_status"]:
            assert m in methods, f"DistillationService 缺少方法 {m}"

    def test_start_distillation_params(self):
        """start_distillation 参数签名。"""
        tree = _parse_stub("distillation_service")
        cls = _get_classes(tree)["DistillationService"]
        method = _get_methods(cls)["start_distillation"]
        params = _get_method_params(method)
        for p in ["self", "source_type", "source_ref", "template_id",
                  "max_turns", "ask_user_on_ambiguity"]:
            assert p in params, f"start_distillation 缺少参数 {p}"


class TestTemplateEngineStub:
    """template_engine.pyi 方法签名 rubric。"""

    def test_render_and_crud(self):
        """定义 render_template + 5 个 CRUD 方法。"""
        tree = _parse_stub("template_engine")
        cls = _get_classes(tree)["TemplateEngine"]
        methods = _get_methods(cls)
        for m in ["render_template", "list_templates", "get_template",
                  "create_template", "update_template", "delete_template"]:
            assert m in methods, f"TemplateEngine 缺少方法 {m}"

    def test_render_template_params(self):
        """render_template 参数签名。"""
        tree = _parse_stub("template_engine")
        cls = _get_classes(tree)["TemplateEngine"]
        method = _get_methods(cls)["render_template"]
        params = _get_method_params(method)
        for p in ["self", "template_id", "variables", "workflow_mode"]:
            assert p in params, f"render_template 缺少参数 {p}"


class TestMultimodalPipelineStub:
    """multimodal_pipeline.pyi 方法签名 rubric。"""

    def test_preprocess_and_workers(self):
        """定义 preprocess + 3 个 worker 方法。"""
        tree = _parse_stub("multimodal_pipeline")
        cls = _get_classes(tree)["MultimodalPipeline"]
        methods = _get_methods(cls)
        for m in ["preprocess", "_text_worker", "_character_card_worker", "_image_worker"]:
            assert m in methods, f"MultimodalPipeline 缺少方法 {m}"

    def test_preprocess_params(self):
        """preprocess 参数签名。"""
        tree = _parse_stub("multimodal_pipeline")
        cls = _get_classes(tree)["MultimodalPipeline"]
        method = _get_methods(cls)["preprocess"]
        params = _get_method_params(method)
        for p in ["self", "source_type", "source_ref"]:
            assert p in params, f"preprocess 缺少参数 {p}"


class TestDecisionCoreStub:
    """decision_core.pyi 方法签名 rubric。"""

    def test_6_decision_methods(self):
        """定义 6 决策点方法。"""
        tree = _parse_stub("decision_core")
        cls = _get_classes(tree)["DecisionCore"]
        methods = _get_methods(cls)
        for m in ["decide_location", "decide_metadata", "decide_ask_user",
                  "decide_redistill", "decide_cross_validate", "decide_reject"]:
            assert m in methods, f"DecisionCore 缺少方法 {m}"

    def test_decide_location_params(self):
        """decide_location 参数签名。"""
        tree = _parse_stub("decision_core")
        cls = _get_classes(tree)["DecisionCore"]
        method = _get_methods(cls)["decide_location"]
        params = _get_method_params(method)
        for p in ["self", "session_id", "decision_input", "rubric"]:
            assert p in params, f"decide_location 缺少参数 {p}"


class TestMemoryManagerV2Stub:
    """memory_manager_v2.pyi 方法签名 rubric。"""

    def test_write_with_decision(self):
        """定义 write_with_decision 方法。"""
        tree = _parse_stub("memory_manager_v2")
        cls = _get_classes(tree)["MemoryManagerV2"]
        methods = _get_methods(cls)
        assert "write_with_decision" in methods, "MemoryManagerV2 缺少 write_with_decision"

    def test_write_with_decision_params(self):
        """write_with_decision 参数签名。"""
        tree = _parse_stub("memory_manager_v2")
        cls = _get_classes(tree)["MemoryManagerV2"]
        method = _get_methods(cls)["write_with_decision"]
        params = _get_method_params(method)
        for p in ["self", "content", "decision", "metadata"]:
            assert p in params, f"write_with_decision 缺少参数 {p}"


class TestAgentToolsV2Stub:
    """agent_tools_v2.pyi 方法签名 rubric。"""

    def test_8_tools(self):
        """定义 8 个工具方法。"""
        tree = _parse_stub("agent_tools_v2")
        cls = _get_classes(tree)["AgentToolsV2"]
        methods = _get_methods(cls)
        for m in ["add_agent", "update_agent", "delete_agent",
                  "start_distillation", "advance_distillation", "finalize_distillation",
                  "render_template", "decide_storage"]:
            assert m in methods, f"AgentToolsV2 缺少工具 {m}"


# ============================================================================ #
# 三、配置契约 rubric（radix_config.json）
# ============================================================================ #


class TestRadixConfig:
    """配置契约 rubric：radix_config.json 含 5 段配置 + 默认值。"""

    def test_config_file_exists(self):
        """配置文件存在。"""
        assert CONFIG_FILE.exists(), f"{CONFIG_FILE} 不存在"

    def test_config_is_valid_json_schema(self):
        """配置为合法 JSON Schema draft-07+。"""
        config = _load_json(CONFIG_FILE)
        assert config.get("$schema") == "http://json-schema.org/draft-07/schema#"

    def test_5_config_sections(self):
        """含 5 个配置段。"""
        config = _load_json(CONFIG_FILE)
        required = config["required"]
        for section in ["distillation_service", "multimodal_pipeline",
                        "template_engine", "decision_core", "vllm"]:
            assert section in required, f"radix_config 缺少配置段 {section}"

    def test_distillation_service_defaults(self):
        """distillation_service 段含端口 + 超时默认值。"""
        config = _load_json(CONFIG_FILE)
        ds = config["properties"]["distillation_service"]["properties"]
        assert ds["port"]["default"] == 8011
        assert ds["session_timeout_seconds"]["default"] == 1800
        assert ds["max_turns"]["default"] == 4

    def test_multimodal_pipeline_defaults(self):
        """multimodal_pipeline 段含 worker 池 + 模态默认值。"""
        config = _load_json(CONFIG_FILE)
        mp = config["properties"]["multimodal_pipeline"]["properties"]
        assert mp["worker_pool_size"]["default"] == 4
        assert mp["enabled_modalities"]["default"] == ["text", "character_card", "image"]

    def test_template_engine_defaults(self):
        """template_engine 段含目录默认值。"""
        config = _load_json(CONFIG_FILE)
        te = config["properties"]["template_engine"]["properties"]
        assert te["templates_dir"]["default"] == "data/templates"
        assert te["presets_dir"]["default"] == "data/templates/presets"
        assert te["custom_dir"]["default"] == "data/templates/custom"

    def test_decision_core_defaults(self):
        """decision_core 段含 rubric 默认值。"""
        config = _load_json(CONFIG_FILE)
        dc = config["properties"]["decision_core"]["properties"]
        assert dc["importance_threshold_permanent"]["default"] == 0.7
        assert dc["quality_reject_threshold"]["default"] == 0.3
        assert dc["max_redistill_turns"]["default"] == 2
        assert dc["ask_user_confidence_threshold"]["default"] == 0.4

    def test_vllm_defaults(self):
        """vllm 段含 base_url + timeout 默认值。"""
        config = _load_json(CONFIG_FILE)
        vllm = config["properties"]["vllm"]["properties"]
        assert vllm["base_url"]["default"] == "http://127.0.0.1:8002"
        assert vllm["timeout_seconds"]["default"] == 300

    def test_legacy_parser_enabled_default(self):
        """legacy_parser_enabled 默认 true。"""
        config = _load_json(CONFIG_FILE)
        assert config["properties"]["legacy_parser_enabled"]["default"] is True

    def test_config_has_error_codes(self):
        """配置含 definitions.error_codes。"""
        config = _load_json(CONFIG_FILE)
        assert "error_codes" in config.get("definitions", {})

    def test_config_has_exceptions(self):
        """配置含 definitions.exceptions。"""
        config = _load_json(CONFIG_FILE)
        assert "exceptions" in config.get("definitions", {})


# ============================================================================ #
# 四、契约一致性检查
# ============================================================================ #


class TestContractConsistency:
    """三层契约一致性检查。"""

    def test_state_enum_consistency(self):
        """distillation_session.state 枚举与 spec.md 7 状态机一致。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        states = schema["properties"]["state"]["enum"]
        # 7 过程状态 + 2 终态 = 9
        assert len(states) == 9
        # 7 状态机顺序
        expected_order = ["S_INIT", "S_PREREAD", "S_QUESTION", "S_REFLECT",
                          "S_CROSSVALIDATE", "S_EXTRACT", "S_STORAGE_DECISION"]
        for i, state in enumerate(expected_order):
            assert states[i] == state, f"状态 {i} 不匹配: {states[i]} != {state}"

    def test_location_enum_consistency(self):
        """storage_decision.location 枚举与 spec.md D1 决策一致。"""
        sd_schema = _load_json(SCHEMA_FILES["storage_decision"])
        locations = sd_schema["properties"]["location"]["enum"]
        assert locations == ["memories", "permanent_memories", "rejected"]

    def test_modality_type_consistency(self):
        """multimodal_artifact.type 枚举与 spec.md 3 模态一致（去音视频）。"""
        ma_schema = _load_json(SCHEMA_FILES["multimodal_artifact"])
        types = ma_schema["properties"]["type"]["enum"]
        assert types == ["text", "character_card", "image"]
        # 不含 audio / video
        assert "audio" not in types
        assert "video" not in types

    def test_decision_point_enum_consistency(self):
        """storage_decision 与 distillation_log 的 decision_point 枚举一致。"""
        sd_schema = _load_json(SCHEMA_FILES["storage_decision"])
        dl_schema = _load_json(SCHEMA_FILES["distillation_log"])
        sd_dps = sd_schema["properties"]["decision_point"]["enum"]
        dl_dps = dl_schema["properties"]["decision_point"]["enum"]
        assert sd_dps == dl_dps, f"decision_point 枚举不一致: {sd_dps} vs {dl_dps}"

    def test_rubric_snapshot_fields_consistency(self):
        """storage_decision 与 distillation_log 的 rubric_snapshot 字段一致。"""
        sd_schema = _load_json(SCHEMA_FILES["storage_decision"])
        dl_schema = _load_json(SCHEMA_FILES["distillation_log"])
        sd_rs = set(sd_schema["properties"]["rubric_snapshot"]["properties"].keys())
        dl_rs = set(dl_schema["properties"]["rubric_snapshot"]["properties"].keys())
        # distillation_log 应包含 storage_decision 的所有字段
        assert sd_rs.issubset(dl_rs), \
            f"distillation_log.rubric_snapshot 缺少字段: {sd_rs - dl_rs}"

    def test_rubric_defaults_consistency(self):
        """agent_config_v2.decision_rubric 与 radix_config.decision_core 默认值一致。"""
        ac_schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        config = _load_json(CONFIG_FILE)
        ac_dr = ac_schema["properties"]["decision_rubric"]["properties"]
        dc = config["properties"]["decision_core"]["properties"]
        for field in ["importance_threshold_permanent", "quality_reject_threshold",
                      "max_redistill_turns", "ask_user_confidence_threshold"]:
            assert ac_dr[field]["default"] == dc[field]["default"], \
                f"{field} 默认值不一致: agent_config_v2={ac_dr[field]['default']} vs radix_config={dc[field]['default']}"

    def test_tools_config_consistency(self):
        """agent_config_v2.tools_config 的 8 工具与 agent_tools_v2.pyi 的 8 方法一致。"""
        ac_schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        tc_tools = set(ac_schema["properties"]["tools_config"]["properties"].keys())
        tree = _parse_stub("agent_tools_v2")
        cls = _get_classes(tree)["AgentToolsV2"]
        methods = set(_get_methods(cls).keys())
        # 去除 __init__ 等内置方法
        methods.discard("__init__")
        assert tc_tools == methods, \
            f"工具不一致: schema={tc_tools} vs stub={methods}"

    def test_session_id_uuid_pattern_consistency(self):
        """所有 schema 中的 session_id UUID pattern 一致。"""
        ds_schema = _load_json(SCHEMA_FILES["distillation_session"])
        sd_schema = _load_json(SCHEMA_FILES["storage_decision"])
        dl_schema = _load_json(SCHEMA_FILES["distillation_log"])
        ds_pattern = ds_schema["properties"]["session_id"]["pattern"]
        sd_pattern = sd_schema["properties"]["session_id"]["pattern"]
        dl_pattern = dl_schema["properties"]["session_id"]["pattern"]
        assert ds_pattern == sd_pattern == dl_pattern, \
            f"session_id pattern 不一致"

    def test_error_codes_present_in_all_schemas(self):
        """所有 6 个 schema 均含 error_codes（rules-3 §1.2）。"""
        for name, path in SCHEMA_FILES.items():
            schema = _load_json(path)
            assert "error_codes" in schema.get("definitions", {}), \
                f"{name} 缺少 definitions.error_codes"

    def test_exceptions_present_in_all_schemas(self):
        """所有 6 个 schema 均含 exceptions（rules-3 §1.2）。"""
        for name, path in SCHEMA_FILES.items():
            schema = _load_json(path)
            assert "exceptions" in schema.get("definitions", {}), \
                f"{name} 缺少 definitions.exceptions"


# ============================================================================ #
# 五、JSON Schema 校验（用样例数据验证 schema 可执行性）
# ============================================================================ #


class TestSchemaValidation:
    """用样例数据验证 schema 可执行性。"""

    def test_distillation_session_valid_sample(self):
        """distillation_session 合法样例通过校验。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        sample = {
            "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "source_type": "text",
            "state": "S_INIT",
            "template_id": "default_distillation",
            "max_turns": 4,
            "ask_user_on_ambiguity": True,
            "turns": [],
            "created_at": "2026-07-15T10:00:00Z",
            "is_finalized": False,
        }
        jsonschema.validate(sample, schema)

    def test_distillation_session_invalid_state(self):
        """distillation_session 非法 state 被拒绝。"""
        schema = _load_json(SCHEMA_FILES["distillation_session"])
        sample = {
            "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "source_type": "text",
            "state": "INVALID_STATE",
            "template_id": "default",
            "max_turns": 4,
            "ask_user_on_ambiguity": True,
            "turns": [],
            "created_at": "2026-07-15T10:00:00Z",
            "is_finalized": False,
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    def test_multimodal_artifact_valid_sample(self):
        """multimodal_artifact 合法样例通过校验。"""
        schema = _load_json(SCHEMA_FILES["multimodal_artifact"])
        sample = {
            "artifact_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "type": "text",
            "source": "test.txt",
            "text_content": "Hello world",
            "confidence": 1.0,
            "vision_degraded": False,
            "created_at": "2026-07-15T10:00:00Z",
        }
        jsonschema.validate(sample, schema)

    def test_storage_decision_valid_sample(self):
        """storage_decision 合法样例通过校验。"""
        schema = _load_json(SCHEMA_FILES["storage_decision"])
        sample = {
            "decision_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "session_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "decision_point": "D1_LOCATION",
            "location": "permanent_memories",
            "reason": "importance >= 0.7",
            "quality_score": 0.85,
            "created_at": "2026-07-15T10:00:00Z",
        }
        jsonschema.validate(sample, schema)

    def test_agent_config_v2_valid_sample(self):
        """agent_config_v2 合法样例通过校验。"""
        schema = _load_json(SCHEMA_FILES["agent_config_v2"])
        sample = {
            "agent_id": "memory-agent",
            "name": "管理 Agent",
            "tools_config": {"add_agent": True, "decide_storage": True},
            "decision_rubric": {
                "importance_threshold_permanent": 0.7,
                "quality_reject_threshold": 0.3,
                "max_redistill_turns": 2,
                "ask_user_confidence_threshold": 0.4,
            },
            "distillation_enabled": True,
        }
        jsonschema.validate(sample, schema)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
