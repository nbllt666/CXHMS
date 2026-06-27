"""CXHMS 模拟服务器启动入口。

设置 ``CXHMS_SIMULATION`` 环境变量后启动真实 uvicorn 进程，
使 lifespan 装配假实现（FakeLLMClient / InMemoryVectorStore /
FakeEmbeddingModel / InMemoryGraphStore），从而在零外部依赖下
对外提供完整 HTTP 服务，供 Playwright 等外部客户端连接。

用法:
    python -m backend.tests.simulation.server [--host 127.0.0.1] [--port 8100]
    CXHMS_SIMULATION=1 uvicorn backend.api.app:app --port 8100  # 等效手动方式
"""

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="CXHMS 模拟服务器（零外部依赖）")
    parser.add_argument("--host", default=None, help="监听地址（默认读 settings）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认读 settings）")
    parser.add_argument(
        "--log-level",
        default=None,
        help="日志级别（默认 INFO）",
    )
    args = parser.parse_args()

    os.environ["CXHMS_SIMULATION"] = "1"
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

    import uvicorn

    from config.settings import settings

    host = args.host or getattr(settings.config.system, "host", "127.0.0.1")
    port = args.port if args.port is not None else getattr(settings.config.system, "port", 8100)
    log_level = (args.log_level or "info").lower()

    print(
        f"""
╔══════════════════════════════════════════════════════╗
║          CXHMS 模拟服务器（零外部依赖）                     ║
╠════════════════════════════════════════════════════════╣
║  模式:        CXHMS_SIMULATION=1（假实现）                 ║
║  FastAPI服务: http://{host}:{port}                       ║
║  API文档:     http://{host}:{port}/docs                  ║
║  健康检查:    http://{host}:{port}/health                 ║
╚══════════════════════════════════════════════════════════╝
    """
    )

    uvicorn.run(
        "backend.api.app:app",
        host=host,
        port=port,
        reload=False,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
