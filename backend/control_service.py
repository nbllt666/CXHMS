"""
CXHMS 控制服务
轻量级 FastAPI 服务，用于控制主后端服务的启动/停止/重启
端口: 8765
"""
import subprocess
import os
import sys
import signal
from typing import Optional

# 添加项目根目录到 sys.path，确保 backend 模块可导入
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psutil
import time

from backend.core.logging_config import setup_logging, get_contextual_logger

# 配置结构化日志
setup_logging(
    level="INFO",
    log_file="logs/control_service.log",
    structured=False,
    console_colors=True
)
logger = get_contextual_logger(__name__)

app = FastAPI(title="CXHMS Control Service", version="1.0.0")

# 启用 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量存储主后端进程
_main_backend_process: Optional[subprocess.Popen] = None

class ServiceStatus(BaseModel):
    """服务状态"""
    running: bool
    pid: Optional[int] = None
    port: int = 8000
    uptime: Optional[float] = None

class ControlResponse(BaseModel):
    """控制响应"""
    status: str
    message: str
    pid: Optional[int] = None

def get_project_root() -> str:
    """获取项目根目录"""
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(current_file)
    return project_root

def get_conda_python_path() -> Optional[str]:
    """获取内置 Conda 环境的 Python 路径"""
    root_dir = get_project_root()
    possible_paths = [
        os.path.join(root_dir, "Miniconda3", "python.exe"),
        os.path.join(root_dir, "Miniconda3", "envs", "base", "python.exe"),
        os.path.join(root_dir, "Miniconda3", "envs", "cx_o", "python.exe"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def get_main_backend_process() -> Optional[psutil.Process]:
    """获取主后端进程"""
    global _main_backend_process
    if _main_backend_process is None:
        return None
    try:
        process = psutil.Process(_main_backend_process.pid)
        if process.is_running():
            return process
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    _main_backend_process = None
    return None

@app.get("/")
async def root():
    """根路径"""
    return {"message": "CXHMS Control Service", "version": "1.0.0"}

@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}

@app.get("/control/status", response_model=ServiceStatus)
async def get_main_service_status():
    """获取主后端服务状态"""
    process = get_main_backend_process()
    
    if process is None:
        # 尝试查找已存在的 uvicorn 进程
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'uvicorn' in ' '.join(cmdline) and 'backend.api.app:app' in ' '.join(cmdline):
                    global _main_backend_process
                    _main_backend_process = subprocess.Popen(
                        ['echo', 'dummy'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    _main_backend_process._pid = proc.info['pid']
                    process = proc
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    
    if process and process.is_running():
        try:
            uptime = time.time() - process.create_time()
        except Exception:
            uptime = None
        return ServiceStatus(
            running=True,
            pid=process.pid,
            port=8000,
            uptime=uptime
        )
    
    return ServiceStatus(running=False, port=8000)

@app.post("/control/start", response_model=ControlResponse)
async def start_main_service():
    """启动主后端服务"""
    global _main_backend_process
    
    # 检查是否已在运行
    existing = get_main_backend_process()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Main backend service is already running")
    
    try:
        root_dir = get_project_root()
        conda_python = get_conda_python_path()
        
        if conda_python and sys.platform == 'win32':
            # 使用 Conda Python 启动
            cmd = [
                conda_python, "-m", "uvicorn",
                "backend.api.app:app",
                "--host", "0.0.0.0",
                "--port", "8000",
                "--log-level", "info"
            ]
            logger.info(f"Starting main backend with Conda Python: {conda_python}")
        else:
            # 使用系统 Python
            cmd = [
                sys.executable, "-m", "uvicorn",
                "backend.api.app:app",
                "--host", "0.0.0.0",
                "--port", "8000",
                "--log-level", "info"
            ]
            logger.info(f"Starting main backend with system Python: {sys.executable}")
        
        # 启动进程
        _main_backend_process = subprocess.Popen(
            cmd,
            cwd=root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        
        logger.info(f"Main backend service started: PID={_main_backend_process.pid}")
        
        return ControlResponse(
            status="success",
            message="Main backend service started",
            pid=_main_backend_process.pid
        )
        
    except Exception as e:
        logger.error(f"Failed to start main backend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start: {str(e)}")

@app.post("/control/stop", response_model=ControlResponse)
async def stop_main_service():
    """停止主后端服务"""
    global _main_backend_process
    
    process = get_main_backend_process()
    
    if process is None:
        # 尝试查找并停止 uvicorn 进程
        stopped = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'uvicorn' in ' '.join(cmdline) and 'backend.api.app:app' in ' '.join(cmdline):
                    proc.terminate()
                    stopped = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if stopped:
            return ControlResponse(status="success", message="Main backend service stopped")
        
        raise HTTPException(status_code=400, detail="Main backend service is not running")
    
    try:
        # 优雅地终止进程
        if sys.platform == 'win32':
            process.terminate()
        else:
            process.send_signal(signal.SIGTERM)
        
        # 等待进程结束
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
        
        _main_backend_process = None
        logger.info("Main backend service stopped")
        
        return ControlResponse(status="success", message="Main backend service stopped")
        
    except Exception as e:
        logger.error(f"Failed to stop main backend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop: {str(e)}")

@app.post("/control/restart", response_model=ControlResponse)
async def restart_main_service():
    """重启主后端服务"""
    try:
        await stop_main_service()
    except HTTPException:
        pass
    
    # 等待端口释放
    import asyncio
    await asyncio.sleep(1)
    
    return await start_main_service()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
