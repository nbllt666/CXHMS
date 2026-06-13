from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import json
from pathlib import Path

from backend.core.logging_config import get_contextual_logger
from config.env import EnvConfig

router = APIRouter()
logger = get_contextual_logger(__name__)


def _get_services_config() -> Dict[str, Any]:
    config_file = Path("config/settings.json")
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_services_config(config_data: Dict[str, Any]) -> None:
    config_file = Path("config/settings.json")
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)


@router.get("/config")
async def get_unified_config():
    from config.settings import settings

    services_config = _get_services_config()

    memory_config = settings.config.memory
    backend = memory_config.vector_backend

    backend_configs = {
        "chroma": memory_config.chroma,
        "milvus_lite": memory_config.milvus_lite,
        "qdrant": memory_config.qdrant,
        "weaviate": memory_config.weaviate,
    }

    vector_config = {
        "vector_enabled": memory_config.vector_enabled,
        "vector_backend": backend,
    }

    # 添加当前后端的配置
    active_backend_config = backend_configs.get(backend)
    if active_backend_config:
        vector_config["backend_config"] = EnvConfig.mask_secrets(asdict(active_backend_config))

    return {
        "status": "success",
        "config": {
            "vector": vector_config,
            "llm": {
                "provider": settings.config.llm.provider,
                "model": settings.config.llm.model,
                "host": settings.config.llm.host,
            },
            "system": {
                "debug": settings.config.system.debug,
                "log_level": settings.config.system.log_level,
            },
        }
    }


@router.put("/config")
async def update_unified_config(request: Request):
    from config.settings import settings

    try:
        data = await request.json()
        section = data.get("section")
        section_data = data.get("data", {})

        if not section:
            raise HTTPException(status_code=400, detail="Missing section")

        if section == "vector":
            if "backend" in section_data:
                settings.config.memory.vector_backend = section_data["backend"]
            if "vector_size" in section_data:
                settings.config.memory.weaviate.vector_size = section_data["vector_size"]

            settings.save_config()
            logger.info("向量配置已更新")
            return {"status": "success", "message": "Vector config saved, restart required"}

        elif section == "llm":
            if "provider" in section_data:
                settings.config.llm.provider = section_data["provider"]
            if "model" in section_data:
                settings.config.llm.model = section_data["model"]
            if "host" in section_data:
                settings.config.llm.host = section_data["host"]

            settings.save_config()
            logger.info("LLM配置已更新")
            return {"status": "success", "message": "LLM config saved, restart required"}

        elif section == "system":
            if "debug" in section_data:
                settings.config.system.debug = section_data["debug"]
            if "log_level" in section_data:
                settings.config.system.log_level = section_data["log_level"]

            settings.save_config()
            logger.info("系统配置已更新")
            return {"status": "success", "message": "System config saved"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown section: {section}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config_post(request: Request):
    return await update_unified_config(request)


def _load_yaml_config(filename: str) -> Dict[str, Any]:
    import yaml
    config_file = Path(f"config/{filename}")
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"加载配置文件 {filename} 失败: {e}")
    return {}


@router.get("/config/vector")
async def get_vector_config_endpoint():
    from config.settings import settings
    try:
        memory_config = settings.config.memory
        config = {
            "vector_enabled": getattr(memory_config, "vector_enabled", False),
            "vector_backend": getattr(memory_config, "vector_backend", "chroma"),
            "vector_size": 768,
        }
        return {"status": "success", "config": config}
    except Exception as e:
        logger.error(f"获取向量配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/llm")
async def update_llm_config(request: Request):
    from config.settings import settings
    try:
        data = await request.json()
        if "provider" in data:
            settings.config.llm.provider = data["provider"]
        if "model" in data:
            settings.config.llm.model = data["model"]
        if "host" in data:
            settings.config.llm.host = data["host"]
        settings.save_config()
        logger.info("LLM配置已更新")
        return {"status": "success", "message": "LLM配置已保存，需要重启生效"}
    except Exception as e:
        logger.error(f"更新LLM配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新LLM配置失败")


@router.get("/config/graph")
async def get_graph_config_endpoint():
    from backend.dependencies import get_graph_database as _get_graph_database
    try:
        graph = _get_graph_database()
        config = graph.config
        return {
            "status": "success",
            "config": {
                "database_path": config.database_path,
                "auto_create_schema": config.auto_create_schema,
                "pool_size": config.pool_size,
                "timeout": config.timeout,
                "weaviate": {
                    "url": config.weaviate.url,
                    "api_key": "***" if config.weaviate.api_key else None,
                    "vector_dim": config.weaviate.vector_dim,
                    "batch_size": config.weaviate.batch_size,
                    "ef_construction": config.weaviate.ef_construction,
                    "max_connections": config.weaviate.max_connections,
                },
                "embedding": {
                    "model": config.embedding.model,
                    "batch_size": config.embedding.batch_size,
                    "device": config.embedding.device,
                    "cache_folder": config.embedding.cache_folder,
                }
            }
        }
    except Exception as e:
        logger.error(f"获取图配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/cxfc")
async def get_cxfc_config_endpoint():
    from config.settings import settings
    cxfc = settings.config.cxfc
    return {
        "status": "success",
        "config": EnvConfig.mask_secrets(asdict(cxfc)),
    }
