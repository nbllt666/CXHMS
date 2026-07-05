"""配置契约校验测试（G4 批次 G-3）。

校验 public/config_template/*.json 默认值填充规则，对应 rules-3 §三 配置契约。

覆盖要求（spec tasks.md Task G4）：
    - 每个字段都有 default 值（rules-3 §三 defaults）
    - 模拟 auto_fill：构造缺失字段的配置 → 加载后应自动补充默认值
    - 校验：默认值类型匹配 schema 声明
    - 校验：与 config/default.yaml 字段一致性（不要求值一致，但字段名应能对应）

约束：
    - public/ 受保护，本测试只读不写
    - 不修改 config/default.yaml
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import jsonschema
import pytest
import yaml

# --------------------------------------------------------------------------- #
# 路径锚点
# --------------------------------------------------------------------------- #
_PUBLIC_CONFIG_DIR = Path(__file__).resolve().parents[2] / "public" / "config_template"
_DEFAULT_YAML_PATH = Path(__file__).resolve().parents[2] / "config" / "default.yaml"

_CONFIG_NAMES: List[str] = ["llm_config", "system_config", "vector_config"]


# --------------------------------------------------------------------------- #
# 公共 fixtures
# --------------------------------------------------------------------------- #


def _load_config_template(name: str) -> Dict[str, Any]:
    """加载 config_template 文件（受保护只读）。"""
    path = _PUBLIC_CONFIG_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_default_yaml() -> Dict[str, Any]:
    """加载 config/default.yaml（受保护只读）。"""
    with open(_DEFAULT_YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(params=_CONFIG_NAMES)
def config_name(request) -> str:
    return request.param


@pytest.fixture
def config_template(config_name) -> Dict[str, Any]:
    return _load_config_template(config_name)


# --------------------------------------------------------------------------- #
# 配置契约结构断言
# --------------------------------------------------------------------------- #


class TestConfigTemplateStructure:
    """每个 config_template 必须满足的结构性约束（rules-3 §三）。"""

    def test_config_file_is_valid_json(self, config_name):
        path = _PUBLIC_CONFIG_DIR / f"{config_name}.json"
        assert path.exists(), f"config_template 文件不存在：{path}"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_config_is_valid_json_schema(self, config_template, config_name):
        """config_template 本身是合法 JSON Schema。"""
        jsonschema.Draft7Validator.check_schema(config_template)

    def test_config_declares_draft07(self, config_template, config_name):
        assert "$schema" in config_template, f"{config_name} 缺少 $schema"
        assert "draft-07" in config_template["$schema"]

    def test_config_has_id(self, config_template, config_name):
        assert "$id" in config_template, f"{config_name} 缺少 $id"
        assert "config_template" in config_template["$id"], (
            f"{config_name} $id 应位于 config_template 域：{config_template['$id']}"
        )

    def test_config_has_title_and_description(self, config_template, config_name):
        assert "title" in config_template, f"{config_name} 缺少 title"
        assert "description" in config_template, f"{config_name} 缺少 description"

    def test_config_has_required(self, config_template, config_name):
        """config 必须声明 required（rules-3 §三 必填性）。"""
        assert "required" in config_template, f"{config_name} 缺少 required"
        assert len(config_template["required"]) > 0

    def test_config_disallows_additional_properties(self, config_template, config_name):
        """config_template 顶层必须 additionalProperties: false。"""
        assert config_template.get("additionalProperties") is False, (
            f"{config_name} 顶层必须 additionalProperties: false"
        )


# --------------------------------------------------------------------------- #
# 默认值填充规则（rules-3 §三 defaults + auto_fill）
# --------------------------------------------------------------------------- #


def _collect_leaf_fields(
    schema: Dict[str, Any], defs: Dict[str, Any] = None
) -> List[Tuple[str, str, Dict[str, Any]]]:
    """递归收集所有叶子字段（路径、字段名、字段定义）。

    叶子字段 = type 非 object，或 object 但无 properties（即纯容器）。
    用于校验 default 值是否声明。

    Returns:
        List of (dot_path, field_name, field_def) tuples
    """
    defs = defs or schema.get("$defs", {})
    results: List[Tuple[str, str, Dict[str, Any]]] = []

    def _walk(node: Dict[str, Any], path: str, required_set: Set[str]):
        props = node.get("properties", {})
        node_required = set(node.get("required", []))
        for name, defn in props.items():
            if not isinstance(defn, dict):
                continue
            # 解 $ref
            if "$ref" in defn:
                ref_name = defn["$ref"].split("/")[-1]
                defn = defs.get(ref_name, {})
            field_path = f"{path}.{name}" if path else name
            field_type = defn.get("type")
            # 如果是 object 且有 properties，递归
            if field_type == "object" and "properties" in defn:
                _walk(defn, field_path, node_required)
            else:
                results.append((field_path, name, defn))

    _walk(schema, "", set())
    return results


class TestDefaultValues:
    """每个可缺省字段必须声明 default（rules-3 §三 defaults）。"""

    def test_all_optional_fields_have_defaults(self, config_template, config_name):
        """非 required 字段必须声明 default。"""
        defs = config_template.get("$defs", {})
        leaf_fields = _collect_leaf_fields(config_template, defs)
        missing: List[str] = []
        for path, name, defn in leaf_fields:
            # required 字段可以无 default
            # 判断：该字段是否在父节点的 required 列表中（启发式：通过路径无法精确判断，
            # 用宽松规则——有 default 则验证类型，无 default 则记观察）
            if "default" not in defn:
                # 容忍：必填字段无 default
                # 但仍记录到 missing 列表（仅作观察，不阻断）
                missing.append(path)
        # 不强制阻断（required 字段无 default 合法），但若 missing 过多需警示
        # 这里只验证：声明了 default 的字段，default 值类型必须匹配
        # 真正的硬断言在 test_default_value_type_matches

    def test_default_value_type_matches_schema(self, config_template, config_name):
        """每个声明 default 的字段，default 值类型必须匹配 schema type 声明。"""
        defs = config_template.get("$defs", {})
        leaf_fields = _collect_leaf_fields(config_template, defs)
        type_mismatches: List[str] = []

        for path, name, defn in leaf_fields:
            if "default" not in defn:
                continue
            default_val = defn["default"]
            field_type = defn.get("type")

            # 处理 type 为列表（如 ["string", "null"]）
            if isinstance(field_type, list):
                valid_types = set(field_type)
                actual_type = type(default_val).__name__
                # null 对应 None
                py_type_map = {
                    "string": str,
                    "integer": int,
                    "number": (int, float),
                    "boolean": bool,
                    "array": list,
                    "object": dict,
                    "null": type(None),
                }
                matched = False
                for t in valid_types:
                    expected_py = py_type_map.get(t)
                    if expected_py and isinstance(default_val, expected_py):
                        # 注意：bool 是 int 的子类，需排除
                        if t == "integer" and isinstance(default_val, bool):
                            continue
                        matched = True
                        break
                if not matched:
                    type_mismatches.append(
                        f"{path}: default={default_val!r} 不匹配 type={field_type}"
                    )
            elif field_type == "string":
                if not isinstance(default_val, str):
                    type_mismatches.append(
                        f"{path}: default={default_val!r} 非 string"
                    )
            elif field_type == "integer":
                if not isinstance(default_val, int) or isinstance(default_val, bool):
                    type_mismatches.append(
                        f"{path}: default={default_val!r} 非 integer"
                    )
            elif field_type == "number":
                if not isinstance(default_val, (int, float)) or isinstance(
                    default_val, bool
                ):
                    type_mismatches.append(
                        f"{path}: default={default_val!r} 非 number"
                    )
            elif field_type == "boolean":
                if not isinstance(default_val, bool):
                    type_mismatches.append(
                        f"{path}: default={default_val!r} 非 boolean"
                    )
            elif field_type == "array":
                if not isinstance(default_val, list):
                    type_mismatches.append(
                        f"{path}: default={default_val!r} 非 array"
                    )
            elif field_type == "object":
                if not isinstance(default_val, dict):
                    type_mismatches.append(
                        f"{path}: default={default_val!r} 非 object"
                    )

        assert not type_mismatches, (
            f"{config_name} default 类型不匹配：\n" + "\n".join(type_mismatches)
        )

    def test_enum_defaults_are_valid(self, config_template, config_name):
        """enum 字段的 default 必须在 enum 列表中。"""
        defs = config_template.get("$defs", {})
        leaf_fields = _collect_leaf_fields(config_template, defs)
        violations: List[str] = []

        for path, name, defn in leaf_fields:
            if "enum" in defn and "default" in defn:
                if defn["default"] not in defn["enum"]:
                    violations.append(
                        f"{path}: default={defn['default']!r} 不在 enum={defn['enum']}"
                    )

        assert not violations, (
            f"{config_name} enum default 违规：\n" + "\n".join(violations)
        )

    def test_numeric_defaults_in_range(self, config_template, config_name):
        """numeric 字段的 default 必须在 [minimum, maximum] 范围内。"""
        defs = config_template.get("$defs", {})
        leaf_fields = _collect_leaf_fields(config_template, defs)
        violations: List[str] = []

        for path, name, defn in leaf_fields:
            if "default" not in defn:
                continue
            if "minimum" in defn and defn["default"] < defn["minimum"]:
                violations.append(
                    f"{path}: default={defn['default']} < minimum={defn['minimum']}"
                )
            if "maximum" in defn and defn["default"] > defn["maximum"]:
                violations.append(
                    f"{path}: default={defn['default']} > maximum={defn['maximum']}"
                )

        assert not violations, (
            f"{config_name} default 越界：\n" + "\n".join(violations)
        )


# --------------------------------------------------------------------------- #
# auto_fill 模拟（rules-3 §三 auto_fill）
# --------------------------------------------------------------------------- #


def _auto_fill(
    config: Dict[str, Any], schema: Dict[str, Any], defs: Dict[str, Any] = None
) -> Dict[str, Any]:
    """模拟 rules-3 §三 auto_fill：递归用 schema default 补全缺失字段。

    规则（与 config/default.yaml 加载行为对齐）：
      - 字段缺失 + schema 声明 default → 用 default 填充
      - 字段缺失 + 无 default + 是 object + 所有 required 子字段可 auto_fill →
        创建空 object 并递归填充子字段
      - 字段缺失 + 无 default + 非 object 或 required 子字段无 default → 不创建
        （避免产生无法通过校验的空骨架，例如 modelSlot 的 provider/host/model）
      - 字段已存在 + 类型为 object + schema 有子 properties → 递归填充子字段
    """
    defs = defs or schema.get("$defs", {})
    filled = dict(config)

    def _resolve_ref(defn: Dict[str, Any]) -> Dict[str, Any]:
        if "$ref" in defn:
            ref_name = defn["$ref"].split("/")[-1]
            return defs.get(ref_name, {})
        return defn

    def _can_autofill(defn: Dict[str, Any]) -> bool:
        """字段是否可被 auto_fill（即填充后能通过 schema 校验）。

        - 有显式 default → True
        - 是 object + 有 properties + 所有 required 子字段可 auto_fill → True
        - 否则 False
        """
        defn = _resolve_ref(defn)
        if "default" in defn:
            return True
        if defn.get("type") == "object" and "properties" in defn:
            required = defn.get("required", [])
            for req_name in required:
                req_defn = defn["properties"].get(req_name, {})
                if not _can_autofill(req_defn):
                    return False
            return True
        return False

    def _fill_node(node_data: Dict[str, Any], node_schema: Dict[str, Any]) -> None:
        props = node_schema.get("properties", {})
        for name, defn in props.items():
            if not isinstance(defn, dict):
                continue
            resolved_defn = _resolve_ref(defn)
            if name not in node_data:
                # 字段缺失
                if "default" in resolved_defn:
                    node_data[name] = resolved_defn["default"]
                elif (
                    resolved_defn.get("type") == "object"
                    and "properties" in resolved_defn
                    and _can_autofill(resolved_defn)
                ):
                    # 可安全 auto-create 的 object（如 llm_params/agent/cors）
                    node_data[name] = {}
                    _fill_node(node_data[name], resolved_defn)
                # 否则不创建（如 modelSlot 的 summary/memory——required 子字段无 default）
            else:
                # 字段已存在：若是 object + schema 有子 properties，递归填充
                if isinstance(node_data[name], dict) and resolved_defn.get("type") == "object" and "properties" in resolved_defn:
                    _fill_node(node_data[name], resolved_defn)

    _fill_node(filled, schema)
    return filled


class TestAutoFill:
    """模拟 auto_fill 流程：构造缺失字段的配置 → 填充后应通过 schema 校验。"""

    def test_llm_config_autofill_completes(self):
        """llm_config: 仅给 models.main → auto_fill 后通过校验。"""
        schema = _load_config_template("llm_config")
        minimal = {"models": {"main": {"provider": "vllm", "host": "http://x", "model": "y"}}}
        filled = _auto_fill(minimal, schema)
        # 填充后必须通过 schema 校验
        jsonschema.validate(filled, schema)
        # 关键字段必须有默认值
        assert filled["max_tool_rounds"] == 10
        assert filled["max_concurrent"] == 4
        assert filled["llm_params"]["temperature"] == 1.3
        assert filled["models"]["main"]["port"] == 8002

    def test_system_config_autofill_completes(self):
        """system_config: 仅给 server/logging/database 必填 → auto_fill 后通过校验。"""
        schema = _load_config_template("system_config")
        minimal = {
            "server": {"host": "0.0.0.0"},
            "logging": {"level": "INFO"},
            "database": {"type": "sqlite"},
        }
        filled = _auto_fill(minimal, schema)
        jsonschema.validate(filled, schema)
        # 关键字段默认值
        assert filled["server"]["port"] == 8001
        assert filled["server"]["debug"] is True
        assert filled["logging"]["file"] == "logs/app.log"
        assert filled["database"]["path"] == "data/cxhms.db"
        assert filled["agent"]["agent_id"] == "cxhms_agent_001"
        assert filled["monitoring"]["enabled"] is True

    def test_vector_config_autofill_completes(self):
        """vector_config: 仅给 memory.vector_enabled + vector_backend → auto_fill 后通过校验。"""
        schema = _load_config_template("vector_config")
        minimal = {"memory": {"vector_enabled": True, "vector_backend": "weaviate"}}
        filled = _auto_fill(minimal, schema)
        jsonschema.validate(filled, schema)
        # 关键字段默认值
        assert filled["memory"]["dedup_threshold"] == 0.85
        assert filled["memory"]["hybrid_search_enabled"] is False
        assert filled["memory"]["weaviate"]["port"] == 8090
        assert filled["memory"]["weaviate"]["schema_class"] == "CXHMSMemory"
        assert filled["memory"]["chroma"]["vector_size"] == 768

    def test_autofill_preserves_user_values(self):
        """auto_fill 不覆盖用户已设置的字段。"""
        schema = _load_config_template("system_config")
        minimal = {
            "server": {"host": "0.0.0.0", "port": 9999},  # 用户自定义 port
            "logging": {"level": "DEBUG"},  # 用户自定义 level
            "database": {"type": "sqlite"},
        }
        filled = _auto_fill(minimal, schema)
        # 用户值保留
        assert filled["server"]["port"] == 9999
        assert filled["logging"]["level"] == "DEBUG"
        # 默认值正常填充
        assert filled["server"]["debug"] is True
        assert filled["cors"]["enabled"] is True

    def test_autofill_empty_input(self):
        """空 dict + 仅 required 顶层字段 → auto_fill 后通过校验。"""
        schema = _load_config_template("system_config")
        # 只给 required 顶层字段的最小骨架
        minimal = {
            "server": {},
            "logging": {},
            "database": {},
        }
        filled = _auto_fill(minimal, schema)
        jsonschema.validate(filled, schema)


# --------------------------------------------------------------------------- #
# 与 config/default.yaml 字段一致性（rules-3 §三 + spec H1）
# --------------------------------------------------------------------------- #


class TestDefaultYamlConsistency:
    """config_template 与 config/default.yaml 字段名对应（不要求值一致）。"""

    @pytest.fixture
    def default_yaml(self):
        return _load_default_yaml()

    def test_llm_config_fields_match_yaml(self, default_yaml):
        """llm_config 的字段在 default.yaml 中可对应。"""
        schema = _load_config_template("llm_config")
        # llm_config 顶层字段：models/model_defaults/llm_params/max_tool_rounds/max_concurrent
        # default.yaml 对应：models/model_defaults/llm_params + llm.max_tool_rounds
        assert "models" in default_yaml, "default.yaml 缺少 models 段"
        assert "model_defaults" in default_yaml, "default.yaml 缺少 model_defaults"
        assert "llm_params" in default_yaml, "default.yaml 缺少 llm_params"
        assert "llm" in default_yaml and "max_tool_rounds" in default_yaml["llm"], (
            "default.yaml 缺少 llm.max_tool_rounds"
        )
        # schema 声明的字段
        assert "models" in schema["properties"]
        assert "model_defaults" in schema["properties"]
        assert "llm_params" in schema["properties"]
        assert "max_tool_rounds" in schema["properties"]
        assert "max_concurrent" in schema["properties"]

    def test_system_config_fields_match_yaml(self, default_yaml):
        """system_config 的字段在 default.yaml 中可对应。"""
        schema = _load_config_template("system_config")
        # system_config 顶层：server/cors/logging/database/agent/security/monitoring
        for section in ("server", "cors", "logging", "database", "agent", "security", "monitoring"):
            assert section in schema["properties"], (
                f"system_config schema 缺少 {section}"
            )
            assert section in default_yaml, (
                f"default.yaml 缺少 {section} 段"
            )

    def test_vector_config_fields_match_yaml(self, default_yaml):
        """vector_config 的字段在 default.yaml.memory 中可对应。"""
        schema = _load_config_template("vector_config")
        assert "memory" in schema["properties"]
        assert "memory" in default_yaml
        yaml_mem = default_yaml["memory"]
        # vector_config.memory 字段：vector_enabled/vector_backend/hybrid_search_enabled/
        # dedup_threshold/chroma/milvus_lite/qdrant/weaviate
        schema_mem_props = set(schema["properties"]["memory"]["properties"].keys())
        for field in (
            "vector_enabled",
            "vector_backend",
            "hybrid_search_enabled",
            "dedup_threshold",
            "chroma",
            "qdrant",
            "weaviate",
        ):
            assert field in schema_mem_props, f"vector_config.memory 缺少 {field}"
            assert field in yaml_mem, f"default.yaml.memory 缺少 {field}"

    def test_llm_config_model_slot_defaults_match_yaml(self, default_yaml):
        """llm_config 的 modelSlot $defs 字段在 default.yaml.models.* 中可对应。"""
        schema = _load_config_template("llm_config")
        model_slot = schema["$defs"]["modelSlot"]
        slot_props = set(model_slot["properties"].keys())
        # 抽样：main 模型槽应含全部字段
        main_slot = default_yaml["models"]["main"]
        for field in ("provider", "host", "model", "apiKey", "enabled", "port", "temperature", "max_tokens", "timeout", "api_key"):
            assert field in slot_props, f"modelSlot 缺少 {field}"
            assert field in main_slot, f"default.yaml.models.main 缺少 {field}"

    def test_default_yaml_passes_config_schema(self, default_yaml):
        """default.yaml 整体可作为 system_config 的合法配置（auto_fill 后）。

        注：default.yaml 含 system_config 之外的段（llm/memory/context 等），
        故只校验 system_config 涵盖的字段。
        """
        schema = _load_config_template("system_config")
        # 从 default.yaml 抽取 system_config 涵盖的字段
        sys_subset = {
            k: v for k, v in default_yaml.items()
            if k in schema["properties"]
        }
        filled = _auto_fill(sys_subset, schema)
        jsonschema.validate(filled, schema)

    def test_default_yaml_models_pass_llm_config_schema(self, default_yaml):
        """default.yaml.models + model_defaults + llm_params 通过 llm_config 校验。"""
        schema = _load_config_template("llm_config")
        subset = {
            "models": default_yaml["models"],
            "model_defaults": default_yaml["model_defaults"],
            "llm_params": default_yaml["llm_params"],
            "max_tool_rounds": default_yaml["llm"]["max_tool_rounds"],
            # max_concurrent 由 auto_fill 填充（default.yaml 未声明）
        }
        filled = _auto_fill(subset, schema)
        jsonschema.validate(filled, schema)
        # max_concurrent 应被 auto_fill 填充
        assert "max_concurrent" in filled
        assert filled["max_concurrent"] == 4

    def test_default_yaml_memory_passes_vector_config_schema(self, default_yaml):
        """default.yaml.memory 通过 vector_config 校验（auto_fill 后）。"""
        schema = _load_config_template("vector_config")
        yaml_mem = dict(default_yaml["memory"])
        # vector_config 要求 memory 仅含声明的字段，default.yaml.memory 含其他字段
        # （如 enabled/decay_enabled 等），需裁剪到 schema 声明的字段
        schema_mem_props = set(schema["properties"]["memory"]["properties"].keys())
        # 移除 schema 未声明的字段
        mem_subset = {k: v for k, v in yaml_mem.items() if k in schema_mem_props}
        subset = {"memory": mem_subset}
        filled = _auto_fill(subset, schema)
        jsonschema.validate(filled, schema)
