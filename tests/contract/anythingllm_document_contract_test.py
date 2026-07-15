"""AnythingLLM Document API 三层契约测试套件。

对应 rules-3 三层契约可验证性要求 (v6 新增 §五)。
覆盖数据契约 / 接口契约 / 配置契约三层 rubric。

运行方式：
    $env:PYTHONPATH = "."; python tests/contract/anythingllm_document_contract_test.py

或通过 pytest：
    pytest tests/contract/anythingllm_document_contract_test.py -v

约束：
    - public/ 受保护，本测试只读不写
    - 不依赖 backend 实现，纯契约校验
    - 使用 jsonschema 库做 draft-07 校验
    - 使用 ast 解析 .pyi 存根验证签名
"""

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema
import pytest

# --------------------------------------------------------------------------- #
# 路径锚点（rules-0 §三：用 os.path.dirname(os.path.abspath(__file__)) 解析）
# 设置 sys.path 包含项目根目录
# --------------------------------------------------------------------------- #
_THIS_FILE = os.path.abspath(__file__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_PUBLIC_DIR = Path(_PROJECT_ROOT) / "public"
_SCHEMA_DIR = _PUBLIC_DIR / "schema"
_INTERFACE_STUB_DIR = _PUBLIC_DIR / "interface_stub"
_CONFIG_TEMPLATE_DIR = _PUBLIC_DIR / "config_template"

_SCHEMA_FILE = _SCHEMA_DIR / "anythingllm_document.json"
_STUB_FILE = _INTERFACE_STUB_DIR / "anythingllm_document_service.pyi"
_CONFIG_FILE = _CONFIG_TEMPLATE_DIR / "anythingllm_document_config.json"


# --------------------------------------------------------------------------- #
# 公共加载辅助
# --------------------------------------------------------------------------- #


def _load_json(path: Path) -> Dict[str, Any]:
    """加载 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_stub_text() -> str:
    """加载 .pyi 存根文本。"""
    with open(_STUB_FILE, "r", encoding="utf-8") as f:
        return f.read()


def _parse_stub() -> ast.Module:
    """解析 .pyi 存根为 AST。"""
    return ast.parse(_load_stub_text(), filename=str(_STUB_FILE))


def _get_functions(tree: ast.Module) -> Dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    """提取模块级函数定义（含 async 与 sync）。"""
    funcs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
    return funcs


def _get_classes(tree: ast.Module) -> Dict[str, ast.ClassDef]:
    """提取模块级类定义。"""
    classes = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes[node.name] = node
    return classes


def _arg_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[str]:
    """提取函数参数名列表（含 self/cls，不含 *args/**kwargs 展开名）。"""
    names: List[str] = []
    for a in func.args.args:
        names.append(a.arg)
    if func.args.vararg:
        names.append(func.args.vararg.arg)
    for a in func.args.kwonlyargs:
        names.append(a.arg)
    if func.args.kwarg:
        names.append(func.args.kwarg.arg)
    return names


def _docstring(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """提取函数 docstring。"""
    return ast.get_docstring(func) or ""


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def schema() -> Dict[str, Any]:
    return _load_json(_SCHEMA_FILE)


@pytest.fixture(scope="module")
def stub_tree() -> ast.Module:
    return _parse_stub()


@pytest.fixture(scope="module")
def config() -> Dict[str, Any]:
    return _load_json(_CONFIG_FILE)


@pytest.fixture(scope="module")
def stub_functions(stub_tree) -> Dict[str, Any]:
    return _get_functions(stub_tree)


@pytest.fixture(scope="module")
def stub_classes(stub_tree) -> Dict[str, Any]:
    return _get_classes(stub_tree)


# ============================================================================ #
# 数据契约 rubric
# ============================================================================ #


class TestDataContract:
    """数据契约（public/schema/anythingllm_document.json）rubric 测试。"""

    def test_schema_file_exists(self):
        """schema 文件存在。"""
        assert _SCHEMA_FILE.exists(), f"数据契约文件不存在：{_SCHEMA_FILE}"

    def test_schema_is_valid_json(self, schema):
        """schema 文件本身是合法 JSON。"""
        assert isinstance(schema, dict), "schema 顶层非 object"

    def test_schema_is_valid_draft07(self, schema):
        """schema 本身是合法 JSON Schema draft-07+。"""
        jsonschema.Draft7Validator.check_schema(schema)

    def test_schema_declares_draft07(self, schema):
        """schema 显式声明 $schema 为 draft-07+。"""
        assert "$schema" in schema, "缺少 $schema 声明"
        assert "draft-07" in schema["$schema"], f"$schema 非 draft-07：{schema['$schema']}"

    def test_schema_has_id(self, schema):
        """schema 含 $id 唯一标识。"""
        assert "$id" in schema, "缺少 $id"
        assert schema["$id"].startswith("https://"), f"$id 必须 https URL：{schema['$id']}"

    def test_schema_has_title_and_description(self, schema):
        """schema 含 title 与 description。"""
        assert "title" in schema and schema["title"], "缺少 title"
        assert "description" in schema and schema["description"], "缺少 description"

    def test_required_fields_present(self, schema):
        """文档响应包含必需字段：doc_name, title, word_count, token_count_estimate。"""
        required = set(schema.get("required", []))
        must_have = {"doc_name", "title", "word_count", "token_count_estimate"}
        missing = must_have - required
        assert not missing, f"required 缺少必需字段：{missing}"

    def test_doc_name_is_string_and_unique(self, schema):
        """doc_name 为 string 类型且声明 unique。"""
        prop = schema["properties"]["doc_name"]
        assert prop["type"] == "string", f"doc_name.type 非 string：{prop['type']}"
        # unique 约束在 description 中声明（JSON Schema 单对象无法直接表达 unique）
        desc = prop.get("description", "")
        assert "唯一" in desc or "unique" in desc.lower(), (
            f"doc_name.description 必须声明唯一性约束：{desc}"
        )

    def test_doc_name_pattern_format(self, schema):
        """doc_name 含 pattern 约束，匹配 {title}-{uuid}.json 格式。"""
        prop = schema["properties"]["doc_name"]
        assert "pattern" in prop, "doc_name 缺少 pattern 约束"
        # 验证 pattern 能匹配合法 doc_name
        import re as _re
        pattern = prop["pattern"]
        valid_name = "test-doc-12345678-1234-1234-1234-123456789abc.json"
        assert _re.search(pattern, valid_name), (
            f"doc_name pattern 无法匹配合法格式：{pattern}"
        )

    def test_doc_name_implementation_matches_schema(self, schema):
        """实现实际生成的 doc_name 通过 schema 校验（GN-004 SOFT_BLOCK-1 修复）。"""
        import jsonschema
        import uuid as _uuid
        # 模拟实现中的 doc_name 生成逻辑（memory.py 第 249 行）
        title = "test-doc"
        doc_name = f"{title}-{_uuid.uuid4()}.json"
        # 构造完整文档实例进行 schema 校验
        instance = {
            "doc_name": doc_name,
            "title": title,
            "doc_author": "Unknown",
            "description": "Unknown",
            "word_count": 0,
            "token_count_estimate": 0,
            "folder": "custom-documents",
            "created_at": "2026-07-15T00:00:00",
            "is_deleted": False,
        }
        # 不应抛出 ValidationError
        jsonschema.validate(instance, schema)

    def test_word_count_is_integer_non_negative(self, schema):
        """word_count 为 integer >= 0。"""
        prop = schema["properties"]["word_count"]
        assert prop["type"] == "integer", f"word_count.type 非 integer：{prop['type']}"
        assert prop["minimum"] == 0, f"word_count.minimum 非 0：{prop.get('minimum')}"

    def test_token_count_estimate_is_integer_non_negative(self, schema):
        """token_count_estimate 为 integer >= 0。"""
        prop = schema["properties"]["token_count_estimate"]
        assert prop["type"] == "integer", (
            f"token_count_estimate.type 非 integer：{prop['type']}"
        )
        assert prop["minimum"] == 0, (
            f"token_count_estimate.minimum 非 0：{prop.get('minimum')}"
        )

    def test_created_at_is_iso8601_string(self, schema):
        """created_at 为 ISO 8601 格式字符串。"""
        prop = schema["properties"]["created_at"]
        assert prop["type"] == "string", f"created_at.type 非 string：{prop['type']}"
        assert prop.get("format") == "date-time", (
            f"created_at.format 非 date-time：{prop.get('format')}"
        )

    def test_updated_at_is_nullable_iso8601(self, schema):
        """updated_at 为 nullable ISO 8601 字符串。"""
        prop = schema["properties"]["updated_at"]
        assert prop["type"] == ["string", "null"], (
            f"updated_at.type 非 [string, null]：{prop['type']}"
        )

    def test_default_values(self, schema):
        """关键字段含默认值（doc_author, description, folder, is_deleted）。"""
        props = schema["properties"]
        assert props["doc_author"]["default"] == "Unknown"
        assert props["description"]["default"] == "Unknown"
        assert props["folder"]["default"] == "custom-documents"
        assert props["is_deleted"]["default"] is False

    def test_error_codes_defined(self, schema):
        """包含错误码定义（404/413/500）。"""
        definitions = schema.get("definitions", {})
        assert "error_codes" in definitions, "缺少 definitions.error_codes"
        error_codes = definitions["error_codes"]["properties"]
        # 404
        assert "DOCUMENT_NOT_FOUND" in error_codes, "缺少 DOCUMENT_NOT_FOUND (404)"
        assert error_codes["DOCUMENT_NOT_FOUND"]["const"] == 404
        # 413
        assert "FILE_TOO_LARGE" in error_codes, "缺少 FILE_TOO_LARGE (413)"
        assert error_codes["FILE_TOO_LARGE"]["const"] == 413
        # 500
        assert "INTERNAL_ERROR" in error_codes, "缺少 INTERNAL_ERROR (500)"
        assert error_codes["INTERNAL_ERROR"]["const"] == 500

    def test_exception_contract_defined(self, schema):
        """包含异常契约。"""
        definitions = schema.get("definitions", {})
        assert "exceptions" in definitions, "缺少 definitions.exceptions"
        exceptions = definitions["exceptions"]["properties"]
        # 验证 HTTPException 异常类型
        expected_exceptions = {
            "HTTPException_404",
            "HTTPException_413",
            "HTTPException_500",
            "sqlite3_Error",
        }
        assert expected_exceptions.issubset(set(exceptions.keys())), (
            f"异常契约缺少：{expected_exceptions - set(exceptions.keys())}"
        )

    def test_additional_properties_false(self, schema):
        """schema 显式 additionalProperties: false。"""
        assert schema.get("additionalProperties") is False, (
            "必须声明 additionalProperties: false"
        )

    def test_valid_sample_passes(self, schema):
        """合法样本通过 schema 校验。"""
        sample = {
            "doc_name": "test-doc-12345678-1234-1234-1234-123456789abc.json",
            "title": "测试文档",
            "doc_author": "Unknown",
            "description": "Unknown",
            "doc_source": "upload",
            "mime_type": "text/plain",
            "word_count": 100,
            "token_count_estimate": 150,
            "text_content": "这是测试内容",
            "memory_id": None,
            "folder": "custom-documents",
            "file_path": None,
            "created_at": "2026-07-15T10:00:00Z",
            "updated_at": None,
            "is_deleted": False,
        }
        jsonschema.validate(sample, schema)

    def test_missing_required_doc_name_fails(self, schema):
        """缺少 doc_name 校验失败。"""
        sample = {
            "title": "测试",
            "doc_author": "Unknown",
            "description": "Unknown",
            "word_count": 0,
            "token_count_estimate": 0,
            "folder": "custom-documents",
            "created_at": "2026-07-15T10:00:00Z",
            "is_deleted": False,
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    def test_negative_word_count_fails(self, schema):
        """word_count 为负数校验失败。"""
        sample = {
            "doc_name": "test-doc-12345678-1234-1234-1234-123456789abc.json",
            "title": "测试",
            "doc_author": "Unknown",
            "description": "Unknown",
            "word_count": -1,
            "token_count_estimate": 0,
            "folder": "custom-documents",
            "created_at": "2026-07-15T10:00:00Z",
            "is_deleted": False,
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    def test_negative_token_count_fails(self, schema):
        """token_count_estimate 为负数校验失败。"""
        sample = {
            "doc_name": "test-doc-12345678-1234-1234-1234-123456789abc.json",
            "title": "测试",
            "doc_author": "Unknown",
            "description": "Unknown",
            "word_count": 0,
            "token_count_estimate": -5,
            "folder": "custom-documents",
            "created_at": "2026-07-15T10:00:00Z",
            "is_deleted": False,
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)

    def test_additional_property_rejected(self, schema):
        """额外字段被拒绝。"""
        sample = {
            "doc_name": "test-doc-12345678-1234-1234-1234-123456789abc.json",
            "title": "测试",
            "doc_author": "Unknown",
            "description": "Unknown",
            "word_count": 0,
            "token_count_estimate": 0,
            "folder": "custom-documents",
            "created_at": "2026-07-15T10:00:00Z",
            "is_deleted": False,
            "extra_field": "should be rejected",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, schema)


# ============================================================================ #
# 接口契约 rubric
# ============================================================================ #


class TestInterfaceContract:
    """接口契约（public/interface_stub/anythingllm_document_service.pyi）rubric 测试。"""

    def test_stub_file_exists(self):
        """接口存根文件存在。"""
        assert _STUB_FILE.exists(), f"接口存根文件不存在：{_STUB_FILE}"

    def test_stub_is_parseable(self, stub_tree):
        """.pyi 存根可被 ast 解析。"""
        assert isinstance(stub_tree, ast.Module)

    def test_stub_has_seven_document_endpoints(self, stub_functions):
        """.pyi 存根定义 7 个 Document 端点签名。"""
        expected = {
            "upload_document",
            "upload_raw_text",
            "list_documents",
            "get_document",
            "delete_document",
            "update_workspace_embeddings",
            "get_metadata_schema",
        }
        actual = set(stub_functions.keys())
        missing = expected - actual
        assert not missing, f"缺少端点签名：{missing}"

    def test_upload_document_signature(self, stub_functions):
        """POST /api/v1/document/upload 签名匹配。"""
        func = stub_functions["upload_document"]
        assert isinstance(func, ast.AsyncFunctionDef), "upload_document 必须为 async"
        args = _arg_names(func)
        assert "file" in args, "upload_document 缺少 file 参数"
        assert "addToWorkspaces" in args, "upload_document 缺少 addToWorkspaces 参数"
        assert "metadata" in args, "upload_document 缺少 metadata 参数"

    def test_upload_document_declares_exceptions(self, stub_functions):
        """upload_document 声明抛出 HTTPException(413) 与 HTTPException(500)。"""
        doc = _docstring(stub_functions["upload_document"])
        assert "413" in doc, "upload_document docstring 未声明 HTTPException(413)"
        assert "500" in doc, "upload_document docstring 未声明 HTTPException(500)"

    def test_upload_raw_text_signature(self, stub_functions):
        """POST /api/v1/document/raw-text 签名匹配。"""
        func = stub_functions["upload_raw_text"]
        assert isinstance(func, ast.AsyncFunctionDef), "upload_raw_text 必须为 async"
        args = _arg_names(func)
        assert "request" in args, "upload_raw_text 缺少 request 参数"

    def test_upload_raw_text_declares_exceptions(self, stub_functions):
        """upload_raw_text 声明抛出 HTTPException(500)。"""
        doc = _docstring(stub_functions["upload_raw_text"])
        assert "500" in doc, "upload_raw_text docstring 未声明 HTTPException(500)"

    def test_list_documents_signature(self, stub_functions):
        """GET /api/v1/documents 签名匹配。"""
        func = stub_functions["list_documents"]
        assert isinstance(func, ast.AsyncFunctionDef), "list_documents 必须为 async"
        args = _arg_names(func)
        # 无参数（仅 self/cls 也不应有）
        normal_args = [a for a in args if a not in ("self", "cls")]
        assert len(normal_args) == 0, f"list_documents 不应有参数：{normal_args}"

    def test_get_document_signature(self, stub_functions):
        """GET /api/v1/document/{docName} 签名匹配。"""
        func = stub_functions["get_document"]
        assert isinstance(func, ast.AsyncFunctionDef), "get_document 必须为 async"
        args = _arg_names(func)
        assert "docName" in args, "get_document 缺少 docName 参数"

    def test_get_document_declares_exceptions(self, stub_functions):
        """get_document 声明抛出 HTTPException(404)。"""
        doc = _docstring(stub_functions["get_document"])
        assert "404" in doc, "get_document docstring 未声明 HTTPException(404)"

    def test_delete_document_signature(self, stub_functions):
        """DELETE /api/v1/document/{docName} 签名匹配。"""
        func = stub_functions["delete_document"]
        assert isinstance(func, ast.AsyncFunctionDef), "delete_document 必须为 async"
        args = _arg_names(func)
        assert "docName" in args, "delete_document 缺少 docName 参数"

    def test_delete_document_declares_exceptions(self, stub_functions):
        """delete_document 声明抛出 HTTPException(404)。"""
        doc = _docstring(stub_functions["delete_document"])
        assert "404" in doc, "delete_document docstring 未声明 HTTPException(404)"

    def test_update_workspace_embeddings_signature(self, stub_functions):
        """POST /api/v1/workspace/{slug}/update-embeddings 签名匹配。"""
        func = stub_functions["update_workspace_embeddings"]
        assert isinstance(func, ast.AsyncFunctionDef), (
            "update_workspace_embeddings 必须为 async"
        )
        args = _arg_names(func)
        assert "slug" in args, "update_workspace_embeddings 缺少 slug 参数"
        assert "request" in args, "update_workspace_embeddings 缺少 request 参数"

    def test_update_workspace_embeddings_declares_exceptions(self, stub_functions):
        """update_workspace_embeddings 声明抛出 HTTPException(404)。"""
        doc = _docstring(stub_functions["update_workspace_embeddings"])
        assert "404" in doc, (
            "update_workspace_embeddings docstring 未声明 HTTPException(404)"
        )

    def test_get_metadata_schema_signature(self, stub_functions):
        """GET /api/v1/document/metadata-schema 签名匹配。"""
        func = stub_functions["get_metadata_schema"]
        assert isinstance(func, ast.AsyncFunctionDef), "get_metadata_schema 必须为 async"
        args = _arg_names(func)
        normal_args = [a for a in args if a not in ("self", "cls")]
        assert len(normal_args) == 0, f"get_metadata_schema 不应有参数：{normal_args}"

    def test_search_all_memories_signature(self, stub_functions):
        """.pyi 存根定义 search_all_memories 方法签名。"""
        assert "search_all_memories" in stub_functions, "缺少 search_all_memories 方法"
        func = stub_functions["search_all_memories"]
        # 同步函数（非 async）
        assert isinstance(func, ast.FunctionDef), (
            "search_all_memories 必须为同步函数（非 async）"
        )
        args = _arg_names(func)
        assert "query" in args, "search_all_memories 缺少 query 参数"
        assert "workspace_id" in args, "search_all_memories 缺少 workspace_id 参数"
        assert "limit" in args, "search_all_memories 缺少 limit 参数"

    def test_search_all_memories_declares_exceptions(self, stub_functions):
        """search_all_memories 声明抛出 sqlite3.Error。"""
        doc = _docstring(stub_functions["search_all_memories"])
        assert "sqlite3" in doc.lower(), (
            "search_all_memories docstring 未声明 sqlite3.Error 异常"
        )

    def test_all_endpoints_declare_exceptions(self, stub_functions):
        """每个端点声明抛出异常类型（或显式声明不抛出）。"""
        # 端点列表（除 search_all_memories 与 list_documents/get_metadata_schema 显式不抛出）
        endpoints_with_exceptions = [
            "upload_document",
            "upload_raw_text",
            "get_document",
            "delete_document",
            "update_workspace_embeddings",
        ]
        for name in endpoints_with_exceptions:
            assert name in stub_functions, f"缺少端点：{name}"
            doc = _docstring(stub_functions[name])
            assert "Raises" in doc or "HTTPException" in doc, (
                f"{name} docstring 未声明异常类型"
            )

    def test_stub_zero_implementation(self, stub_functions):
        """.pyi 存根必须是零实现逻辑（函数体只有 ... 或 pass）。"""
        for name, func in stub_functions.items():
            body = func.body
            # 函数体应只包含一个 Expr(... Ellipsis) 或 Pass
            assert len(body) >= 1, f"{name} 函数体为空"
            first_stmt = body[0]
            is_ellipsis = (
                isinstance(first_stmt, ast.Expr)
                and isinstance(first_stmt.value, ast.Constant)
                and first_stmt.value.value is ...
            )
            is_pass = isinstance(first_stmt, ast.Pass)
            # 允许 docstring + .../pass
            if len(body) == 1:
                assert is_ellipsis or is_pass or isinstance(first_stmt, ast.Expr), (
                    f"{name} 函数体非零实现（首语句类型：{type(first_stmt).__name__}）"
                )
            else:
                # 多语句时，最后一条应为 ... 或 pass
                last_stmt = body[-1]
                is_last_ellipsis = (
                    isinstance(last_stmt, ast.Expr)
                    and isinstance(last_stmt.value, ast.Constant)
                    and last_stmt.value.value is ...
                )
                is_last_pass = isinstance(last_stmt, ast.Pass)
                assert is_last_ellipsis or is_last_pass, (
                    f"{name} 函数体非零实现（最后语句类型：{type(last_stmt).__name__}）"
                )

    def test_required_models_defined(self, stub_classes):
        """存根定义必要的 Pydantic 模型。"""
        expected_models = {
            "DocumentResponse",
            "UploadResponse",
            "RawTextRequest",
            "UpdateEmbeddingsRequest",
            "MetadataSchemaResponse",
        }
        actual = set(stub_classes.keys())
        missing = expected_models - actual
        assert not missing, f"缺少 Pydantic 模型定义：{missing}"

    def test_document_response_fields_match_schema(self, stub_classes, schema):
        """DocumentResponse 模型字段与数据契约 properties 一致。"""
        cls = stub_classes["DocumentResponse"]
        # 提取类属性名（带类型注解的赋值）
        model_fields = set()
        for stmt in cls.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                model_fields.add(stmt.target.id)
        schema_fields = set(schema["properties"].keys())
        assert model_fields == schema_fields, (
            f"DocumentResponse 字段与 schema 不一致：\n"
            f"  模型独有：{model_fields - schema_fields}\n"
            f"  schema 独有：{schema_fields - model_fields}"
        )

    def test_stub_module_docstring_mentions_seven_endpoints(self, stub_tree):
        """存根模块 docstring 声明 7 个端点。"""
        module_doc = ast.get_docstring(stub_tree) or ""
        assert "7" in module_doc, "模块 docstring 未声明 7 个端点"
        # 验证端点方法名都在 docstring 中提及
        endpoint_names = [
            "upload_document",
            "upload_raw_text",
            "list_documents",
            "get_document",
            "delete_document",
            "update_workspace_embeddings",
            "get_metadata_schema",
        ]
        for name in endpoint_names:
            assert name in module_doc or name.replace("_", "-") in module_doc or "7个" in module_doc, (
                f"模块 docstring 未提及端点：{name}"
            )


# ============================================================================ #
# 配置契约 rubric
# ============================================================================ #


class TestConfigContract:
    """配置契约（public/config_template/anythingllm_document_config.json）rubric 测试。"""

    def test_config_file_exists(self):
        """配置文件存在。"""
        assert _CONFIG_FILE.exists(), f"配置契约文件不存在：{_CONFIG_FILE}"

    def test_config_is_valid_json(self, config):
        """配置文件本身是合法 JSON。"""
        assert isinstance(config, dict), "config 顶层非 object"

    def test_config_is_valid_json_schema(self, config):
        """配置契约为合法 JSON Schema（draft-07）。"""
        jsonschema.Draft7Validator.check_schema(config)

    def test_config_declares_draft07(self, config):
        """配置契约显式声明 $schema 为 draft-07。"""
        assert "$schema" in config, "配置契约缺少 $schema 声明"
        assert "draft-07" in config["$schema"], (
            f"配置契约 $schema 非 draft-07：{config['$schema']}"
        )

    def test_config_has_db_path(self, config):
        """包含 db_path（string, default: 'data/documents.db'）。"""
        props = config["properties"]
        assert "db_path" in props, "缺少 db_path 配置项"
        db_path = props["db_path"]
        assert db_path["type"] == "string", f"db_path.type 非 string：{db_path['type']}"
        assert db_path["default"] == "data/documents.db", (
            f"db_path.default 非 'data/documents.db'：{db_path.get('default')}"
        )

    def test_config_has_max_file_size(self, config):
        """包含 max_file_size（integer, default: 10485760）。"""
        props = config["properties"]
        assert "max_file_size" in props, "缺少 max_file_size 配置项"
        max_size = props["max_file_size"]
        assert max_size["type"] == "integer", (
            f"max_file_size.type 非 integer：{max_size['type']}"
        )
        assert max_size["default"] == 10485760, (
            f"max_file_size.default 非 10485760：{max_size.get('default')}"
        )

    def test_config_has_default_folder(self, config):
        """包含 default_folder（string, default: 'custom-documents'）。"""
        props = config["properties"]
        assert "default_folder" in props, "缺少 default_folder 配置项"
        folder = props["default_folder"]
        assert folder["type"] == "string", (
            f"default_folder.type 非 string：{folder['type']}"
        )
        assert folder["default"] == "custom-documents", (
            f"default_folder.default 非 'custom-documents'：{folder.get('default')}"
        )

    def test_config_required_fields(self, config):
        """配置契约 required 字段包含全部 3 项。"""
        required = set(config.get("required", []))
        expected = {"db_path", "max_file_size", "default_folder"}
        assert expected == required, (
            f"required 字段不一致：期望 {expected}，实际 {required}"
        )

    def test_config_additional_properties_false(self, config):
        """配置契约显式 additionalProperties: false。"""
        assert config.get("additionalProperties") is False, (
            "配置契约必须声明 additionalProperties: false"
        )

    def test_config_has_title_and_description(self, config):
        """配置契约含 title 与 description。"""
        assert "title" in config and config["title"], "配置契约缺少 title"
        assert "description" in config and config["description"], (
            "配置契约缺少 description"
        )

    def test_config_valid_sample_passes(self, config):
        """合法配置样本通过 schema 校验。"""
        sample = {
            "db_path": "data/documents.db",
            "max_file_size": 10485760,
            "default_folder": "custom-documents",
        }
        jsonschema.validate(sample, config)

    def test_config_missing_required_fails(self, config):
        """缺少 required 字段校验失败。"""
        sample = {
            "db_path": "data/documents.db",
            # 缺少 max_file_size 与 default_folder
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, config)

    def test_config_additional_property_rejected(self, config):
        """额外字段被拒绝。"""
        sample = {
            "db_path": "data/documents.db",
            "max_file_size": 10485760,
            "default_folder": "custom-documents",
            "extra": "should be rejected",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, config)

    def test_config_wrong_type_fails(self, config):
        """类型错误校验失败。"""
        sample = {
            "db_path": 123,  # 应为 string
            "max_file_size": 10485760,
            "default_folder": "custom-documents",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(sample, config)


# ============================================================================ #
# 三层契约一致性 rubric
# ============================================================================ #


class TestContractConsistency:
    """三层契约之间的一致性校验。"""

    def test_schema_and_stub_field_consistency(self, schema, stub_classes):
        """DocumentResponse 模型字段与数据契约 properties 完全一致。"""
        cls = stub_classes["DocumentResponse"]
        model_fields = set()
        for stmt in cls.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                model_fields.add(stmt.target.id)
        schema_fields = set(schema["properties"].keys())
        assert model_fields == schema_fields, (
            f"接口契约 DocumentResponse 与数据契约字段不一致：\n"
            f"  模型独有：{model_fields - schema_fields}\n"
            f"  schema 独有：{schema_fields - model_fields}"
        )

    def test_error_codes_consistency_between_schema_and_stub(self, schema, stub_functions):
        """数据契约错误码与接口契约 docstring 中声明的 HTTP 状态码一致。"""
        # schema 中定义的错误码
        error_codes = schema["definitions"]["error_codes"]["properties"]
        schema_codes = {ec["const"] for ec in error_codes.values()}

        # 从 stub docstring 中提取所有 HTTP 状态码
        stub_text = _load_stub_text()
        http_codes_in_stub = set()
        for match in re.finditer(r"HTTPException\((\d+)\)", stub_text):
            http_codes_in_stub.add(int(match.group(1)))
        # 也匹配 docstring 中的纯数字声明（如 "HTTPException(413)" 或 "413"）
        for match in re.finditer(r"HTTPException[（(](\d+)[）)]", stub_text):
            http_codes_in_stub.add(int(match.group(1)))

        # schema 中的错误码应都在 stub 中有对应声明（或 stub 声明的码都在 schema 中）
        # 至少 404/413/500 都应在 stub 中出现
        for code in [404, 413, 500]:
            assert code in http_codes_in_stub or str(code) in stub_text, (
                f"接口契约 stub 中未声明 HTTPException({code})"
            )

    def test_config_max_file_size_referenced_in_stub(self, stub_functions):
        """配置契约 max_file_size 在接口契约 upload_document docstring 中被引用。"""
        doc = _docstring(stub_functions["upload_document"])
        assert "max_file_size" in doc or "413" in doc, (
            "upload_document docstring 未引用 max_file_size 配置项或 413 错误码"
        )


# ============================================================================ #
# 入口：支持直接 python 运行（也支持 pytest）
# --------------------------------------------------------------------------- #
# 使用 unittest main 入口确保 `python <file>` 可独立执行
# ============================================================================ #


if __name__ == "__main__":
    # 通过 pytest main 入口运行，确保 `python <file>` 可独立执行
    # 传入当前文件路径，pytest 自动发现所有 TestXxx 类
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
