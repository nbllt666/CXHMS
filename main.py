"""
CXHMS 启动脚本
支持从前端启动或独立启动
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from config.settings import settings


def main():
    """主函数"""
    host = settings.config.system.host
    port = settings.config.system.port
    debug = settings.config.system.debug

    print(f"""
╔══════════════════════════════════════════════════════╗
║              CXHMS - 晨曦人格化记忆系统                     ║
╠════════════════════════════════════════════════════════╣
║  FastAPI服务: http://{host}:{port}                       ║
║  API文档:     http://{host}:{port}/docs                  ║
║  健康检查:    http://{host}:{port}/health                 ║
╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "backend.api.app:app",
        host=host,
        port=port,
        reload=debug,
        log_level=settings.config.system.log_level.lower()
    )


if __name__ == "__main__":
    main()
