from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import asyncio

from config.settings import settings
from backend.api.routers import chat, memory, context, tools, acp, admin, archive, service, agents, websocket, backup
from backend.api.response import APIResponse, HealthResponse
from backend.api.exceptions import (
    CXHMSError,
    cxhms_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)
from backend.core.logging_config import setup_logging, get_contextual_logger, LogContext

# 配置结构化日志
log_file_config = getattr(settings.config, 'logging', {})
log_file = log_file_config.get('file', 'logs/app.log') if isinstance(log_file_config, dict) else 'logs/app.log'

setup_logging(
    level=settings.config.system.log_level,
    log_file=log_file,
    max_bytes=log_file_config.get('max_bytes', 10*1024*1024) if isinstance(log_file_config, dict) else 10*1024*1024,
    backup_count=log_file_config.get('backup_count', 5) if isinstance(log_file_config, dict) else 5,
    structured=False,  # 可以设置为 True 启用 JSON 格式日志
    console_colors=True
)

logger = get_contextual_logger(__name__)

memory_manager = None
context_manager = None
acp_manager = None
llm_client = None
secondary_router = None
decay_batch_processor = None
mcp_manager = None
model_router = None  # 新增：模型路由器

@asynccontextmanager
async def lifespan(app: FastAPI):
    global memory_manager, context_manager, acp_manager, llm_client, secondary_router, decay_batch_processor, mcp_manager, model_router

    from backend.core.memory.manager import MemoryManager
    from backend.core.context.manager import ContextManager
    from backend.core.acp.manager import ACPManager
    from backend.core.llm.client import LLMFactory
    from backend.core.memory.secondary_router import SecondaryModelRouter
    from backend.core.memory.decay_batch import DecayBatchProcessor
    from backend.core.tools.mcp import MCPManager
    from backend.core.tools.registry import tool_registry
    from backend.core.model_router import model_router as mr  # 导入模型路由器

    logger.info("正在启动CXHMS服务...")

    # 1. 初始化模型路由器（最先初始化，其他组件可能依赖它）
    try:
        model_router = mr
        await model_router.initialize()
        logger.info("模型路由器已启动")
    except Exception as e:
        logger.warning(f"模型路由器启动失败: {e}")
        model_router = None

    try:
        db_config = settings.config.database
        memory_manager = MemoryManager(db_path=db_config.memories_db)
        logger.info("记忆管理器已启动")
    except Exception as e:
        logger.warning(f"记忆管理器启动失败: {e}")
        memory_manager = None

    try:
        db_config = settings.config.database
        context_manager = ContextManager(db_path=db_config.sessions_db)
        logger.info("上下文管理器已启动")
    except Exception as e:
        logger.warning(f"上下文管理器启动失败: {e}")
        context_manager = None

    try:
        db_config = settings.config.database
        acp_manager = ACPManager(data_dir=db_config.acp_db)
        acp_manager.initialize(
            agent_id=settings.config.acp.agent_id,
            agent_name=settings.config.acp.agent_name
        )
        await acp_manager.start()
        logger.info("ACP管理器已启动")
    except Exception as e:
        logger.warning(f"ACP管理器启动失败: {e}")
        acp_manager = None

    # 使用模型路由器的主模型客户端作为默认LLM客户端（向后兼容）
    try:
        if model_router:
            llm_client = model_router.get_client("main")
            logger.info(f"LLM客户端已启动: {llm_client.model_name if llm_client else 'None'}")
        else:
            # 回退到旧方式
            llm_client = LLMFactory.create_client(
                provider=settings.config.llm.provider,
                host=settings.config.llm.host,
                model=settings.config.llm.model,
                temperature=settings.config.llm.temperature,
                max_tokens=settings.config.llm.max_tokens
            )
            logger.info(f"LLM客户端已启动(回退模式): {llm_client.model_name}")
    except Exception as e:
        logger.warning(f"LLM客户端启动失败: {e}")
        llm_client = None

    try:
        if memory_manager:
            secondary_router = SecondaryModelRouter(
                memory_manager,
                llm_client,
                model_router=model_router,
                context_manager=context_manager
            )
            logger.info("副模型路由器已启动")
    except Exception as e:
        logger.warning(f"副模型路由器启动失败: {e}")
        secondary_router = None

    try:
        mcp_manager = MCPManager()
        mcp_manager.set_tool_registry(tool_registry)
        logger.info("MCP管理器已启动")
    except Exception as e:
        logger.warning(f"MCP管理器启动失败: {e}")
        mcp_manager = None

    # 注册内置工具
    try:
        from backend.core.tools import register_builtin_tools
        register_builtin_tools()
        logger.info("内置工具已注册")
    except Exception as e:
        logger.warning(f"内置工具注册失败: {e}")
    
    # 注册主模型工具
    master_tools_registered = False
    try:
        from backend.core.tools import (
            register_master_tools,
            set_master_dependencies
        )
        set_master_dependencies(
            memory_manager=memory_manager,
            secondary_router=secondary_router,
            context_manager=context_manager,
            acp_manager=acp_manager
        )
        register_master_tools()
        master_tools_registered = True
        logger.info("主模型工具已注册")
    except Exception as e:
        logger.warning(f"主模型工具注册失败: {e}")
    
    # 注册摘要模型工具
    summary_tools_registered = False
    try:
        from backend.core.tools import (
            register_summary_tools,
            set_summary_dependencies
        )
        set_summary_dependencies(
            memory_manager=memory_manager,
            model_router=model_router,
            context_manager=context_manager
        )
        register_summary_tools()
        summary_tools_registered = True
        logger.info("摘要模型工具已注册")
    except Exception as e:
        logger.warning(f"摘要模型工具注册失败: {e}")
    
    # 注册记忆管理模型工具
    assistant_tools_registered = False
    try:
        from backend.core.tools import (
            register_assistant_tools,
            set_assistant_dependencies
        )
        set_assistant_dependencies(
            memory_manager=memory_manager,
            secondary_router=secondary_router,
            context_manager=context_manager
        )
        register_assistant_tools()
        assistant_tools_registered = True
        logger.info("记忆管理模型工具已注册")
    except Exception as e:
        logger.warning(f"记忆管理模型工具注册失败: {e}")
    
    # 验证工具注册状态
    from backend.core.tools import tool_registry
    tools_stats = tool_registry.get_tool_stats()
    logger.info(f"工具注册统计: 总计{tools_stats['total_tools']}个, "
                f"启用{tools_stats['enabled_tools']}个, "
                f"禁用{tools_stats['disabled_tools']}个")
    
    if not (master_tools_registered and summary_tools_registered and assistant_tools_registered):
        logger.warning("部分工具注册失败，系统可能无法正常工作")

    try:
        if memory_manager and llm_client and settings.config.memory.vector_enabled:
            vector_backend = settings.config.memory.vector_backend
            if vector_backend == "chroma":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="chroma",
                    db_path=settings.config.memory.chroma.db_path,
                    collection_name=settings.config.memory.chroma.collection_name,
                    vector_size=settings.config.memory.chroma.vector_size
                )
            elif vector_backend == "milvus_lite":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="milvus_lite",
                    milvus_db_path=settings.config.memory.milvus_lite.db_path
                )
            elif vector_backend == "qdrant":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="qdrant",
                    qdrant_host=settings.config.memory.qdrant.host,
                    qdrant_port=settings.config.memory.qdrant.port
                )
            elif vector_backend == "weaviate":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="weaviate",
                    host=settings.config.memory.weaviate.host,
                    port=settings.config.memory.weaviate.port,
                    grpc_port=settings.config.memory.weaviate.grpc_port,
                    embedded=False,
                    vector_size=settings.config.memory.weaviate.vector_size,
                    schema_class=settings.config.memory.weaviate.schema_class
                )
            elif vector_backend == "weaviate_embedded":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="weaviate_embedded",
                    embedded=True,
                    vector_size=settings.config.memory.weaviate.vector_size,
                    schema_class=settings.config.memory.weaviate.schema_class
                )
            logger.info(f"向量搜索已启用: {vector_backend}")
    except Exception as e:
        logger.warning(f"向量搜索启动失败: {e}")

    try:
        if memory_manager:
            decay_batch_processor = DecayBatchProcessor(memory_manager, interval_hours=24)
            await decay_batch_processor.start()
            logger.info("批量衰减处理器已启动")
    except Exception as e:
        logger.warning(f"批量衰减处理器启动失败: {e}")
        decay_batch_processor = None

    yield

    logger.info("正在关闭CXHMS服务...")

    if decay_batch_processor:
        await decay_batch_processor.stop()

    if acp_manager:
        await acp_manager.stop()

    if memory_manager:
        memory_manager.shutdown()

    # 关闭模型路由器
    if model_router:
        await model_router.close()

    logger.info("CXHMS服务已关闭")


app = FastAPI(
    title="CXHMS - CX-O History & Memory Service",
    description="AI代理中间层服务，提供记忆管理、工具调用、ACP互联等功能",
    version="1.0.0",
    lifespan=lifespan
)

# CORS配置
if getattr(settings.config, 'cors', None) and settings.config.cors.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.config.cors.origins,
        allow_credentials=settings.config.cors.allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"]
    )

app.include_router(chat.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(context.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(acp.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(archive.router, prefix="/api")
app.include_router(service.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(websocket.router)

app.add_exception_handler(CXHMSError, cxhms_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    components = {
        "memory_manager": memory_manager is not None,
        "context_manager": context_manager is not None,
        "acp_manager": acp_manager is not None,
        "llm_client": llm_client is not None,
        "model_router": model_router is not None
    }
    return HealthResponse(
        status="healthy" if all(components.values()) else "degraded",
        version="1.0.0",
        components=components
    )


@app.get("/")
async def root():
    return {
        "service": "CXHMS",
        "version": "1.0.0",
        "description": "CX-O History & Memory Service",
        "docs": "/docs",
        "redoc": "/redoc"
    }


def get_memory_manager():
    if memory_manager is None:
        raise HTTPException(status_code=503, detail="记忆服务不可用")
    return memory_manager


def get_context_manager():
    if context_manager is None:
        raise HTTPException(status_code=503, detail="上下文服务不可用")
    return context_manager


def get_acp_manager():
    if acp_manager is None:
        raise HTTPException(status_code=503, detail="ACP服务不可用")
    return acp_manager


def get_llm_client():
    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM服务不可用")
    return llm_client

def get_secondary_router():
    if secondary_router is None:
        raise HTTPException(status_code=503, detail="副模型路由器不可用")
    return secondary_router

def get_decay_batch_processor():
    if decay_batch_processor is None:
        raise HTTPException(status_code=503, detail="批量衰减处理器不可用")
    return decay_batch_processor

def get_mcp_manager():
    if mcp_manager is None:
        raise HTTPException(status_code=503, detail="MCP管理器不可用")
    return mcp_manager

def get_model_router():
    if model_router is None:
        raise HTTPException(status_code=503, detail="模型路由器不可用")
    return model_router
