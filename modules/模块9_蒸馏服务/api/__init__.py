"""模块9_蒸馏服务 API 子包。

提供 FastAPI app 构造入口与 4 个 REST API 端点。

公开导出:
    - create_app — FastAPI app 构造函数
    - router — API 路由器

@version 1.0.0
"""

from modules.模块9_蒸馏服务.api.app import create_app
from modules.模块9_蒸馏服务.api.routes import router

__all__ = ["create_app", "router"]

__version__ = "1.0.0"
