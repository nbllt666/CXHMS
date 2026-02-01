import sys
import os
import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api.app import app
from webui.app import create_app as create_webui
import uvicorn
from config.settings import settings


def run_gradio():
    """启动 Gradio WebUI"""
    try:
        webui = create_webui()
        webui.launch(
            server_name="127.0.0.1",
            server_port=7860,
            share=False,
            debug=False,
            quiet=True,
            prevent_thread_lock=False,
            show_error=True,
            theme="soft"
        )
    except Exception as e:
        print(f"Gradio 启动失败: {e}")


def main():
    host = settings.config.system.host
    port = settings.config.system.port
    debug = settings.config.system.debug

    print(f"""
╔══════════════════════════════════════════════════════╗
║              CXHMS - AI代理中间层服务                      ║
╠══════════════════════════════════════════════════════╣
║  FastAPI服务: http://{host}:{port}                       ║
║  API文档:     http://{host}:{port}/docs                  ║
║  健康检查:    http://{host}:{port}/health                 ║
║  WebUI界面:   http://127.0.0.1:7860                       ║
╚════════════════════════════════════════════════════════╝
    """)

    import threading

    gradio_thread = threading.Thread(target=run_gradio, daemon=True)
    gradio_thread.start()

    uvicorn.run(
        "backend.api.app:app",
        host=host,
        port=port,
        reload=debug,
        log_level=settings.config.system.log_level.lower()
    )


if __name__ == "__main__":
    main()
