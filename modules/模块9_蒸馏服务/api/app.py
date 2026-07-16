"""DistillationService FastAPI app 构造。

独立 FastAPI 子服务（端口 8011），承载 7 状态机多轮蒸馏工作流。
与主后端（8001）通过 HTTP REST API 通信。

@version 1.0.0
"""

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI

from modules.模块9_蒸馏服务.api.routes import router
from modules.模块9_蒸馏服务.distillation_service import DistillationService


def create_app(
    config: Optional[Dict[str, Any]] = None,
    service: Optional[DistillationService] = None,
) -> FastAPI:
    """构造 DistillationService FastAPI app。

    Args:
        config: 配置字典（None 时从 radix_config.json 加载）
        service: 已实例化的 DistillationService（None 时自动实例化）

    Returns:
        FastAPI app 实例
    """
    app = FastAPI(
        title="RADIX-Lite DistillationService",
        description=(
            "RADIX-Lite 蒸馏服务，独立 FastAPI 子服务（端口 8011）。"
            "承载 7 状态机多轮蒸馏工作流。"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 实例化 DistillationService
    if service is None:
        service = DistillationService(config=config)
    app.state.distillation_service = service

    # 注册路由
    app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health_check() -> Dict[str, Any]:
        """健康检查端点（rules-0 §三 health_check: API轻量连通性）。

        Returns:
            服务状态字典
        """
        return {
            "status": "ok",
            "service": "DistillationService",
            "port": (
                service._config.get("port", 8011)
                if hasattr(service, "_config")
                else 8011
            ),
        }

    return app


def main() -> None:
    """主入口：启动 DistillationService FastAPI 子服务。

    使用 uvicorn 启动，监听端口 8011（默认，可由 radix_config.json 配置）。
    """
    import uvicorn

    app = create_app()
    service = app.state.distillation_service
    host = service._config.get("host", "127.0.0.1")
    port = int(service._config.get("port", 8011))

    print(
        f"[INFO] [{__file__}] DistillationService 启动: "
        f"http://{host}:{port} (docs: /docs)"
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
