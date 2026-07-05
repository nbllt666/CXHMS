"""配置契约默认值填充测试。

校验 public/config_template/*.json：
- 文件存在且为合法 JSON Schema (draft-07+)
- 关键字段含 default 值
- 配置加载时自动补充缺失字段（auto_fill 行为模拟）

执行：python -m pytest public/test_cases/test_config_template.py -v
降级：python public/test_cases/test_config_template.py
"""

import os

import pytest

from .conftest import CONFIG_DIR, load_json, try_jsonschema

jsonschema = try_jsonschema()

# jsonschema 是配置契约验证的硬依赖（rules-3 §五 test_suite.requirement）
pytestmark = pytest.mark.skipif(
    jsonschema is None,
    reason="jsonschema 未安装；配置契约约束验证不可降级。安装：pip install jsonschema（见 public/dependencies/requirements.txt）",
)


def _collect_defaults(schema: dict, prefix: str = "") -> dict:
    """递归收集 schema 中所有带 default 的字段路径。"""
    defaults = {}
    props = schema.get("properties", {})
    for name, sub in props.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(sub, dict) and "default" in sub:
            defaults[path] = sub["default"]
        if isinstance(sub, dict) and "properties" in sub:
            defaults.update(_collect_defaults(sub, path))
    return defaults


def _auto_fill(schema: dict, instance: dict) -> dict:
    """模拟配置加载自动补充缺失字段为默认值。"""
    props = schema.get("properties", {})
    for name, sub in props.items():
        if isinstance(sub, dict) and "default" in sub:
            instance.setdefault(name, sub["default"])
        if isinstance(sub, dict) and "properties" in sub and isinstance(instance.get(name), dict):
            _auto_fill(sub, instance[name])
    return instance


# ---------- 文件存在性 ----------

def test_llm_config_exists():
    path = os.path.join(CONFIG_DIR, "llm_config.json")
    assert os.path.exists(path), "llm_config.json 缺失"
    schema = load_json(path)
    assert schema.get("type") == "object"
    assert "models" in schema.get("properties", {})


def test_vector_config_exists():
    path = os.path.join(CONFIG_DIR, "vector_config.json")
    assert os.path.exists(path), "vector_config.json 缺失"
    schema = load_json(path)
    assert "memory" in schema.get("properties", {})


def test_system_config_exists():
    path = os.path.join(CONFIG_DIR, "system_config.json")
    assert os.path.exists(path), "system_config.json 缺失"
    schema = load_json(path)
    assert "server" in schema.get("properties", {})
    assert "logging" in schema.get("properties", {})
    assert "database" in schema.get("properties", {})


# ---------- 默认值存在性 ----------

def test_system_config_has_defaults():
    schema = load_json(os.path.join(CONFIG_DIR, "system_config.json"))
    defaults = _collect_defaults(schema)
    assert "server.port" in defaults, "server.port 应有默认值"
    assert defaults["server.port"] == 8001
    assert "logging.level" in defaults, "logging.level 应有默认值"
    assert defaults["logging.level"] == "INFO"
    assert "database.type" in defaults, "database.type 应有默认值"


def test_llm_config_has_defaults():
    schema = load_json(os.path.join(CONFIG_DIR, "llm_config.json"))
    assert "max_tool_rounds" in schema.get("properties", {})
    assert schema["properties"]["max_tool_rounds"]["default"] == 10
    assert "max_concurrent" in schema.get("properties", {})
    assert schema["properties"]["max_concurrent"]["default"] == 4


def test_vector_config_has_defaults():
    schema = load_json(os.path.join(CONFIG_DIR, "vector_config.json"))
    defaults = _collect_defaults(schema)
    assert "memory.vector_backend" in defaults
    assert defaults["memory.vector_backend"] == "weaviate"
    assert "memory.weaviate.port" in defaults
    assert defaults["memory.weaviate.port"] == 8090


# ---------- 自动补充行为 ----------

def test_system_config_auto_fill():
    """空实例经 auto_fill 后应含 server.port=8001 与 logging.level=INFO。"""
    schema = load_json(os.path.join(CONFIG_DIR, "system_config.json"))
    instance = {"server": {}, "logging": {}, "database": {}}
    filled = _auto_fill(schema, instance)
    assert filled["server"]["port"] == 8001
    assert filled["logging"]["level"] == "INFO"
    assert filled["database"]["type"] == "sqlite"


def test_llm_config_auto_fill_top_level():
    """缺失 max_tool_rounds 时应被补充为 10。"""
    schema = load_json(os.path.join(CONFIG_DIR, "llm_config.json"))
    instance = {"models": {"main": {"provider": "vllm", "host": "h", "model": "m"}}}
    filled = _auto_fill(schema, instance)
    assert filled.get("max_tool_rounds") == 10
    assert filled.get("max_concurrent") == 4


def test_config_validates_against_schema():
    """auto_fill 后的实例应能通过 schema 校验。"""
    for name in ["system_config.json", "llm_config.json", "vector_config.json"]:
        schema = load_json(os.path.join(CONFIG_DIR, name))
        instance = {}
        if name == "system_config.json":
            instance = {"server": {}, "logging": {}, "database": {}}
        elif name == "llm_config.json":
            instance = {"models": {"main": {"provider": "vllm", "host": "h", "model": "m"}}}
        else:
            instance = {"memory": {"vector_enabled": True, "vector_backend": "weaviate"}}
        filled = _auto_fill(schema, instance)
        jsonschema.validate(instance=filled, schema=schema)


# ---------- 直接运行入口 ----------

if __name__ == "__main__":
    import traceback

    tests = [
        test_llm_config_exists, test_vector_config_exists, test_system_config_exists,
        test_system_config_has_defaults, test_llm_config_has_defaults,
        test_vector_config_has_defaults,
        test_system_config_auto_fill, test_llm_config_auto_fill_top_level,
        test_config_validates_against_schema,
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
