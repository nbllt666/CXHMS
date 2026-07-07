"""
服务管理 API 路由
用于从前端启动/停止/重启后端服务
支持使用内置 Conda 环境或系统 Python
"""

import asyncio
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, Optional, Set

import psutil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core.logging_config import get_contextual_logger

router = APIRouter()
logger = get_contextual_logger(__name__)

# 全局变量存储后端进程
_backend_process: Optional[subprocess.Popen] = None


class ServiceStatus(BaseModel):
    """服务状态"""

    running: bool
    pid: Optional[int] = None
    port: int = 8001
    uptime: Optional[float] = None  # 运行时间（秒）
    using_conda: bool = False  # 是否使用 Conda 环境


class ServiceConfig(BaseModel):
    """服务配置"""

    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "info"
    reload: bool = False
    use_conda: bool = True  # 是否优先使用 Conda 环境


def get_project_root() -> str:
    """获取项目根目录"""
    # 从 service.py 所在位置向上回溯到项目根目录
    # service.py 在 backend/api/routers/ 下，所以向上3层
    current_file = os.path.abspath(__file__)
    # backend/api/routers/service.py -> 回到项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
    return project_root


def get_conda_python_path() -> Optional[str]:
    """获取内置 Conda 环境的 Python 路径"""
    root_dir = get_project_root()

    # 可能的 Conda Python 路径
    possible_paths = [
        os.path.join(root_dir, "Miniconda3", "python.exe"),
        os.path.join(root_dir, "Miniconda3", "envs", "base", "python.exe"),
        os.path.join(root_dir, "Miniconda3", "envs", "cx_o", "python.exe"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"Found Conda Python: {path}")
            return path

    return None


def get_conda_activate_script() -> Optional[str]:
    """获取 Conda 激活脚本路径"""
    root_dir = get_project_root()

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


@router.get("/service/status", response_model=ServiceStatus)
async def get_service_status():
    """获取后端服务状态"""
    from config.settings import settings

    process = get_backend_process()

    if process is None:
        # 尝试查找已存在的 uvicorn 进程
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline", [])
                if (
                    cmdline
                    and "uvicorn" in " ".join(cmdline)
                    and "backend.api.app:app" in " ".join(cmdline)
                ):
                    global _backend_process
                    # 找到已运行的进程，直接使用其PID
                    process = proc
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if process and process.is_running():
        try:
            uptime = time.time() - process.create_time()
        except Exception as e:
            logger.warning(f"获取运行时间失败: {e}")
            uptime = None

        # 检查是否使用了 Conda
        using_conda = False
        try:
            cmdline = process.cmdline()
            if any("miniconda" in arg.lower() or "conda" in arg.lower() for arg in cmdline):
                using_conda = True
        except Exception as e:
            logger.warning(f"检查Conda环境失败: {e}")

        return ServiceStatus(
            running=True, pid=process.pid, port=settings.config.system.port, uptime=uptime, using_conda=using_conda
        )

    return ServiceStatus(running=False, port=settings.config.system.port)


def validate_service_config(config: ServiceConfig) -> None:
    """验证服务配置，防止命令注入"""
    # 验证 host
    allowed_hosts = ["0.0.0.0", "127.0.0.1", "localhost"]
    if config.host not in allowed_hosts:
        # 验证 IP 地址格式
        import re

        if not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", config.host):
            raise HTTPException(status_code=400, detail=f"Invalid host: {config.host}")

    # 验证端口
    if not (1 <= config.port <= 65535):
        raise HTTPException(status_code=400, detail=f"Invalid port: {config.port}")

    # 验证日志级别
    allowed_log_levels = ["debug", "info", "warning", "error", "critical"]
    if config.log_level.lower() not in allowed_log_levels:
        raise HTTPException(status_code=400, detail=f"Invalid log_level: {config.log_level}")


@router.post("/service/start")
async def start_service(config: ServiceConfig):
    """启动后端服务"""
    global _backend_process

    # 验证配置
    validate_service_config(config)

    # 检查是否已在运行
    existing_process = get_backend_process()
    if existing_process is not None:
        raise HTTPException(status_code=400, detail="Service is already running")

    try:
        # 获取项目根目录
        root_dir = get_project_root()

        # 检查是否使用 Conda 环境
        conda_python = get_conda_python_path()
        conda_activate = get_conda_activate_script()
        use_conda = config.use_conda and conda_python is not None

        if use_conda and sys.platform == "win32" and conda_activate:
            # Windows: 使用 activate.bat 激活环境
            # 使用列表形式的命令避免命令注入
            cmd = [
                "cmd",
                "/c",
                f'"{conda_activate}" base && python -m uvicorn backend.api.app:app '
                f"--host {config.host} --port {config.port} --log-level {config.log_level}",
            ]
            if config.reload:
                cmd[-1] += " --reload"

            logger.info(f"Starting with Conda activate script")

            # 使用 shell=False 执行命令
            _backend_process = subprocess.Popen(
                cmd,
                cwd=root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )

        elif use_conda and conda_python:
            # 直接使用 Conda Python
            cmd = [
                conda_python,
                "-m",
                "uvicorn",
                "backend.api.app:app",
                "--host",
                config.host,
                "--port",
                str(config.port),
                "--log-level",
                config.log_level,
            ]

            if config.reload:
                cmd.append("--reload")

            logger.info(f"Starting with Conda Python: {' '.join(cmd)}")

            _backend_process = subprocess.Popen(
                cmd,
                cwd=root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )

        else:
            # 使用系统 Python
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.api.app:app",
                "--host",
                config.host,
                "--port",
                str(config.port),
                "--log-level",
                config.log_level,
            ]

            if config.reload:
                cmd.append("--reload")

            logger.info(f"Starting with system Python: {' '.join(cmd)}")

            _backend_process = subprocess.Popen(
                cmd,
                cwd=root_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )

        logger.info(
            f"Backend service started: PID={_backend_process.pid}, Port={config.port}, Conda={use_conda}"
        )

        return {
            "status": "success",
            "message": "Service started",
            "pid": _backend_process.pid,
            "port": config.port,
            "using_conda": use_conda,
        }

    except Exception as e:
        logger.error(f"Failed to start service: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start: {str(e)}")


@router.post("/service/stop")
async def stop_service():
    """停止后端服务"""
    global _backend_process

    process = get_backend_process()

    if process is None:
        # 尝试查找并停止 CXHMS 后端 uvicorn 进程
        stopped = False
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline", [])
                cmdline_str = " ".join(cmdline) if cmdline else ""
                # 仅停止 CXHMS 后端服务进程（通过 backend.api.app 标识区分）
                if cmdline_str and "uvicorn" in cmdline_str and "backend.api.app" in cmdline_str:
                    proc.terminate()
                    stopped = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if stopped:
            return {"status": "success", "message": "Service stopped"}

        raise HTTPException(status_code=400, detail="Service is not running")

    try:
        # 优雅地终止进程
        if sys.platform == "win32":
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

        logger.info("Backend service stopped")

        return {"status": "success", "message": "Service stopped"}

    except Exception as e:
        logger.error(f"Failed to stop service: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop: {str(e)}")


@router.post("/service/restart")
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


@router.get("/service/logs")
async def get_service_logs(lines: int = 100):
    """获取服务日志"""
    try:
        # 限制行数上限，防止过大请求
        lines = max(1, min(lines, 10000))

        # 读取日志文件（如果配置了日志文件）
        log_file = "logs/cxhms.log"
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                return {"status": "success", "logs": "".join(all_lines[-lines:])}

        return {"status": "success", "logs": "No log file available"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")


@router.get("/service/config")
async def get_service_config():
    """获取当前服务配置"""
    from config.settings import settings
    from config.env import EnvConfig

    # 检查 Conda 环境是否可用
    conda_available = get_conda_python_path() is not None

    # 构建完整配置响应
    config = {
        "host": settings.config.system.host,
        "port": settings.config.system.port,
        "log_level": settings.config.system.log_level,
        "debug": settings.config.system.debug,
        "conda_available": conda_available,
    }

    # 检测由环境变量管理的配置段
    active_env_overrides = EnvConfig.get_active_env_overrides()
    vector_env_keys = (
        "CXHMS_VECTOR_ENABLED",
        "CXHMS_VECTOR_BACKEND",
        "CXHMS_WEAVIATE_HOST",
        "CXHMS_WEAVIATE_PORT",
        "CXHMS_MILVUS_PATH",
        "CXHMS_VECTOR_SIZE",
    )
    models_env_keys = (
        "CXHMS_LLM_PROVIDER",
        "CXHMS_LLM_HOST",
        "CXHMS_LLM_MODEL",
        "CXHMS_LLM_API_KEY",
        "CXHMS_VLLM_HOST",
        "CXHMS_VLLM_MODEL",
        "CXHMS_SUMMARY_MODEL",
        "CXHMS_MEMORY_MODEL",
    )
    config["env_managed_sections"] = {
        "vector": any(key in active_env_overrides for key in vector_env_keys),
        "models": any(key in active_env_overrides for key in models_env_keys),
    }

    # 添加模型配置（转为 dict 并脱敏；defaults 单独通过 model_defaults 返回，避免重复）
    if hasattr(settings.config, "models"):
        models_dict = asdict(settings.config.models)
        models_dict.pop("defaults", None)
        config["models"] = EnvConfig.mask_secrets(models_dict)

    # 添加模型默认配置 - 仅返回 ModelsConfig.defaults（{summary, memory}）
    config["model_defaults"] = (
        dict(settings.config.models.defaults)
        if hasattr(settings.config.models, "defaults")
        else {"summary": "main", "memory": "main"}
    )
    llm_cfg = settings.config.llm

    # 添加LLM参数 - 从 llm 配置中提取
    llm_params = {
        "provider": llm_cfg.provider,
        "host": llm_cfg.host,
        "model": llm_cfg.model,
        "temperature": llm_cfg.temperature,
        "max_tokens": llm_cfg.max_tokens,
        "stream": llm_cfg.stream,
    }
    config["llm_params"] = llm_params

    # 添加向量配置
    if hasattr(settings.config, "memory"):
        memory_config = settings.config.memory
        vector_config = {
            "backend": getattr(memory_config, "vector_backend", "chroma"),
            "vector_size": 768,
        }

        # 根据后端类型添加特定配置
        backend = vector_config["backend"]
        if backend == "chroma" and hasattr(memory_config, "chroma"):
            chroma_cfg = memory_config.chroma
            vector_config["db_path"] = getattr(chroma_cfg, "db_path", "data/chroma_db")
            vector_config["collection_name"] = getattr(
                chroma_cfg, "collection_name", "memory_vectors"
            )
            vector_config["vector_size"] = getattr(chroma_cfg, "vector_size", 768)
        elif backend == "milvus_lite" and hasattr(memory_config, "milvus_lite"):
            milvus_cfg = memory_config.milvus_lite
            vector_config["db_path"] = getattr(milvus_cfg, "db_path", "data/milvus_lite.db")
            vector_config["vector_size"] = getattr(milvus_cfg, "vector_size", 768)
        elif backend in ["weaviate", "weaviate_embedded"] and hasattr(memory_config, "weaviate"):
            weaviate_cfg = memory_config.weaviate
            vector_config["weaviate_host"] = getattr(weaviate_cfg, "host", "localhost")
            vector_config["weaviate_port"] = getattr(weaviate_cfg, "port", 8080)
            vector_config["vector_size"] = getattr(weaviate_cfg, "vector_size", 768)
        elif backend == "qdrant" and hasattr(memory_config, "qdrant"):
            qdrant_cfg = memory_config.qdrant
            vector_config["qdrant_host"] = getattr(qdrant_cfg, "host", "localhost")
            vector_config["qdrant_port"] = getattr(qdrant_cfg, "port", 6333)
            vector_config["vector_size"] = getattr(qdrant_cfg, "vector_size", 768)

        config["vector"] = vector_config

    # 添加上下文配置
    if hasattr(settings.config, "context"):
        context_config = settings.config.context
        config["context"] = {
            "max_summaries_in_context": getattr(context_config, "max_summaries_in_context", 3),
        }

    return {"status": "success", "config": config}


@router.post("/service/config")
async def update_service_config(request: Request, config: dict):
    """更新服务配置（可选自动触发组件重初始化）。

    请求体：
        原有配置字段（vector/models/llm_params/system/...）+
        auto_reinit: bool = True  # 是否在保存后自动触发异步 reinit

    auto_reinit=True  → reload 配置 + 异步触发 reinit，返回 diff 与 reinit_task_id
    auto_reinit=False → 仅保存 YAML，返回 "manual reinit required"
    """
    try:
        # 基本配置验证
        if not config:
            raise HTTPException(status_code=400, detail="配置不能为空")
        if "port" in config and not isinstance(config["port"], int):
            raise HTTPException(status_code=400, detail="port 必须为整数")
        if "host" in config and not isinstance(config["host"], str):
            raise HTTPException(status_code=400, detail="host 必须为字符串")

        # 解析 auto_reinit（默认 True），从 config 中弹出避免写入 YAML
        auto_reinit = config.pop("auto_reinit", True)

        import yaml

        config_path = "config/default.yaml"

        # 读取现有配置
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                current_config = yaml.safe_load(f) or {}
        else:
            current_config = {}

        # 更新配置 - 根据配置类型更新对应的部分
        if "vector" in config:
            vector_cfg = config["vector"]
            if "memory" not in current_config:
                current_config["memory"] = {}

            # 更新 vector_backend
            if "backend" in vector_cfg:
                current_config["memory"]["vector_backend"] = vector_cfg["backend"]

            # 更新对应后端的配置
            backend = vector_cfg.get("backend", "chroma")
            if backend == "chroma":
                if "chroma" not in current_config["memory"]:
                    current_config["memory"]["chroma"] = {}
                if "db_path" in vector_cfg:
                    current_config["memory"]["chroma"]["db_path"] = vector_cfg["db_path"]
                if "collection_name" in vector_cfg:
                    current_config["memory"]["chroma"]["collection_name"] = vector_cfg[
                        "collection_name"
                    ]
                if "vector_size" in vector_cfg:
                    current_config["memory"]["chroma"]["vector_size"] = vector_cfg["vector_size"]
            elif backend == "milvus_lite":
                if "milvus_lite" not in current_config["memory"]:
                    current_config["memory"]["milvus_lite"] = {}
                if "db_path" in vector_cfg:
                    current_config["memory"]["milvus_lite"]["db_path"] = vector_cfg["db_path"]
                if "vector_size" in vector_cfg:
                    current_config["memory"]["milvus_lite"]["vector_size"] = vector_cfg[
                        "vector_size"
                    ]
            elif backend in ["weaviate", "weaviate_embedded"]:
                if "weaviate" not in current_config["memory"]:
                    current_config["memory"]["weaviate"] = {}
                if "weaviate_host" in vector_cfg:
                    current_config["memory"]["weaviate"]["host"] = vector_cfg["weaviate_host"]
                if "weaviate_port" in vector_cfg:
                    current_config["memory"]["weaviate"]["port"] = vector_cfg["weaviate_port"]
                if "vector_size" in vector_cfg:
                    current_config["memory"]["weaviate"]["vector_size"] = vector_cfg["vector_size"]
            elif backend == "qdrant":
                if "qdrant" not in current_config["memory"]:
                    current_config["memory"]["qdrant"] = {}
                if "qdrant_host" in vector_cfg:
                    current_config["memory"]["qdrant"]["host"] = vector_cfg["qdrant_host"]
                if "qdrant_port" in vector_cfg:
                    current_config["memory"]["qdrant"]["port"] = vector_cfg["qdrant_port"]
                if "vector_size" in vector_cfg:
                    current_config["memory"]["qdrant"]["vector_size"] = vector_cfg["vector_size"]

        if "models" in config:
            current_config["models"] = config["models"]

        if "model_defaults" in config:
            current_config["model_defaults"] = config["model_defaults"]

        if "llm_params" in config:
            llm_params_data = config["llm_params"]
            if "llm" not in current_config:
                current_config["llm"] = {}
            # 仅合并 LLMConfig 认识的字段
            for key in ("provider", "host", "model", "temperature", "max_tokens", "stream", "api_key"):
                if key in llm_params_data:
                    current_config["llm"][key] = llm_params_data[key]

        if "context" in config:
            context_data = config["context"]
            if "context" not in current_config:
                current_config["context"] = {}
            # 仅合并 ContextConfig 认识的字段
            for key in ("max_summaries_in_context",):
                if key in context_data:
                    current_config["context"][key] = context_data[key]

        # system 配置
        if "system" in config:
            if "system" not in current_config:
                current_config["system"] = {}
            current_config["system"].update(config["system"])
        elif any(k in config for k in ["host", "port", "log_level", "reload", "use_conda"]):
            if "system" not in current_config:
                current_config["system"] = {}
            for key in ["host", "port", "log_level", "reload", "use_conda"]:
                if key in config:
                    current_config["system"][key] = config[key]

        # 写回文件
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(current_config, f, allow_unicode=True, sort_keys=False)

        # auto_reinit=False → 仅保存，返回提示信息
        if not auto_reinit:
            return {
                "status": "success",
                "message": "Configuration saved, manual reinit required",
            }

        # auto_reinit=True → reload 配置并异步触发 reinit
        from config.settings import settings

        try:
            diff = settings.reload_config_with_diff()
        except Exception as e:
            logger.error(f"auto_reinit: reload 配置失败: {e}", exc_info=True)
            return {
                "status": "success",
                "message": "Configuration saved, but reload failed",
                "error": str(e),
            }

        reinit_manager = _get_reinit_manager(request)
        if reinit_manager is None:
            # reinit_manager 不可用 → 仅返回 diff，提示需手动重启
            return {
                "status": "success",
                "message": "Configuration saved, reinit_manager unavailable",
                "diff": _diff_to_dict(diff),
            }

        # 并发保护：若已有 reinit 在执行，不重复触发
        rm_status = reinit_manager.get_status()
        if rm_status.get("status") == "running":
            return {
                "status": "success",
                "message": "Configuration saved, reinit already in progress",
                "diff": _diff_to_dict(diff),
                "current_component": rm_status.get("current_component"),
            }

        # 决策组件集合
        try:
            component_set = reinit_manager.decide_components(diff)
        except Exception as e:
            logger.error(f"auto_reinit: decide_components 失败: {e}", exc_info=True)
            return {
                "status": "success",
                "message": "Configuration saved, decide_components failed",
                "diff": _diff_to_dict(diff),
                "error": str(e),
            }

        # 空集合 → 跳过 reinit
        if not component_set:
            return {
                "status": "success",
                "message": "Configuration saved, no components need reinit",
                "diff": _diff_to_dict(diff),
                "reinit_skipped": True,
            }

        # 异步触发 reinit
        task_id = str(uuid.uuid4())
        task = asyncio.create_task(
            reinit_manager.reinit(components=component_set, diff=diff)
        )
        reinit_manager._current_task = task

        return {
            "status": "accepted",
            "message": "Configuration saved, reinit triggered",
            "diff": _diff_to_dict(diff),
            "reinit_task_id": task_id,
            "estimated_components": list(component_set),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")


# --------------------------------------------------------------------------- #
# 配置热重载与组件重初始化端点（Task 5）
# --------------------------------------------------------------------------- #


def _diff_to_dict(diff: Any) -> Optional[Dict[str, Any]]:
    """将 ConfigDiff 转换为可 JSON 序列化的 dict。

    Args:
        diff: ConfigDiff 实例（或 None）。

    Returns:
        {"changed_sections": [...], "field_changes": [...]} 或 None。
    """
    if diff is None:
        return None
    return {
        "changed_sections": list(diff.changed_sections),
        "field_changes": list(diff.field_changes),
    }


def _get_reinit_manager(request: Request) -> Any:
    """从 app.state 获取 ReinitManager 实例。

    ReinitManager 由 lifespan 挂载到 app.state.reinit_manager；
    若未挂载（旧版兼容或启动失败），返回 None。
    """
    return getattr(request.app.state, "reinit_manager", None)


@router.post("/service/reload-config")
async def reload_config():
    """手动触发配置文件重载（不重初始化组件），返回 diff。

    读取 config/default.yaml 与环境变量，重新构造 CXHMSConfig 并替换
    settings 中的旧实例。返回 ConfigDiff 描述本次重载引起的变化。
    """
    from config.settings import settings

    try:
        diff = settings.reload_config_with_diff()
        return {
            "status": "success",
            "diff": _diff_to_dict(diff),
        }
    except Exception as e:
        logger.error(f"重载配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重载失败: {str(e)}")


@router.post("/service/reinit")
async def reinit_components(request: Request, body: Optional[dict] = None):
    """手动触发组件重初始化（异步执行，返回 202）。

    请求体（可选）：
        {
            "components": ["model_router", "llm_client"],  # 显式指定组件
            "reload_first": false                          # 是否先 reload 配置
        }

    行为：
        1. 检查 reinit_manager 是否可用（503 if not）
        2. 并发保护：若已有任务在执行，返回 409 conflict
        3. 决策组件集合：
           - components 显式指定 → 使用该集合
           - reload_first=True → reload_config_with_diff 后用 decide_components
           - 都未指定 → 全量 REINIT_ORDER
        4. 空集合 → 返回 skipped（200）
        5. 非空集合 → asyncio.create_task 异步执行，返回 202 accepted + task_id
    """
    body = body or {}
    components = body.get("components")
    reload_first = body.get("reload_first", False)

    reinit_manager = _get_reinit_manager(request)
    if reinit_manager is None:
        raise HTTPException(status_code=503, detail="重初始化管理器未启用")

    # 并发保护：检查是否已有任务在执行
    status = reinit_manager.get_status()
    if status.get("status") == "running":
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "message": "reinit in progress",
                "current_component": status.get("current_component"),
            },
        )

    # 决策 diff
    diff = None
    if reload_first:
        from config.settings import settings

        try:
            diff = settings.reload_config_with_diff()
        except Exception as e:
            logger.error(f"reinit 前 reload 配置失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"重载配置失败: {str(e)}")

    # 决策组件集合
    if components is not None:
        # 显式指定优先
        component_set: Optional[Set[str]] = set(components)
    elif diff is not None:
        # 由 diff 决定
        component_set = reinit_manager.decide_components(diff)
    else:
        # 全量
        component_set = None

    # diff 为空且 components 为 None 时，component_set 为 None → 全量
    # 若显式指定了 components 或由 diff 决策出空集合 → 跳过
    if component_set is not None and len(component_set) == 0:
        return {
            "status": "success",
            "message": "no components need reinit",
            "diff": _diff_to_dict(diff),
            "result": {"affected": [], "skipped": True, "success": True},
        }

    # 异步执行 reinit
    task_id = str(uuid.uuid4())
    task = asyncio.create_task(
        reinit_manager.reinit(components=component_set, diff=diff)
    )
    # 让 manager 跟踪当前 task（get_status 据此判定 running）
    reinit_manager._current_task = task

    # 计算预计影响的组件列表
    if component_set is not None:
        estimated = list(component_set)
    else:
        estimated = list(reinit_manager.REINIT_ORDER)

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "task_id": task_id,
            "estimated_components": estimated,
            "diff": _diff_to_dict(diff),
        },
    )


@router.get("/service/reinit/status")
async def get_reinit_status(request: Request):
    """查询重初始化状态。

    返回 ReinitManager.get_status() 的内容：
        运行中：{"status": "running", "current_component": ..., "progress": "N/M"}
        空闲：  {"status": "idle", "last_result": ..., "last_at": ...}
    """
    reinit_manager = _get_reinit_manager(request)
    if reinit_manager is None:
        raise HTTPException(status_code=503, detail="重初始化管理器未启用")
    return reinit_manager.get_status()


@router.get("/service/environment")
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
            "platform": sys.platform,
        },
    }


@router.get("/service/startup-command")
async def get_startup_command(use_conda: bool = True):
    """获取启动命令（供前端直接执行）"""
    conda_python = get_conda_python_path()
    conda_activate = get_conda_activate_script()
    project_root = get_project_root()

    config = {"host": "0.0.0.0", "port": 8001, "log_level": "info"}

    from config.settings import settings

    try:
        config["host"] = settings.config.system.host
        config["port"] = settings.config.system.port
        config["log_level"] = settings.config.system.log_level
    except Exception:
        pass

    startup_info = {
        "status": "success",
        "command": None,
        "args": [],
        "use_conda": use_conda,
        "conda_available": conda_python is not None,
        "project_root": project_root,
    }

    if use_conda and conda_python:
        startup_info["command"] = conda_python
        startup_info["args"] = [
            "-m",
            "uvicorn",
            "backend.api.app:app",
            "--host",
            config["host"],
            "--port",
            str(config["port"]),
            "--log-level",
            config["log_level"],
        ]
    else:
        startup_info["command"] = sys.executable
        startup_info["args"] = [
            "-m",
            "uvicorn",
            "backend.api.app:app",
            "--host",
            config["host"],
            "--port",
            str(config["port"]),
            "--log-level",
            config["log_level"],
        ]

    return startup_info


@router.get("/service/models")
async def get_available_models():
    """获取可用的模型列表"""
    import httpx

    from config.settings import settings

    models = []
    providers = []

    # 从配置获取模型信息
    models_config = settings.config.models

    # main 模型
    providers.append(
        {
            "id": "main",
            "name": models_config.main.model,
            "provider": models_config.main.provider,
            "host": models_config.main.host,
            "enabled": True,
        }
    )

    # summary 模型
    providers.append(
        {
            "id": "summary",
            "name": models_config.summary.model,
            "provider": models_config.summary.provider,
            "host": models_config.summary.host,
            "enabled": True,
        }
    )

    # memory 模型
    providers.append(
        {
            "id": "memory",
            "name": models_config.memory.model,
            "provider": models_config.memory.provider,
            "host": models_config.memory.host,
            "enabled": True,
        }
    )

    # 尝试从 Ollama 获取可用模型列表
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            main_host = models_config.main.host
            response = await client.get(f"{main_host}/api/tags")
            if response.status_code == 200:
                data = response.json()
                for model in data.get("models", []):
                    models.append(
                        {
                            "name": model.get("name", ""),
                            "size": model.get("size", 0),
                            "modified_at": model.get("modified_at", ""),
                            "details": model.get("details", {}),
                        }
                    )
    except Exception as e:
        logger.warning(f"无法获取 Ollama 模型列表: {e}")

    return {"status": "success", "providers": providers, "ollama_models": models}
