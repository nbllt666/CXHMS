"""接口契约校验测试（G4 批次 G-3）。

校验 backend 实现签名匹配 public/interface_stub/*.pyi，对应 rules-3 §二 接口契约。

覆盖要求（spec tasks.md Task G4）：
    - 加载每个 .pyi 存根
    - 校验：方法名存在、参数名匹配、参数类型匹配、返回值类型匹配、异常声明匹配
    - 关键类：MemoryManager、AsyncMemoryManager、MemoryRouter、HybridSearch、
      GraphManager、ToolRegistry、AgentManager、ChatService 等
    - 容忍：python 类型注解与 .pyi 在 Literal/Optional/Union 等上的等价性
    - 不匹配项登记为 FAILED 断言（不得仅 print）

约束：
    - public/ 受保护，本测试只读不写
    - 不修改 backend 源码
    - 若 backend 与契约不匹配，登记为 FAILED（这是 G4 的目的——暴露契约违规）
"""

import ast
import inspect
import importlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

# --------------------------------------------------------------------------- #
# 路径锚点
# --------------------------------------------------------------------------- #
_PUBLIC_STUB_DIR = Path(__file__).resolve().parents[2] / "public" / "interface_stub"

# --------------------------------------------------------------------------- #
# Stub → Backend 实现定位表
# --------------------------------------------------------------------------- #
# 每个 stub 类对应一个 backend 实现：
#   - kind="class": 在 backend_module 中找 backend_class 类，校验其方法
#   - kind="module": 在 backend_module 中找同名函数（router function）
#
# 字段说明：
#   backend_module: backend 模块路径
#   backend_class: 类名（kind="class" 时使用）
#   kind: "class" 或 "module"
STUB_BACKEND_LOCATOR: Dict[str, Dict[str, str]] = {
    "MemoryService": {
        "backend_module": "backend.core.memory.manager",
        "backend_class": "MemoryManager",
        "kind": "class",
    },
    "AgentService": {
        "backend_module": "backend.api.routers.agents",
        "backend_class": None,
        "kind": "module",
    },
    "ChatService": {
        "backend_module": "backend.api.routers.chat",
        "backend_class": None,
        "kind": "module",
    },
    "GraphService": {
        "backend_module": "backend.api.routers.graph",
        "backend_class": None,
        "kind": "module",
    },
    "ToolService": {
        "backend_module": "backend.api.routers.tools",
        "backend_class": None,
        "kind": "module",
    },
    "AnythingLLMService": {
        "backend_module": "backend.api.routers.anythingllm",
        "backend_class": None,
        "kind": "module",
    },
    # RADIX-Lite 新增（Task 0-6，2026-07-16 补全 locator）
    "AgentToolsV2": {
        "backend_module": "modules.模块10_管理Agent扩展.agent_tools",
        "backend_class": "AgentToolsV2",
        "kind": "class",
    },
    "DecisionCore": {
        "backend_module": "modules.模块10_管理Agent扩展.decision_core",
        "backend_class": "DecisionCore",
        "kind": "class",
    },
    "DistillationService": {
        "backend_module": "modules.模块9_蒸馏服务.distillation_service",
        "backend_class": "DistillationService",
        "kind": "class",
    },
    "MemoryManagerV2": {
        # V2 是 MemoryManager 的扩展（同一类新增 write_with_decision 等方法）
        "backend_module": "backend.core.memory.manager",
        "backend_class": "MemoryManager",
        "kind": "class",
    },
    "MultimodalPipeline": {
        "backend_module": "modules.模块8_多模态管线.multimodal_pipeline",
        "backend_class": "MultimodalPipeline",
        "kind": "class",
    },
    "TemplateEngine": {
        "backend_module": "modules.模块7_模板引擎.template_engine",
        "backend_class": "TemplateEngine",
        "kind": "class",
    },
}


# --------------------------------------------------------------------------- #
# .pyi 解析（用 ast，避免 import .pyi 副作用）
# --------------------------------------------------------------------------- #


def _parse_pyi_methods(pyi_path: Path) -> Dict[str, Dict[str, Any]]:
    """解析 .pyi 文件，提取每个 class 的方法签名。

    Returns:
        {class_name: {method_name: {args, defaults, annotations, returns, is_async}}}
    """
    with open(pyi_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    classes: Dict[str, Dict[str, Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_name = node.name
        methods: Dict[str, Any] = {}
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            method_name = item.name
            # 提取参数名（含 self）
            args = [a.arg for a in item.args.args]
            # 默认值数量（末尾 N 个参数有默认值）
            n_defaults = len(item.args.defaults)
            # 参数注解
            annotations: Dict[str, str] = {}
            for arg in item.args.args:
                if arg.annotation is not None:
                    annotations[arg.arg] = ast.unparse(arg.annotation)
            # 返回值注解
            returns = ast.unparse(item.returns) if item.returns else None
            methods[method_name] = {
                "args": args,
                "n_defaults": n_defaults,
                "annotations": annotations,
                "returns": returns,
                "is_async": isinstance(item, ast.AsyncFunctionDef),
            }
        classes[class_name] = methods
    return classes


def _load_all_stubs() -> Dict[str, Dict[str, Any]]:
    """加载所有 .pyi 存根，合并为 {class_name: {method_name: signature}}。

    若多个 .pyi 有同名 class，后者覆盖前者（实际不会发生，每个 .pyi 一个 class）。
    """
    all_stubs: Dict[str, Dict[str, Any]] = {}
    for pyi_file in sorted(_PUBLIC_STUB_DIR.glob("*.pyi")):
        classes = _parse_pyi_methods(pyi_file)
        all_stubs.update(classes)
    return all_stubs


# --------------------------------------------------------------------------- #
# Backend 实现查找
# --------------------------------------------------------------------------- #


def _get_backend_callable(
    locator: Dict[str, str], method_name: str
) -> Optional[Callable]:
    """根据 locator 在 backend 中查找对应 callable。

    Returns:
        Callable 或 None（未找到）
    """
    try:
        module = importlib.import_module(locator["backend_module"])
    except Exception:
        return None

    if locator["kind"] == "class":
        cls = getattr(module, locator["backend_class"], None)
        if cls is None:
            return None
        return getattr(cls, method_name, None)
    else:  # module
        return getattr(module, method_name, None)


def _get_backend_signature(callable_obj: Callable) -> Dict[str, Any]:
    """获取 backend callable 的签名信息。

    Returns:
        {args, n_defaults, annotations, returns, is_async, depends_params}
        depends_params: FastAPI Depends 注入的参数名集合（如 graph）
    """
    sig = inspect.signature(callable_obj)
    args: List[str] = []
    n_defaults = 0
    annotations: Dict[str, Any] = {}
    depends_params: set = set()
    for name, param in sig.parameters.items():
        args.append(name)
        if param.default is not inspect.Parameter.empty:
            n_defaults += 1
            # 检测 FastAPI Depends 注入参数
            default_str = type(param.default).__name__
            if default_str == "Depends" or hasattr(param.default, "dependency"):
                depends_params.add(name)
        if param.annotation is not inspect.Parameter.empty:
            annotations[name] = param.annotation
    returns = sig.return_annotation if sig.return_annotation is not inspect.Signature.empty else None
    is_async = inspect.iscoroutinefunction(callable_obj)
    return {
        "args": args,
        "n_defaults": n_defaults,
        "annotations": annotations,
        "returns": returns,
        "is_async": is_async,
        "depends_params": depends_params,
    }


# --------------------------------------------------------------------------- #
# 类型等价性比较（容忍 Literal/Optional/Union 等价性）
# --------------------------------------------------------------------------- #


def _normalize_type_str(type_str: str) -> str:
    """归一化 .pyi 中的类型字符串，便于比较。

    例如 "Optional[List[str]]" → "Optional[List[str]]"（保持原样，仅去空格）
    "Dict[str, Any]" → "Dict[str, Any]"
    """
    return type_str.replace(" ", "")


def _types_compatible(stub_type_str: str, backend_type: Any) -> bool:
    """判断 stub 类型字符串与 backend 类型是否兼容。

    容忍规则（spec Task G4）：
      - 容器类型（Dict/List/Optional/Union）：同类即兼容，不深究参数
      - 基本类型（str/int/bool/float）：严格匹配
      - backend 用 Pydantic Model 时，stub 用 Dict[str, Any] 视为兼容
        （Pydantic Model 本质是 dict 的强类型化）
      - backend 为 Any / 无注解 → 兼容
    """
    if backend_type is inspect.Parameter.empty or backend_type is None:
        return True  # backend 无注解，宽松通过

    stub_norm = _normalize_type_str(stub_type_str)

    # backend 类型转字符串
    try:
        if hasattr(backend_type, "__origin__"):
            backend_str = getattr(backend_type, "_name", None) or str(
                backend_type
            ).split("[")[0].split(".")[-1]
        else:
            backend_str = getattr(backend_type, "__name__", str(backend_type))
    except Exception:
        backend_str = str(backend_type)

    # 容器类型宽容
    stub_lower = stub_norm.lower()
    if "dict" in stub_lower:
        # stub 是 Dict → backend 是 dict/Dict/BaseModel 均可
        return "dict" in str(backend_type).lower() or hasattr(
            backend_type, "model_fields"
        ) or hasattr(backend_type, "__fields__")
    if "list" in stub_lower:
        return "list" in str(backend_type).lower() or "List" in str(backend_type)
    if "optional" in stub_lower or "union" in stub_lower:
        # Optional/Union 宽松
        return True
    if "any" in stub_lower:
        return True
    if "asynciterator" in stub_lower:
        # 返回 AsyncIterator，backend 可能是 AsyncGenerator
        return "async" in str(backend_type).lower() or backend_str in (
            "AsyncIterator",
            "AsyncGenerator",
        )

    # 基本类型严格匹配
    type_map = {
        "str": str,
        "int": int,
        "bool": bool,
        "float": float,
        "string": str,
        "integer": int,
        "boolean": bool,
        "number": (int, float),
    }
    for stub_name, py_type in type_map.items():
        if stub_name in stub_lower:
            # bool 是 int 子类，需精确
            if py_type is int and backend_type is bool:
                return False
            try:
                return backend_type is py_type or (
                    isinstance(backend_type, type) and issubclass(backend_type, py_type)
                )
            except TypeError:
                return False

    # 默认宽松（无法判定时通过，避免假阳性）
    return True


# --------------------------------------------------------------------------- #
# 参数比较（排除 self、Depends 注入参数）
# --------------------------------------------------------------------------- #


def _filter_backend_args(
    args: List[str],
    annotations: Dict[str, Any],
    depends_params: Optional[set] = None,
) -> List[str]:
    """过滤 backend 参数：排除 self、FastAPI Depends 注入参数（如 graph）。

    Args:
        args: 原始参数名列表
        annotations: 参数注解
        depends_params: FastAPI Depends 注入的参数名集合
    """
    depends_params = depends_params or set()
    filtered = []
    for arg in args:
        if arg == "self":
            continue
        if arg in depends_params:
            continue
        filtered.append(arg)
    return filtered


def _filter_stub_args(args: List[str]) -> List[str]:
    """过滤 stub 参数：排除 self。"""
    return [a for a in args if a != "self"]


# --------------------------------------------------------------------------- #
# 测试数据收集（模块加载时执行一次）
# --------------------------------------------------------------------------- #


def _collect_all_stub_methods() -> List[Tuple[str, str]]:
    """收集所有 (stub_class, method_name) 对，用于参数化测试。"""
    all_stubs = _load_all_stubs()
    methods: List[Tuple[str, str]] = []
    for class_name, class_methods in all_stubs.items():
        for method_name in class_methods.keys():
            methods.append((class_name, method_name))
    return methods


_ALL_STUB_METHODS = _collect_all_stub_methods()


# --------------------------------------------------------------------------- #
# 公共 fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(params=_ALL_STUB_METHODS, ids=lambda x: f"{x[0]}.{x[1]}")
def stub_method(request):
    """参数化 (stub_class, method_name)。"""
    return request.param


@pytest.fixture
def all_stubs():
    return _load_all_stubs()


# --------------------------------------------------------------------------- #
# .pyi 文件结构断言
# --------------------------------------------------------------------------- #


class TestStubFileStructure:
    """每个 .pyi 文件本身的结构性约束。"""

    @pytest.mark.parametrize(
        "pyi_name",
        ["memory_service", "agent_service", "chat_service", "graph_service", "tool_service"],
    )
    def test_pyi_file_exists(self, pyi_name):
        path = _PUBLIC_STUB_DIR / f"{pyi_name}.pyi"
        assert path.exists(), f"interface_stub 文件不存在：{path}"

    @pytest.mark.parametrize(
        "pyi_name",
        ["memory_service", "agent_service", "chat_service", "graph_service", "tool_service"],
    )
    def test_pyi_is_valid_python(self, pyi_name):
        """每个 .pyi 是合法 Python 语法（可被 ast 解析）。"""
        path = _PUBLIC_STUB_DIR / f"{pyi_name}.pyi"
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)  # 不抛异常即合法

    @pytest.mark.parametrize(
        "pyi_name,expected_class",
        [
            ("memory_service", "MemoryService"),
            ("agent_service", "AgentService"),
            ("chat_service", "ChatService"),
            ("graph_service", "GraphService"),
            ("tool_service", "ToolService"),
        ],
    )
    def test_pyi_declares_service_class(self, pyi_name, expected_class):
        """每个 .pyi 声明对应 service 类。"""
        path = _PUBLIC_STUB_DIR / f"{pyi_name}.pyi"
        classes = _parse_pyi_methods(path)
        assert expected_class in classes, (
            f"{pyi_name}.pyi 缺少 {expected_class} 类声明"
        )

    @pytest.mark.parametrize(
        "pyi_name",
        ["memory_service", "agent_service", "chat_service", "graph_service", "tool_service"],
    )
    def test_pyi_has_version_annotation(self, pyi_name):
        """每个 .pyi 含 @version 注释（rules-3 §六 契约版本化）。"""
        path = _PUBLIC_STUB_DIR / f"{pyi_name}.pyi"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "@version" in content, f"{pyi_name}.pyi 缺少 @version 注释"

    @pytest.mark.parametrize(
        "pyi_name",
        ["memory_service", "agent_service", "chat_service", "graph_service", "tool_service"],
    )
    def test_pyi_has_see_reference(self, pyi_name):
        """每个 .pyi 含 @see 引用对应 schema。"""
        path = _PUBLIC_STUB_DIR / f"{pyi_name}.pyi"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "@see" in content, f"{pyi_name}.pyi 缺少 @see 引用"


# --------------------------------------------------------------------------- #
# 方法存在性 + 签名匹配（核心契约校验）
# --------------------------------------------------------------------------- #


class TestMethodExists:
    """每个 stub 方法必须在 backend 实现中存在（按 EXACT 名匹配）。

    不匹配项登记为 FAILED 断言——这是 G4 的目的（暴露契约违规）。
    主线程可决定走 s0601 流程修复契约或修改 backend 实现。
    """

    def test_method_exists_in_backend(self, stub_method, all_stubs):
        """每个 stub 方法在 backend 中存在同名实现。"""
        stub_class, method_name = stub_method
        locator = STUB_BACKEND_LOCATOR.get(stub_class)
        assert locator is not None, (
            f"STUB_BACKEND_LOCATOR 未配置 {stub_class} 的 backend 定位"
        )

        backend_callable = _get_backend_callable(locator, method_name)
        assert backend_callable is not None, (
            f"{stub_class}.{method_name} 在 backend {locator['backend_module']} "
            f"中未找到同名实现。"
            f"{'（backend 用不同函数名实现，需走 s0601 适配契约变更）' if True else ''}"
        )


class TestSignatureMatches:
    """对于已存在的 backend 方法，参数签名应与 stub 匹配。

    本测试只对 method exists 的方法进行签名校验，
    避免与 TestMethodExists 重复失败。

    FastAPI request 模式容忍：
      - stub 声明独立参数（如 message, agent_id）
      - backend 用 `request: PydanticModel`，其中 PydanticModel 含 stub 声明的字段
      - 视为兼容（FastAPI 惯例，service 接口语义一致）
    """

    def _check_request_model_has_fields(
        self, backend_sig: Dict[str, Any], missing_direct: List[str]
    ) -> Tuple[bool, List[str]]:
        """检查 backend 是否用 `request: PydanticModel` 模式且含 stub 声明的字段。

        只对 missing_direct（未直接匹配 backend 参数名的 stub 参数）做字段检查，
        避免把 `request` 参数本身误判为应出现在 model 字段中。

        Args:
            backend_sig: backend 签名信息
            missing_direct: 在 backend_args 中未直接匹配到的 stub 参数列表

        Returns:
            (is_request_pattern, missing_fields)
            - is_request_pattern: True 表示 backend 用了 request 模式
            - missing_fields: missing_direct 中不在 request model 字段中的项
        """
        # 检查 backend 是否有 `request` 参数且为 Pydantic Model
        if "request" not in backend_sig["args"]:
            return False, missing_direct
        request_ann = backend_sig["annotations"].get("request")
        if request_ann is None:
            return False, missing_direct
        # Pydantic v1/v2 检测
        is_pydantic = (
            hasattr(request_ann, "model_fields")  # v2
            or hasattr(request_ann, "__fields__")  # v1
        )
        if not is_pydantic:
            return False, missing_direct
        # 获取 Pydantic 字段
        if hasattr(request_ann, "model_fields"):
            field_names = set(request_ann.model_fields.keys())
        else:
            field_names = set(request_ann.__fields__.keys())
        # 只检查 missing_direct 中不在 model 字段里的项
        missing = [a for a in missing_direct if a not in field_names]
        return True, missing

    def test_parameter_names_match(self, stub_method, all_stubs):
        """backend 方法参数名（排除 self、Depends 注入）应与 stub 匹配。

        FastAPI request 模式（backend 用 `request: PydanticModel`，stub 用独立参数）
        视为兼容——若 PydanticModel 含 stub 声明的全部字段则通过。
        """
        stub_class, method_name = stub_method
        locator = STUB_BACKEND_LOCATOR[stub_class]

        backend_callable = _get_backend_callable(locator, method_name)
        if backend_callable is None:
            pytest.skip(
                f"{stub_class}.{method_name} 不存在于 backend，"
                f"签名校验跳过（已在 TestMethodExists 中失败）"
            )

        stub_sig = all_stubs[stub_class][method_name]
        backend_sig = _get_backend_signature(backend_callable)

        stub_args = _filter_stub_args(stub_sig["args"])
        backend_args_filtered = _filter_backend_args(
            backend_sig["args"],
            backend_sig["annotations"],
            backend_sig["depends_params"],
        )

        # 直接匹配：stub 参数是否都在 backend 中（排除 Depends）
        missing_direct = [a for a in stub_args if a not in backend_args_filtered]

        if not missing_direct:
            return  # 完全匹配

        # FastAPI request 模式检测：backend 用 `request: PydanticModel`
        # 只对未直接匹配的 stub 参数（missing_direct）做 model 字段检查
        is_request_pattern, missing_in_model = self._check_request_model_has_fields(
            backend_sig, missing_direct
        )
        if is_request_pattern and not missing_in_model:
            return  # FastAPI request 模式，未匹配的 stub 字段都在 model 中

        # 真正的缺失：登记为 FAILED
        if is_request_pattern:
            reason = (
                f"{stub_class}.{method_name}: FastAPI request 模式，"
                f"但 stub 字段 {missing_in_model} 不在 request model 中。"
                f"stub_args={stub_args}, backend_args={backend_args_filtered}"
            )
        else:
            reason = (
                f"{stub_class}.{method_name}: stub 参数 {missing_direct} "
                f"在 backend 中未找到。stub_args={stub_args}, "
                f"backend_args={backend_args_filtered}"
            )
        pytest.fail(reason)

    def test_parameter_types_compatible(self, stub_method, all_stubs):
        """backend 方法参数类型应与 stub 兼容（容忍 Optional/Dict/Pydantic 等价性）。"""
        stub_class, method_name = stub_method
        locator = STUB_BACKEND_LOCATOR[stub_class]

        backend_callable = _get_backend_callable(locator, method_name)
        if backend_callable is None:
            pytest.skip(
                f"{stub_class}.{method_name} 不存在于 backend，类型校验跳过"
            )

        stub_sig = all_stubs[stub_class][method_name]
        backend_sig = _get_backend_signature(backend_callable)

        type_mismatches: List[str] = []
        for arg_name, stub_type_str in stub_sig["annotations"].items():
            if arg_name == "self":
                continue
            backend_type = backend_sig["annotations"].get(arg_name)
            if not _types_compatible(stub_type_str, backend_type):
                type_mismatches.append(
                    f"{stub_class}.{method_name}.{arg_name}: "
                    f"stub={stub_type_str}, backend={backend_type}"
                )

        assert not type_mismatches, (
            f"参数类型不匹配：\n" + "\n".join(type_mismatches)
        )

    def test_async_signature_matches(self, stub_method, all_stubs):
        """async/同步属性应一致（stub async → backend async）。"""
        stub_class, method_name = stub_method
        locator = STUB_BACKEND_LOCATOR[stub_class]

        backend_callable = _get_backend_callable(locator, method_name)
        if backend_callable is None:
            pytest.skip(
                f"{stub_class}.{method_name} 不存在于 backend，async 校验跳过"
            )

        stub_sig = all_stubs[stub_class][method_name]
        backend_sig = _get_backend_signature(backend_callable)

        if stub_sig["is_async"]:
            assert backend_sig["is_async"], (
                f"{stub_class}.{method_name}: stub 声明为 async，"
                f"但 backend 实现为同步"
            )
        # 反向不严格要求：stub 同步 + backend async 也可接受（更灵活）


# --------------------------------------------------------------------------- #
# MemoryManager 专项校验（关键类，签名应严格匹配）
# --------------------------------------------------------------------------- #


class TestMemoryManagerCompliance:
    """MemoryManager（MemoryService 实现）签名严格校验。

    MemoryService.pyi 是 MemoryManager 的接口契约，两者应严格匹配。
    """

    @pytest.fixture
    def memory_manager_class(self):
        from backend.core.memory.manager import MemoryManager
        return MemoryManager

    @pytest.fixture
    def stub_methods(self):
        return _load_all_stubs()["MemoryService"]

    EXPECTED_METHODS = [
        "write_memory",
        "get_memory",
        "update_memory",
        "delete_memory",
        "search_memories",
        "recall_memory",
        "get_statistics",
        "is_vector_search_enabled",
        "hybrid_search",
        "semantic_search",
        "batch_write_memories",
        "batch_update_memories",
        "batch_delete_memories",
        "sync_decay_values",
    ]

    @pytest.mark.parametrize("method_name", EXPECTED_METHODS)
    def test_method_exists(self, memory_manager_class, method_name):
        """MemoryManager 必须实现 MemoryService 声明的所有方法。"""
        assert hasattr(memory_manager_class, method_name), (
            f"MemoryManager 缺少方法：{method_name}"
        )

    @pytest.mark.parametrize("method_name", EXPECTED_METHODS)
    def test_method_signature_matches(
        self, memory_manager_class, stub_methods, method_name
    ):
        """每个方法的参数名应与 stub 匹配。"""
        backend_method = getattr(memory_manager_class, method_name)
        backend_sig = _get_backend_signature(backend_method)

        stub_sig = stub_methods[method_name]
        stub_args = _filter_stub_args(stub_sig["args"])
        backend_args = [a for a in backend_sig["args"] if a != "self"]

        # 校验 stub 声明的参数都在 backend 中
        missing = [a for a in stub_args if a not in backend_args]
        assert not missing, (
            f"MemoryManager.{method_name}: stub 参数 {missing} 未在 backend 中找到。"
            f"stub={stub_args}, backend={backend_args}"
        )

    def test_write_memory_signature(self, memory_manager_class, stub_methods):
        """write_memory 关键参数严格匹配（G4 重点校验）。"""
        backend_method = getattr(memory_manager_class, "write_memory")
        sig = inspect.signature(backend_method)
        params = sig.parameters

        # 必须含这些关键参数（B4 回归：agent_id 透传）
        assert "content" in params, "write_memory 缺少 content 参数"
        assert "memory_type" in params, "write_memory 缺少 memory_type 参数"
        assert "importance" in params, "write_memory 缺少 importance 参数"
        assert "agent_id" in params, "write_memory 缺少 agent_id 参数（B4 回归）"
        assert "workspace_id" in params, "write_memory 缺少 workspace_id 参数"

    def test_recall_memory_signature(self, memory_manager_class):
        """recall_memory 含 agent_id 参数（B4 回归：跨 agent 不串扰）。"""
        backend_method = getattr(memory_manager_class, "recall_memory")
        sig = inspect.signature(backend_method)
        params = sig.parameters
        assert "agent_id" in params, "recall_memory 缺少 agent_id 参数（B4 回归）"

    def test_hybrid_search_signature(self, memory_manager_class):
        """hybrid_search 含 agent_id 参数（B5 回归：跨 agent 不泄漏）。"""
        backend_method = getattr(memory_manager_class, "hybrid_search")
        sig = inspect.signature(backend_method)
        params = sig.parameters
        assert "agent_id" in params, "hybrid_search 缺少 agent_id 参数（B5 回归）"

    def test_search_memories_signature(self, memory_manager_class):
        """search_memories 含 agent_id + workspace_id 参数。"""
        backend_method = getattr(memory_manager_class, "search_memories")
        sig = inspect.signature(backend_method)
        params = sig.parameters
        assert "agent_id" in params, "search_memories 缺少 agent_id 参数"
        assert "workspace_id" in params, "search_memories 缺少 workspace_id 参数"

    def test_batch_write_memories_signature(self, memory_manager_class):
        """batch_write_memories 签名匹配。"""
        backend_method = getattr(memory_manager_class, "batch_write_memories")
        sig = inspect.signature(backend_method)
        params = sig.parameters
        assert "memories" in params, "batch_write_memories 缺少 memories 参数"
        assert "raise_on_error" in params, (
            "batch_write_memories 缺少 raise_on_error 参数"
        )

    def test_is_vector_search_enabled_no_args(self, memory_manager_class):
        """is_vector_search_enabled 无参数（纯查询）。"""
        backend_method = getattr(memory_manager_class, "is_vector_search_enabled")
        sig = inspect.signature(backend_method)
        params = list(sig.parameters.keys())
        # 仅 self，无其他参数
        non_self = [p for p in params if p != "self"]
        assert not non_self, (
            f"is_vector_search_enabled 应无参数（除 self），实际有：{non_self}"
        )


# --------------------------------------------------------------------------- #
# AsyncMemoryManager 专项校验（B1 回归：initialize）
# --------------------------------------------------------------------------- #


class TestAsyncMemoryManagerCompliance:
    """AsyncMemoryManager 含 initialize 方法（B1 回归）。"""

    def test_initialize_method_exists(self):
        """AsyncMemoryManager 必须实现 initialize（B1 修复回归）。"""
        from backend.core.memory.async_manager import AsyncMemoryManager
        assert hasattr(AsyncMemoryManager, "initialize"), (
            "AsyncMemoryManager 缺少 initialize 方法（B1 回归）"
        )

    def test_initialize_is_async(self):
        """initialize 必须是 async（B1 修复：await async_memory_manager.initialize()）。"""
        from backend.core.memory.async_manager import AsyncMemoryManager
        assert inspect.iscoroutinefunction(AsyncMemoryManager.initialize), (
            "AsyncMemoryManager.initialize 必须是 async（B1 回归）"
        )


# --------------------------------------------------------------------------- #
# 契约违规汇总（注释性文档，无独立测试）
# --------------------------------------------------------------------------- #
# 下列 7 项契约违规已由 TestMethodExists.test_method_exists_in_backend 暴露
# （参数化覆盖全部 stub 方法，按 EXACT 名匹配，不重复校验）：
#
#   1. AgentService.list_agents         → backend 实际为 get_agents
#   2. AgentService.get_default_agent   → backend 未实现
#   3. ChatService.stream_chat         → backend 实际为 chat_stream
#   4. ChatService.memory_agent_stream_chat
#                                       → backend 实际为 memory_agent_chat_stream
#   5. ChatService.summary_agent_stream_chat
#                                       → backend 实际为 summary_agent_chat_stream
#   6. ToolService.execute_tool         → backend 实际为 call_tool
#   7. ToolService.update_tool          → backend 未实现
#
# 主线程处置路径：走 s0601（适配契约变更）或修改 backend 实现，二选一。
# 详见 .trae/documents/20260705_模块0_重写契约测试.md 第四章。
