"""测试套件公共配置。

提供 public/ 目录的绝对路径解析与共享工具，支持两种使用方式：
1. 模块级常量直接 import（pytest 收集时用相对 import）：
       from .conftest import SCHEMA_DIR, load_json, try_jsonschema
2. pytest fixture 注入（推荐用于新测试）：
       def test_x(schema_dir, load_json_func): ...

执行方式（在项目根 c:\\CXHMS 下）：
    python -m pytest public/test_cases/ -v

兼容子目录调用：
    cd public\\test_cases && python -m pytest . -v --rootdir=.
"""

import os
import sys

try:
    import pytest

    _HAS_PYTEST = True
except ImportError:
    pytest = None  # type: ignore[assignment]
    _HAS_PYTEST = False

# public/ 目录绝对路径（本文件位于 public/test_cases/）
PUBLIC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(PUBLIC_DIR, "schema")
STUB_DIR = os.path.join(PUBLIC_DIR, "interface_stub")
CONFIG_DIR = os.path.join(PUBLIC_DIR, "config_template")
MOCK_DIR = os.path.join(PUBLIC_DIR, "pre_generated_mock")

# 真实实现根目录（用于 test_interface_stub.py 对比存根 vs 真实实现）
PROJECT_ROOT = os.path.dirname(PUBLIC_DIR)
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

# 将项目根加入 sys.path，便于 import public.pre_generated_mock
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def load_json(path: str) -> dict:
    """加载 JSON 文件。"""
    import json

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def try_jsonschema():
    """尝试导入 jsonschema；不可用时返回 None，由测试降级为关键字断言。"""
    try:
        import jsonschema  # noqa: F401

        return jsonschema
    except ImportError:
        return None


# ---------- pytest fixtures（标准 fixture 模式，rules-3 §五 契约可验证性要求）----------
# 保留上方模块级常量供 test_*.py 直接 import；下方 fixture 供需要注入的测试使用。

if _HAS_PYTEST:

    @pytest.fixture(scope="session")
    def schema_dir() -> str:
        """返回 public/schema/ 绝对路径。"""
        return SCHEMA_DIR

    @pytest.fixture(scope="session")
    def stub_dir() -> str:
        """返回 public/interface_stub/ 绝对路径。"""
        return STUB_DIR

    @pytest.fixture(scope="session")
    def config_dir() -> str:
        """返回 public/config_template/ 绝对路径。"""
        return CONFIG_DIR

    @pytest.fixture(scope="session")
    def mock_dir() -> str:
        """返回 public/pre_generated_mock/ 绝对路径。"""
        return MOCK_DIR

    @pytest.fixture(scope="session")
    def backend_dir() -> str:
        """返回 backend/ 绝对路径（真实实现根目录）。"""
        return BACKEND_DIR

    @pytest.fixture
    def load_json_func():
        """返回 load_json 函数。"""
        return load_json

    @pytest.fixture(scope="session")
    def jsonschema_mod():
        """返回 jsonschema 模块；不可用时返回 None。"""
        return try_jsonschema()
