"""接口契约签名匹配测试。

两层校验：
1. Mock vs 存根：校验 public/pre_generated_mock/*.py 的实现签名是否匹配 public/interface_stub/*.pyi 存根
2. 存根 vs 真实实现：校验存根签名是否与 backend 真实实现一致（memory 做严格参数+顺序+默认值对比；
   chat/agent/tool/graph 做 router 函数存在性校验，因 router endpoint 含 HTTP 框架参数非 1:1 签名对应）

通过 AST 解析 .pyi、.py，对比类的方法名集合与方法签名。

执行：python -m pytest public/test_cases/test_interface_stub.py -v
降级：python public/test_cases/test_interface_stub.py
"""

import ast
import os

from .conftest import BACKEND_DIR, MOCK_DIR, STUB_DIR


# ---------- AST 解析工具 ----------

def _parse_methods(path: str) -> dict:
    """解析 .pyi 或 .py，返回 {类名: {方法名: (args, returns)}}。"""
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in item.args.args]
                    returns = ast.unparse(item.returns) if item.returns else None
                    methods[item.name] = (args, returns)
            result[node.name] = methods
    return result


def _parse_signatures(path: str, class_name: str = None) -> dict:
    """解析 .pyi 或 .py 的方法/函数签名。

    若指定 class_name，解析该类的方法；否则解析模块级函数。
    返回 {方法名/函数名: (参数名列表, 有默认值的参数名集合)}。
    参数名列表不含 self。
    """
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    result = {}
    nodes = []
    if class_name:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                nodes = [item for item in node.body
                         if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
                break
    else:
        nodes = [node for node in ast.iter_child_nodes(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for item in nodes:
        args = [a.arg for a in item.args.args if a.arg != "self"]
        defaults = item.args.defaults
        n_defaults = len(defaults)
        defaulted = set(args[-n_defaults:]) if n_defaults > 0 else set()
        result[item.name] = (args, defaulted)
    return result


def _find_impl_class_name(path: str, stub_method_names: set) -> str:
    """在真实实现文件中找到包含最多存根方法的类名。"""
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    best_name, best_count = None, 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = {item.name for item in node.body
                       if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
            count = len(methods & stub_method_names)
            if count > best_count:
                best_count, best_name = count, node.name
    assert best_name is not None, f"未在 {path} 中找到包含存根方法的类"
    return best_name


def _stub_to_impl_name(stub_class: str) -> str:
    """MemoryService -> MockMemoryService。"""
    return "Mock" + stub_class


# ---------- 第一层：Mock vs 存根签名匹配 ----------

def _check_signatures(stub_file: str, impl_file: str, class_name: str) -> None:
    stub_path = os.path.join(STUB_DIR, stub_file)
    impl_path = os.path.join(MOCK_DIR, impl_file)
    assert os.path.exists(stub_path), f"存根缺失: {stub_file}"
    assert os.path.exists(impl_path), f"实现缺失: {impl_file}"

    stub_methods = _parse_methods(stub_path).get(class_name, {})
    impl_methods = _parse_methods(impl_path).get(_stub_to_impl_name(class_name), {})

    assert stub_methods, f"{stub_file} 中未找到类 {class_name}"
    assert impl_methods, f"{impl_file} 中未找到类 {_stub_to_impl_name(class_name)}"

    # 存根中每个方法必须在实现中存在
    missing = set(stub_methods) - set(impl_methods)
    assert not missing, f"{class_name} 实现缺失方法: {missing}"

    # 参数名集合应一致（不含 self）
    for mname, (stub_args, _) in stub_methods.items():
        impl_args = impl_methods[mname][0]
        stub_clean = [a for a in stub_args if a != "self"]
        impl_clean = [a for a in impl_args if a != "self"]
        assert stub_clean == impl_clean, (
            f"{class_name}.{mname} 参数不匹配: 存根={stub_clean} 实现={impl_clean}"
        )


def test_memory_service_signature():
    _check_signatures("memory_service.pyi", "memory_mock.py", "MemoryService")


def test_chat_service_signature():
    _check_signatures("chat_service.pyi", "chat_mock.py", "ChatService")


def test_agent_service_signature():
    _check_signatures("agent_service.pyi", "agent_mock.py", "AgentService")


def test_tool_service_signature():
    _check_signatures("tool_service.pyi", "tool_mock.py", "ToolService")


def test_graph_service_signature():
    _check_signatures("graph_service.pyi", "graph_mock.py", "GraphService")


def test_all_stubs_are_signature_only():
    """存根文件不得包含实现逻辑（仅声明签名）。"""
    for name in os.listdir(STUB_DIR):
        if not name.endswith(".pyi"):
            continue
        path = os.path.join(STUB_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                # 允许的合法形式：仅含 Ellipsis(...) 或 pass 或 docstring
                for stmt in body:
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                        continue  # docstring 或 ...
                    if isinstance(stmt, ast.Pass):
                        continue
                    raise AssertionError(
                        f"{name}::{node.name} 含实现逻辑（应仅声明签名）"
                    )


# ---------- 第二层：存根 vs 真实实现签名对比 ----------

# memory 存根 MemoryService 对应真实实现 MemoryManager 类（同名方法严格对比）
MEMORY_REAL_PATH = os.path.join(BACKEND_DIR, "core", "memory", "manager.py")

# chat/agent/tool/graph 存根方法名 → router 函数名映射
# router endpoint 与 service 方法非 1:1 签名对应（HTTP 参数差异），故做存在性校验
CHAT_METHOD_MAP = {
    "chat": "chat",
    "stream_chat": "stream_chat",
    "get_chat_history": "get_chat_history",
    "memory_agent_stream_chat": "memory_agent_stream_chat",
    "summary_agent_stream_chat": "summary_agent_stream_chat",
}
AGENT_METHOD_MAP = {
    "list_agents": "list_agents",
    "get_agent": "get_agent",
    "create_agent": "create_agent",
    "update_agent": "update_agent",
    "delete_agent": "delete_agent",
    "get_default_agent": "get_default_agent",
}
TOOL_METHOD_MAP = {
    "list_tools": "list_tools",
    "register_tool": "register_tool",
    "execute_tool": "execute_tool",
    "update_tool": "update_tool",
    "delete_tool": "delete_tool",
    "get_tool_stats": "get_tool_stats",
}
GRAPH_METHOD_MAP = {
    "create_node": "create_node",
    "get_node": "get_node",
    "update_node": "update_node",
    "delete_node": "delete_node",
    "create_edge": "create_edge",
    "get_edge": "get_edge",
    "update_edge": "update_edge",
    "delete_edge": "delete_edge",
    "traverse_bfs": "traverse_bfs",
    "traverse_dfs": "traverse_dfs",
    "shortest_path": "shortest_path",
    "semantic_search": "semantic_search",
}


def _check_router_funcs_exist(router_path: str, method_map: dict, stub_class: str) -> None:
    """验证存根方法名在 router 中有对应函数。"""
    assert os.path.exists(router_path), f"真实实现缺失: {router_path}"
    stub_path = os.path.join(STUB_DIR, f"{stub_class.split('Service')[0].lower()}_service.pyi")
    # 存根方法存在性
    stub_methods = _parse_signatures(stub_path, stub_class)
    # router 函数存在性
    real_funcs = _parse_signatures(router_path)
    for stub_method, router_func in method_map.items():
        assert stub_method in stub_methods, f"存根 {stub_class} 缺方法: {stub_method}"
        assert router_func in real_funcs, (
            f"router 缺函数: {router_func}（对应存根 {stub_class}.{stub_method}）"
        )


def test_memory_service_vs_real_impl():
    """存根 MemoryService vs 真实实现 MemoryManager 严格签名对比。

    校验：方法名集合（存根 ⊆ 实现）+ 参数名列表（顺序敏感）+ 有默认值的参数名集合。
    """
    stub_path = os.path.join(STUB_DIR, "memory_service.pyi")
    assert os.path.exists(MEMORY_REAL_PATH), f"真实实现缺失: {MEMORY_REAL_PATH}"

    stub = _parse_signatures(stub_path, "MemoryService")
    impl_class = _find_impl_class_name(MEMORY_REAL_PATH, set(stub))
    real = _parse_signatures(MEMORY_REAL_PATH, impl_class)

    # 存根方法名 ⊆ 真实实现方法名
    missing = set(stub) - set(real)
    assert not missing, f"{impl_class} 缺失存根方法: {missing}"

    # 严格对比参数名 + 顺序 + 默认值参数集合
    for mname, (stub_args, stub_defaults) in stub.items():
        real_args, real_defaults = real[mname]
        assert stub_args == real_args, (
            f"MemoryService.{mname} 参数不匹配: 存根={stub_args} 实现={real_args}"
        )
        assert stub_defaults == real_defaults, (
            f"MemoryService.{mname} 默认值参数不匹配: 存根={stub_defaults} 实现={real_defaults}"
        )


def test_chat_service_vs_real_impl():
    """存根 ChatService 方法 vs 真实实现 router 函数存在性。"""
    _check_router_funcs_exist(
        os.path.join(BACKEND_DIR, "api", "routers", "chat.py"),
        CHAT_METHOD_MAP, "ChatService",
    )


def test_agent_service_vs_real_impl():
    """存根 AgentService 方法 vs 真实实现 router 函数存在性。"""
    _check_router_funcs_exist(
        os.path.join(BACKEND_DIR, "api", "routers", "agents.py"),
        AGENT_METHOD_MAP, "AgentService",
    )


def test_tool_service_vs_real_impl():
    """存根 ToolService 方法 vs 真实实现 router 函数存在性。"""
    _check_router_funcs_exist(
        os.path.join(BACKEND_DIR, "api", "routers", "tools.py"),
        TOOL_METHOD_MAP, "ToolService",
    )


def test_graph_service_vs_real_impl():
    """存根 GraphService 方法 vs 真实实现 router 函数存在性。"""
    _check_router_funcs_exist(
        os.path.join(BACKEND_DIR, "api", "routers", "graph.py"),
        GRAPH_METHOD_MAP, "GraphService",
    )


# ---------- 直接运行入口 ----------

if __name__ == "__main__":
    import traceback

    tests = [
        test_memory_service_signature, test_chat_service_signature,
        test_agent_service_signature, test_tool_service_signature,
        test_graph_service_signature, test_all_stubs_are_signature_only,
        test_memory_service_vs_real_impl, test_chat_service_vs_real_impl,
        test_agent_service_vs_real_impl, test_tool_service_vs_real_impl,
        test_graph_service_vs_real_impl,
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
