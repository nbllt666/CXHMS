"""模块11 独立知识库三层契约测试套件。

对应 rules-3 §五（契约可验证性：数据契约 / 接口契约 / 配置契约 / 预生成 Mock
+ 契约变更日志）。本测试纯契约校验，**不导入 backend 实现**（仅读取文件与 AST）。

运行方式：
    python -m pytest tests/contract/knowledge_contract_test.py -q

覆盖断言：
1. knowledge.json：可解析、Draft7Validator.check_schema 通过、6 个 definitions、
   error_codes 含 8 个错误码、三类实体样例均可各自通过校验。
2. knowledge_service.pyi：KnowledgeManager 恰好 11 个类签名（含 __init__）、
   方法名/参数名/async 标记与冻结签名一致；顶层无 KnowledgeParser / ASRClient /
   ParseResult 类；7 个异常类存在且类体无 FunctionDef；模块级 parse 存在。
3. knowledge_config.json：键集与冻结表完全相等、每个 property 有 default、
   additionalProperties=false。
4. mock_knowledge_service.py：文件存在、AST 含 MockKnowledgeService、10 个公开方法。
5. CHANGELOG.md：含 [1.3.0] 与 knowledge.json。
6. modules/模块11_独立知识库/AGENTS.md：文件存在且含关键规则段。

约束：public/ 受保护，本测试只读不写。
"""

import ast
import json

import jsonschema
import pytest

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PUBLIC_DIR = _PROJECT_ROOT / "public"

_SCHEMA_FILE = _PUBLIC_DIR / "schema" / "knowledge.json"
_STUB_FILE = _PUBLIC_DIR / "interface_stub" / "knowledge_service.pyi"
_CONFIG_FILE = _PUBLIC_DIR / "config_template" / "knowledge_config.json"
_MOCK_FILE = _PUBLIC_DIR / "pre_generated_mock" / "mock_knowledge_service.py"
_CHANGELOG_FILE = _PUBLIC_DIR / "schema" / "CHANGELOG.md"
_MODULE_AGENTS_FILE = _PROJECT_ROOT / "modules" / "模块11_独立知识库" / "AGENTS.md"


# --------------------------------------------------------------------------- #
# 冻结口径（与 spec「冻结的 KnowledgeManager 签名集 / 冻结的配置字段表」一致）
# --------------------------------------------------------------------------- #

EXPECTED_DEFINITIONS = {
    "parse_status",
    "item_type",
    "error_codes",
    "knowledge_document",
    "knowledge_item",
    "knowledge_search_hit",
}

EXPECTED_ERROR_CODES = {
    "KNOWLEDGE_ERROR",
    "KNOWLEDGE_VALIDATION_ERROR",
    "KNOWLEDGE_PARSE_FAILED",
    "KNOWLEDGE_UNSUPPORTED_MIME",
    "KNOWLEDGE_STORE_UNAVAILABLE",
    "KNOWLEDGE_ASR_UNAVAILABLE",
    "KNOWLEDGE_FFMPEG_UNAVAILABLE",
    "KNOWLEDGE_MEDIA_TOO_LONG",
}

# 方法名 -> (参数名元组（不含 self）, 是否 async)
EXPECTED_MANAGER_SIGNATURES = {
    "__init__": (("agent_id", "config", "embedding_model", "vector_index"), False),
    "add_document": (("filename", "mime", "data", "source_path", "tags", "title"), True),
    "add_experience": (("title", "content", "tags", "importance"), True),
    "search": (("query", "top_k", "tags", "item_type"), True),
    "list_items": (("item_type", "tags", "q", "limit", "offset"), False),
    "get_item": (("item_id",), False),
    "delete_item": (("item_id",), True),
    "list_documents": (("limit", "offset"), False),
    "get_document": (("document_id",), False),
    "delete_document": (("document_id",), True),
    "health": ((), False),
}

EXPECTED_EXCEPTION_CLASSES = {
    "KnowledgeError",
    "KnowledgeValidationError",
    "KnowledgeParseError",
    "KnowledgeUnsupportedMediaError",
    "KnowledgeStoreError",
    "KnowledgeASRUnavailableError",
    "KnowledgeFFmpegUnavailableError",
}

FORBIDDEN_TOP_LEVEL_CLASSES = {"KnowledgeParser", "ASRClient", "ParseResult"}

EXPECTED_CONFIG_DEFAULTS = {
    "enabled": True,
    "db_dir": "data",
    "db_filename_prefix": "knowledge",
    "files_dir": "data/knowledge_files",
    "collection_prefix": "CXHMSKnowledge",
    "max_document_size_mb": 20,
    "max_media_size_mb": 200,
    "allowed_document_mimes": [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
        "text/markdown",
    ],
    "allowed_image_mimes": ["image/png", "image/jpeg", "image/webp", "image/bmp"],
    "allowed_audio_mimes": [
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/mp4",
        "audio/flac",
        "audio/ogg",
        "audio/aac",
        "audio/opus",
    ],
    "allowed_video_mimes": [
        "video/mp4",
        "video/quicktime",
        "video/x-matroska",
        "video/webm",
        "video/x-msvideo",
        "video/x-flv",
    ],
    "chunk_size": 800,
    "chunk_overlap": 120,
    "max_chunks_per_document": 2000,
    "parse_max_workers": 2,
    "asr_provider": "faster_whisper",
    "asr_model": "small",
    "asr_device": "auto",
    "asr_compute_type": "int8",
    "asr_language": "zh",
    "asr_download_root": "data/models/faster_whisper",
    "asr_base_url": "",
    "asr_api_key": "",
    "asr_timeout_seconds": 600,
    "ffmpeg_path": "",
    "ffmpeg_fallback_to_imageio": True,
    "ffmpeg_audio_sample_rate": 16000,
    "video_frame_interval_seconds": 10,
    "video_max_frames": 12,
    "max_media_duration_seconds": 3600,
    "vector_enabled": True,
    "vector_top_k_default": 8,
    "vector_top_k_max": 50,
    "vector_rrf_k": 60,
    "fts_enabled": True,
    "fts_fallback_like": True,
    "search_top_k_default": 8,
    "search_top_k_max": 50,
    "preview_chars": 500,
}

EXPECTED_MOCK_METHODS = {
    "add_document",
    "add_experience",
    "search",
    "list_items",
    "get_item",
    "delete_item",
    "list_documents",
    "get_document",
    "delete_document",
    "health",
}

EXPECTED_MOCK_ASYNC_METHODS = {
    "add_document",
    "add_experience",
    "search",
    "delete_item",
    "delete_document",
}


# --------------------------------------------------------------------------- #
# 公共加载辅助
# --------------------------------------------------------------------------- #


def _load_json(path: Path) -> dict:
    """加载 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_text(path: Path) -> str:
    """加载文本文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_stub() -> ast.Module:
    """用 AST 解析 .pyi 存根（不执行、不导入）。"""
    return ast.parse(_load_text(_STUB_FILE))


def _class_by_name(module: ast.Module, name: str) -> ast.ClassDef:
    """按名字取顶层类节点。"""
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError("顶层未找到类: {0}".format(name))


def _method_params(node: ast.AST) -> tuple:
    """提取方法/函数参数名（不含 self），跳过 posonly/普通/keyword-only 三类。"""
    names = []
    for arg in list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs):
        if arg.arg != "self":
            names.append(arg.arg)
    return tuple(names)


# --------------------------------------------------------------------------- #
# 1. 数据契约
# --------------------------------------------------------------------------- #


def test_schema_is_valid_draft7():
    """knowledge.json 可解析且通过 Draft-07 meta-schema 校验。"""
    schema = _load_json(_SCHEMA_FILE)
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["version"] == "1.0.0"
    assert schema["type"] == "object"
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_has_six_definitions():
    """knowledge.json 含 6 个 definitions，且与冻结口径一致。"""
    schema = _load_json(_SCHEMA_FILE)
    definitions = set(schema["definitions"].keys())
    assert definitions == EXPECTED_DEFINITIONS


def test_schema_parse_status_and_item_type_enums():
    """parse_status / item_type 枚举值与冻结口径一致。"""
    schema = _load_json(_SCHEMA_FILE)
    assert schema["definitions"]["parse_status"]["enum"] == [
        "pending",
        "parsing",
        "parsed",
        "failed",
        "unsupported",
    ]
    assert schema["definitions"]["item_type"]["enum"] == ["doc_chunk", "experience"]


def test_schema_error_codes_eight_codes():
    """definitions.error_codes 恰含 8 个错误码，且每个码有非空描述。"""
    schema = _load_json(_SCHEMA_FILE)
    error_codes = schema["definitions"]["error_codes"]["properties"]
    assert set(error_codes.keys()) == EXPECTED_ERROR_CODES
    for code, spec in error_codes.items():
        assert spec["type"] == "string", code
        assert spec.get("description"), code


def test_schema_entities_validate():
    """三类实体样例可各自通过顶层 oneOf 校验。"""
    schema = _load_json(_SCHEMA_FILE)
    validator = jsonschema.Draft7Validator(schema)

    sha256_hex = "a" * 64
    document = {
        "document_id": "doc-001",
        "agent_id": "default",
        "filename": "spec.pdf",
        "mime": "application/pdf",
        "size_bytes": 1024,
        "sha256": sha256_hex,
        "parse_status": "parsed",
        "created_at": "2026-11-01T00:00:00+00:00",
        "storage_path": "/data/knowledge_files/default/doc-001.pdf",
        "parse_error": None,
        "metadata": {"pages": 3},
        "updated_at": None,
        "is_deleted": 0,
    }
    item = {
        "item_id": "item-001",
        "agent_id": "default",
        "item_type": "experience",
        "content": "可复用结论：先冻结契约再并行开发。",
        "fingerprint": "b" * 32,
        "created_at": "2026-11-01T00:00:00+00:00",
        "document_id": None,
        "title": "工程经验",
        "tags": ["契约", "并行"],
        "importance": 4,
        "chunk_index": None,
        "updated_at": None,
        "is_deleted": 0,
    }
    hit = dict(item)
    hit["item_id"] = "item-002"
    hit["score"] = 0.87

    for sample in (document, item, hit):
        errors = sorted(validator.iter_errors(sample), key=lambda e: e.path)
        assert errors == [], sample["item_id" if "item_id" in sample else "document_id"]


def test_schema_rejects_invalid_document():
    """非法文档（缺少必填字段 + 非法 parse_status）必须被拒绝。"""
    schema = _load_json(_SCHEMA_FILE)
    validator = jsonschema.Draft7Validator(schema)
    invalid = {
        "document_id": "doc-bad",
        "agent_id": "default",
        "filename": "bad.txt",
        "mime": "text/plain",
        "size_bytes": 1,
        "sha256": "c" * 64,
        "parse_status": "unknown",
        "created_at": "2026-11-01T00:00:00+00:00",
    }
    assert list(validator.iter_errors(invalid)) != []


# --------------------------------------------------------------------------- #
# 2. 接口契约（.pyi）
# --------------------------------------------------------------------------- #


def test_stub_manager_has_exactly_eleven_signatures():
    """KnowledgeManager 恰好 11 个类签名（含 __init__），方法名与冻结集一致。"""
    module = _parse_stub()
    manager = _class_by_name(module, "KnowledgeManager")
    functions = [n for n in manager.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert len(functions) == 11
    assert set(n.name for n in functions) == set(EXPECTED_MANAGER_SIGNATURES.keys())


def test_stub_manager_params_and_async_marks():
    """每个方法的参数名与 async 标记与冻结签名一致。"""
    module = _parse_stub()
    manager = _class_by_name(module, "KnowledgeManager")
    for node in manager.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        expected_params, expected_async = EXPECTED_MANAGER_SIGNATURES[node.name]
        assert _method_params(node) == expected_params, node.name
        assert isinstance(node, ast.AsyncFunctionDef) is expected_async, node.name


def test_stub_top_level_classes_scope():
    """顶层类集合 = KnowledgeManager + 7 个异常类；禁止 KnowledgeParser / ASRClient / ParseResult。"""
    module = _parse_stub()
    class_names = {n.name for n in module.body if isinstance(n, ast.ClassDef)}
    assert class_names == {"KnowledgeManager"} | EXPECTED_EXCEPTION_CLASSES
    assert class_names & FORBIDDEN_TOP_LEVEL_CLASSES == set()


def test_stub_exception_classes_have_no_methods():
    """7 个异常类只写类头 + ...，类体不含任何函数定义。"""
    module = _parse_stub()
    for name in EXPECTED_EXCEPTION_CLASSES:
        node = _class_by_name(module, name)
        assert not any(
            isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) for stmt in node.body
        ), name
        assert len(node.body) == 1, name
        assert isinstance(node.body[0], ast.Expr), name
        assert isinstance(node.body[0].value, ast.Constant), name
        assert node.body[0].value.value is Ellipsis, name


def test_stub_module_level_parse_function():
    """模块级 parse 存在，参数与返回前向引用 "ParseResult" 符合冻结口径。"""
    module = _parse_stub()
    parse_nodes = [
        n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "parse"
    ]
    assert len(parse_nodes) == 1
    parse_node = parse_nodes[0]
    assert isinstance(parse_node, ast.FunctionDef)
    assert _method_params(parse_node) == ("source_path", "filename", "mime", "config")
    assert isinstance(parse_node.returns, ast.Constant)
    assert parse_node.returns.value == "ParseResult"


# --------------------------------------------------------------------------- #
# 3. 配置契约
# --------------------------------------------------------------------------- #


def test_config_keys_and_defaults_exact():
    """配置键集与冻结表完全相等，且每个 property 的 default 与冻结默认值一致。"""
    config = _load_json(_CONFIG_FILE)
    properties = config["properties"]
    assert set(properties.keys()) == set(EXPECTED_CONFIG_DEFAULTS.keys())
    for key, spec in properties.items():
        assert "default" in spec, "缺少 default: {0}".format(key)
        assert spec["default"] == EXPECTED_CONFIG_DEFAULTS[key], key


def test_config_additional_properties_false():
    """配置契约禁止未知键。"""
    config = _load_json(_CONFIG_FILE)
    assert config["additionalProperties"] is False
    jsonschema.Draft7Validator.check_schema(config)


# --------------------------------------------------------------------------- #
# 4. 预生成 Mock
# --------------------------------------------------------------------------- #


def test_mock_file_exists_and_class_present():
    """Mock 文件存在、含 MockKnowledgeService 类、10 个公开方法。"""
    assert _MOCK_FILE.is_file()
    module = ast.parse(_load_text(_MOCK_FILE))
    mock_class = _class_by_name(module, "MockKnowledgeService")

    functions = [
        n
        for n in mock_class.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    ]
    assert set(n.name for n in functions) == EXPECTED_MOCK_METHODS

    for node in functions:
        assert isinstance(node, ast.AsyncFunctionDef) is (node.name in EXPECTED_MOCK_ASYNC_METHODS), node.name


def test_mock_does_not_import_backend_or_jsonschema():
    """Mock 不导入 backend 实现、不依赖 jsonschema（保持替身自包含）。"""
    module = ast.parse(_load_text(_MOCK_FILE))
    imported = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    assert "backend" not in imported
    assert "jsonschema" not in imported


# --------------------------------------------------------------------------- #
# 5. 契约变更日志与模块规则
# --------------------------------------------------------------------------- #


def test_changelog_has_1_3_0_entry():
    """CHANGELOG 含 [1.3.0] 条目且引用 knowledge.json。"""
    text = _load_text(_CHANGELOG_FILE)
    assert "## [1.3.0] - 2026-11-01" in text
    assert "knowledge.json" in text


def test_module_agents_exists_with_required_sections():
    """模块11 AGENTS.md 存在且含优先级/上下文保留/public 保护/三段交接。"""
    assert _MODULE_AGENTS_FILE.is_file()
    text = _load_text(_MODULE_AGENTS_FILE)
    for marker in (
        "最高优先级规则",
        "上下文保留规则",
        "public/",
        "知识库",
        "三段交接",
    ):
        assert marker in text, marker
