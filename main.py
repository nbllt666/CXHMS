import sys
import os
import httpx
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api.app import app
from config.settings import settings
import uvicorn

def main():
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

    import threading
    
    # 启动 React 前端（如果存在）
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
    if os.path.exists(frontend_dir):
        print("\n📦 检测到 React 前端，正在启动...")
        
        # 检查是否已安装依赖
        node_modules_path = os.path.join(frontend_dir, 'node_modules')
        if not os.path.exists(node_modules_path):
            print("⚠️  React 前端依赖未安装，请先运行：")
            print("   cd frontend")
            print("   npm install")
            print("\n正在仅启动后端服务...")
        else:
            # 启动 React 开发服务器
            def run_frontend():
                try:
                    subprocess.Popen(
                        ['npm', 'run', 'dev'],
                        cwd=frontend_dir,
                        shell=True
                    )
                    print("✅ React 前端开发服务器已启动")
                except Exception as e:
                    print(f"❌ React 前端启动失败: {e}")
            
            frontend_thread = threading.Thread(target=run_frontend, daemon=True)
            frontend_thread.start()
    else:
        print("\n⚠️  未检测到 React 前端目录")
        print("   如需使用新前端，请确保 frontend/ 目录存在并安装依赖")

    # 启动 FastAPI 后端
    uvicorn.run(
        "backend.api.app:app",
        host=host,
        port=port,
        reload=debug,
        log_level=settings.config.system.log_level.lower()
    )

if __name__ == "__main__":
    main()
