from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import asyncio

from config.settings import settings
from backend.api.routers import chat, memory, context, tools, acp, admin

logging.basicConfig(
    level=getattr(logging, settings.config.system.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

memory_manager = None
context_manager = None
acp_manager = None
llm_client = None
secondary_router = None
decay_batch_processor = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global memory_manager, context_manager, acp_manager, llm_client, secondary_router, decay_batch_processor

    from backend.core.memory.manager import MemoryManager
    from backend.core.context.manager import ContextManager
    from backend.core.acp.manager import ACPManager
    from backend.core.llm.client import LLMFactory
    from backend.core.memory.secondary_router import SecondaryModelRouter
    from backend.core.memory.decay_batch import DecayBatchProcessor

    logger.info("正在启动CXHMS服务...")

    try:
        memory_manager = MemoryManager()
        logger.info("记忆管理器已启动")
    except Exception as e:
        logger.warning(f"记忆管理器启动失败: {e}")
        memory_manager = None

    try:
        context_manager = ContextManager()
        logger.info("上下文管理器已启动")
    except Exception as e:
        logger.warning(f"上下文管理器启动失败: {e}")
        context_manager = None

    try:
        acp_manager = ACPManager()
        acp_manager.initialize(
            agent_id=settings.config.acp.agent_id,
            agent_name=settings.config.acp.agent_name
        )
        await acp_manager.start()
        logger.info("ACP管理器已启动")
    except Exception as e:
        logger.warning(f"ACP管理器启动失败: {e}")
        acp_manager = None

    try:
        llm_client = LLMFactory.create_client(
            provider=settings.config.llm.provider,
            host=settings.config.llm.host,
            model=settings.config.llm.model,
            temperature=settings.config.llm.temperature,
            max_tokens=settings.config.llm.max_tokens
        )
        logger.info(f"LLM客户端已启动: {llm_client.model_name}")
    except Exception as e:
        logger.warning(f"LLM客户端启动失败: {e}")
        llm_client = None

    try:
        if memory_manager:
            secondary_router = SecondaryModelRouter(memory_manager, llm_client)
            logger.info("副模型路由器已启动")
    except Exception as e:
        logger.warning(f"副模型路由器启动失败: {e}")
        secondary_router = None

    try:
        if memory_manager and llm_client and settings.config.memory.vector_enabled:
            vector_backend = settings.config.memory.vector_backend
            if vector_backend == "milvus_lite":
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

    logger.info("CXHMS服务已关闭")


app = FastAPI(
    title="CXHMS - CX-O History & Memory Service",
    description="AI代理中间层服务，提供记忆管理、工具调用、ACP互联等功能",
    version="1.0.0",
    lifespan=lifespan
)

if settings.config.cors.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.config.cors.origins,
        allow_credentials=settings.config.cors.allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"]
    )

app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(context.router)
app.include_router(tools.router)
app.include_router(acp.router)
app.include_router(admin.router)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"全局异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务器错误", "error": str(exc)}
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "CXHMS",
        "version": "1.0.0"
    }


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
