"""
服务管理 API 路由
用于从前端启动/停止/重启后端服务
支持使用内置 Conda 环境或系统 Python
"""
import subprocess
import os
import signal
import sys
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psutil
import logging
import time

router = APIRouter()
logger = logging.getLogger(__name__)

# 全局变量存储后端进程
_backend_process: Optional[subprocess.Popen] = None


class ServiceStatus(BaseModel):
    """服务状态"""
    running: bool
    pid: Optional[int] = None
    port: int = 8000
    uptime: Optional[float] = None  # 运行时间（秒）
    using_conda: bool = False  # 是否使用 Conda 环境


class ServiceConfig(BaseModel):
    """服务配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    reload: bool = False
    use_conda: bool = True  # 是否优先使用 Conda 环境


def get_conda_python_path() -> Optional[str]:
    """获取内置 Conda 环境的 Python 路径"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    # 可能的 Conda Python 路径
    possible_paths = [
        os.path.join(root_dir, "Miniconda3", "python.exe"),
        os.path.join(root_dir, "Miniconda3", "envs", "base", "python.exe"),
        os.path.join(root_dir, "Miniconda3", "envs", "cx_o", "python.exe"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"找到 Conda Python: {path}")
            return path
    
    return None


def get_conda_activate_script() -> Optional[str]:
    """获取 Conda 激活脚本路径"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    activate_script = os.path.join(root_dir, "Miniconda3", "Scripts", "activate.bat")
    if os.path.exists(activate_script):
        return activate_script
    
    return None


def get_backend_process() -> Optional[psutil.Process]:
    """获取后端进程"""
    global _backend_process
    if _backend_process is None:
        return None
    
    try:
        process = psutil.Process(_backend_process.pid)
        if process.is_running():
            return process
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    
    _backend_process = None
    return None


@router.get("/api/service/status", response_model=ServiceStatus)
async def get_service_status():
    """获取后端服务状态"""
    process = get_backend_process()
    
    if process is None:
        # 尝试查找已存在的 uvicorn 进程
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'uvicorn' in ' '.join(cmdline) and 'backend.api.app:app' in ' '.join(cmdline):
                    global _backend_process
                    _backend_process = subprocess.Popen(
                        ['echo', 'dummy'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    _backend_process._pid = proc.info['pid']
                    process = proc
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    
    if process and process.is_running():
        try:
            uptime = time.time() - process.create_time()
        except:
            uptime = None
        
        # 检查是否使用了 Conda
        using_conda = False
        try:
            cmdline = process.cmdline()
            if any('miniconda' in arg.lower() or 'conda' in arg.lower() for arg in cmdline):
                using_conda = True
        except:
            pass
        
        return ServiceStatus(
            running=True,
            pid=process.pid,
            port=8000,
            uptime=uptime,
            using_conda=using_conda
        )
    
    return ServiceStatus(running=False, port=8000)


@router.post("/api/service/start")
async def start_service(config: ServiceConfig):
    """启动后端服务"""
    global _backend_process
    
    # 检查是否已在运行
    if get_backend_process() is not None:
        raise HTTPException(status_code=400, detail="服务已在运行中")
    
    try:
        # 获取项目根目录
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # 检查是否使用 Conda 环境
        conda_python = get_conda_python_path()
        conda_activate = get_conda_activate_script()
        use_conda = config.use_conda and conda_python is not None
        
        if use_conda and sys.platform == 'win32' and conda_activate:
            # Windows: 使用 activate.bat 激活环境
            cmd = [
                "cmd", "/c",
                f'"{conda_activate}" base && python -m uvicorn backend.api.app:app '
                f'--host {config.host} --port {config.port} --log-level {config.log_level}'
            ]
            if config.reload:
                cmd[-1] += " --reload"
            
            # 使用 shell=True 执行命令
            _backend_process = subprocess.Popen(
                ' '.join(cmd),
                cwd=root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
        elif use_conda and conda_python:
            # 直接使用 Conda Python
            cmd = [
                conda_python, "-m", "uvicorn",
                "backend.api.app:app",
                "--host", config.host,
                "--port", str(config.port),
                "--log-level", config.log_level
            ]
            
            if config.reload:
                cmd.append("--reload")
            
            _backend_process = subprocess.Popen(
                cmd,
                cwd=root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )
            
        else:
            # 使用系统 Python
            cmd = [
                sys.executable, "-m", "uvicorn",
                "backend.api.app:app",
                "--host", config.host,
                "--port", str(config.port),
                "--log-level", config.log_level
            ]
            
            if config.reload:
                cmd.append("--reload")
            
            _backend_process = subprocess.Popen(
                cmd,
                cwd=root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )
        
        logger.info(f"后端服务已启动: PID={_backend_process.pid}, Port={config.port}, Conda={use_conda}")
        
        return {
            "status": "success",
            "message": "服务已启动",
            "pid": _backend_process.pid,
            "port": config.port,
            "using_conda": use_conda
        }
        
    except Exception as e:
        logger.error(f"启动服务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")


@router.post("/api/service/stop")
async def stop_service():
    """停止后端服务"""
    global _backend_process
    
    process = get_backend_process()
    
    if process is None:
        # 尝试查找并停止 uvicorn 进程
        stopped = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'uvicorn' in ' '.join(cmdline):
                    proc.terminate()
                    stopped = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if stopped:
            return {"status": "success", "message": "服务已停止"}
        
        raise HTTPException(status_code=400, detail="服务未在运行")
    
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
            # 强制终止
            process.kill()
        
        _backend_process = None
        
        logger.info("后端服务已停止")
        
        return {"status": "success", "message": "服务已停止"}
        
    except Exception as e:
        logger.error(f"停止服务失败: {e}")
        raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")


@router.post("/api/service/restart")
async def restart_service(config: ServiceConfig):
    """重启后端服务"""
    try:
        # 先停止
        await stop_service()
    except HTTPException:
        # 服务可能未运行，忽略错误
        pass
    
    # 等待一下确保端口释放
    import asyncio
    await asyncio.sleep(1)
    
    # 再启动
    return await start_service(config)


@router.get("/api/service/logs")
async def get_service_logs(lines: int = 100):
    """获取服务日志"""
    try:
        # 读取日志文件（如果配置了日志文件）
        log_file = "logs/cxhms.log"
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return {
                    "status": "success",
                    "logs": ''.join(all_lines[-lines:])
                }
        
        return {
            "status": "success",
            "logs": "暂无日志文件"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {str(e)}")


@router.get("/api/service/config")
async def get_service_config():
    """获取当前服务配置"""
    from config.settings import settings
    
    # 检查 Conda 环境是否可用
    conda_available = get_conda_python_path() is not None
    
    return {
        "status": "success",
        "config": {
            "host": settings.config.system.host,
            "port": settings.config.system.port,
            "log_level": settings.config.system.log_level,
            "debug": settings.config.system.debug,
            "conda_available": conda_available
        }
    }


@router.post("/api/service/config")
async def update_service_config(config: dict):
    """更新服务配置（需要重启生效）"""
    try:
        # 保存配置到文件
        import yaml
        
        config_path = "config/default.yaml"
        
        # 读取现有配置
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f) or {}
        else:
            current_config = {}
        
        # 更新配置
        if 'system' not in current_config:
            current_config['system'] = {}
        
        current_config['system'].update(config)
        
        # 写回文件
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, sort_keys=False)
        
        return {
            "status": "success",
            "message": "配置已更新，重启服务后生效"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")


@router.get("/api/service/environment")
async def get_environment_info():
    """获取环境信息"""
    conda_python = get_conda_python_path()
    conda_activate = get_conda_activate_script()
    
    return {
        "status": "success",
        "environment": {
            "conda_available": conda_python is not None,
            "conda_python_path": conda_python,
            "conda_activate_script": conda_activate,
            "system_python": sys.executable,
            "platform": sys.platform
        }
    }
