from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict
import logging

router = APIRouter()


@router.get("/api/admin/dashboard")
async def get_dashboard():
    from backend.api.app import get_memory_manager, get_context_manager, get_acp_manager

    stats = {
        "memory": {},
        "context": {},
        "acp": {}
    }

    try:
        memory_mgr = get_memory_manager()
        stats["memory"] = memory_mgr.get_statistics()
    except Exception:
        pass

    try:
        context_mgr = get_context_manager()
        stats["context"] = context_mgr.get_statistics()
    except Exception:
        pass

    try:
        acp_mgr = get_acp_manager()
        stats["acp"] = await acp_mgr.get_statistics()
    except Exception:
        pass

    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "dashboard": stats
    }


@router.get("/api/admin/stats")
async def get_stats():
    from backend.api.app import get_memory_manager, get_context_manager
    from backend.core.tools.registry import tool_registry

    stats = {
        "memory": {},
        "context": {},
        "tools": {}
    }

    try:
        memory_mgr = get_memory_manager()
        stats["memory"] = memory_mgr.get_statistics()
    except Exception:
        pass

    try:
        context_mgr = get_context_manager()
        stats["context"] = context_mgr.get_statistics()
    except Exception:
        pass

    try:
        stats["tools"] = tool_registry.get_tool_stats()
    except Exception:
        pass

    return {
        "status": "success",
        "statistics": stats
    }


@router.get("/api/admin/health")
async def health_check():
    from backend.api.app import get_memory_manager, get_context_manager, get_acp_manager

    health = {
        "memory": "unknown",
        "context": "unknown",
        "acp": "unknown"
    }

    try:
        memory_mgr = get_memory_manager()
        health["memory"] = "healthy"
    except Exception:
        health["memory"] = "unhealthy"

    try:
        context_mgr = get_context_manager()
        health["context"] = "healthy"
    except Exception:
        health["context"] = "unhealthy"

    try:
        acp_mgr = get_acp_manager()
        acp_stats = await acp_mgr.get_statistics()
        health["acp"] = "healthy" if acp_stats.get("total_agents", 0) >= 0 else "unhealthy"
    except Exception:
        health["acp"] = "unhealthy"

    overall = "healthy" if all(h == "healthy" for h in health.values()) else "degraded"

    return {
        "status": overall,
        "components": health
    }


@router.get("/api/admin/config")
async def get_config():
    from config.settings import settings

    return {
        "status": "success",
        "config": {
            "llm": {
                "provider": settings.config.llm.provider,
                "host": settings.config.llm.host,
                "model": settings.config.llm.model
            },
            "vector": {
                "enabled": settings.config.vector.enabled,
                "host": settings.config.vector.host,
                "port": settings.config.vector.port
            },
            "acp": {
                "enabled": settings.config.acp.enabled,
                "agent_id": settings.config.acp.agent_id,
                "agent_name": settings.config.acp.agent_name
            },
            "system": {
                "host": settings.config.system.host,
                "port": settings.config.system.port,
                "debug": settings.config.system.debug
            }
        }
    }


@router.put("/api/admin/config")
async def update_config(config: Dict):
    from config.settings import settings

    try:
        if "llm" in config:
            if "provider" in config["llm"]:
                settings.config.llm.provider = config["llm"]["provider"]
            if "host" in config["llm"]:
                settings.config.llm.host = config["llm"]["host"]
            if "model" in config["llm"]:
                settings.config.llm.model = config["llm"]["model"]

        if "vector" in config:
            if "enabled" in config["vector"]:
                settings.config.vector.enabled = config["vector"]["enabled"]
            if "host" in config["vector"]:
                settings.config.vector.host = config["vector"]["host"]
            if "port" in config["vector"]:
                settings.config.vector.port = config["vector"]["port"]

        if "acp" in config:
            if "enabled" in config["acp"]:
                settings.config.acp.enabled = config["acp"]["enabled"]
            if "agent_id" in config["acp"]:
                settings.config.acp.agent_id = config["acp"]["agent_id"]
            if "agent_name" in config["acp"]:
                settings.config.acp.agent_name = config["acp"]["agent_name"]

        if "system" in config:
            if "host" in config["system"]:
                settings.config.system.host = config["system"]["host"]
            if "port" in config["system"]:
                settings.config.system.port = config["system"]["port"]
            if "debug" in config["system"]:
                settings.config.system.debug = config["system"]["debug"]

        settings.save_config()

        return {
            "status": "success",
            "message": "配置已更新"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/logs")
async def get_logs(level: str = "INFO", lines: int = 50):
    from config.settings import settings

    log_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger()

    logs = []
    for handler in logger.handlers:
        if hasattr(handler, 'buffer'):
            continue

    return {
        "status": "success",
        "logs": ["日志功能暂未完全实现", "请使用命令行查看日志"],
        "total": 2
    }


@router.post("/api/admin/backup")
async def create_backup():
    import shutil
    import os
    from datetime import datetime

    try:
        data_dir = "data"
        backup_dir = "data/backups"

        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{backup_dir}/backup_{timestamp}.zip"

        shutil.make_archive(
            backup_file.replace(".zip", ""),
            'zip',
            data_dir
        )

        return {
            "status": "success",
            "path": backup_file,
            "message": f"备份已创建: {backup_file}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
