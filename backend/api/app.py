import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.exceptions import (
    cxhms_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from backend.core.exceptions import CXHMSException
from backend.api.middleware.performance import PerformanceMiddleware
from backend.api.response import APIResponse, HealthResponse
from backend.api.routers import (
    acp,
    admin,
    agents,
    anythingllm,
    archive,
    backup,
    chat,
    config as config_router,
    context,
    cxfc as cxfc_router,
    graph as graph_router,
    memory,
    memory_chat,
    service,
    stats as stats_router,
    tools,
    vector as vector_router,
    websocket,
)
from backend.core.logging_config import LogContext, get_contextual_logger, setup_logging
from backend.dependencies import ServiceState, set_service_state
from config.settings import settings

# 配置结构化日志
log_file_config = getattr(settings.config, "logging", {})
log_file = (
    log_file_config.get("file", "logs/app.log")
    if isinstance(log_file_config, dict)
    else "logs/app.log"
)

setup_logging(
    level=settings.config.system.log_level,
    log_file=log_file,
    max_bytes=(
        log_file_config.get("max_bytes", 10 * 1024 * 1024)
        if isinstance(log_file_config, dict)
        else 10 * 1024 * 1024
    ),
    backup_count=log_file_config.get("backup_count", 5) if isinstance(log_file_config, dict) else 5,
    structured=False,  # 可以设置为 True 启用 JSON 格式日志
    console_colors=True,
)

logger = get_contextual_logger(__name__)


async def _build_sim_service_state(app: FastAPI):
    """模拟模式装配：用假实现构造 ServiceState，返回 (service_state, tmpdir)。

    在 ``CXHMS_SIMULATION`` 环境变量被设置时由 lifespan 调用，使用
    ``tests.fakes`` 下的假实现驱动真实业务逻辑，
    不依赖任何外部服务（vLLM/Ollama/Chroma/Milvus 等）。
    """
    import os
    import tempfile

    from backend.core.context.manager import ContextManager
    from backend.core.memory.manager import MemoryManager
    from backend.core.memory.secondary_router import SecondaryModelRouter
    from backend.core.tools import (
        register_assistant_tools,
        register_builtin_tools,
        register_master_tools,
        register_summary_tools,
        set_assistant_dependencies,
        set_master_dependencies,
        set_summary_dependencies,
    )
    from backend.core.tools.graph_tools import set_graph_dependencies
    from backend.dependencies import ServiceState, set_service_state
    from tests.fakes.fake_embedding import FakeEmbeddingModel
    from tests.fakes.fake_graph import make_in_memory_graph_store
    from tests.fakes.fake_llm import FakeLLMClient, FakeModelRouter
    from tests.fakes.fake_vector_store import InMemoryVectorStore

    import backend.dependencies as _deps

    tmpdir = tempfile.mkdtemp(prefix="cxhms_sim_")
    logger.info(f"模拟模式：使用临时目录 {tmpdir}")

    # 1. 用临时文件 db 构造 MemoryManager（每次实例化独立，无需重置单例）
    #    注意：不能用 :memory:，因为 MemoryManager 用每线程 sqlite 连接池，
    #    不同线程会看到不同的内存库。
    memory_manager = MemoryManager(db_path=os.path.join(tmpdir, "memories.db"))
    memory_manager.enable_vector_search(
        embedding_model=FakeEmbeddingModel(),
        vector_store=InMemoryVectorStore(),
    )

    # 1.5 Phase 2: 初始化 DocumentMemoryManager（注入 memory_manager + 临时目录配置）
    document_memory_manager = None
    try:
        from backend.core.document.memory import DocumentMemoryManager

        # 构造临时配置文件指向 tmpdir，避免污染真实 data 目录
        sim_doc_config = {
            "db_path": os.path.join(tmpdir, "documents.db"),
            "max_file_size": 10485760,
            "default_folder": "custom-documents",
        }
        sim_doc_config_path = os.path.join(tmpdir, "doc_config.json")
        import json as _json
        with open(sim_doc_config_path, "w", encoding="utf-8") as _f:
            _json.dump(sim_doc_config, _f)

        document_memory_manager = DocumentMemoryManager(
            memory_manager=memory_manager,
            config_path=sim_doc_config_path,
        )
        logger.info("模拟模式：文档记忆管理器已启动")
    except Exception as e:
        logger.warning(f"模拟模式：文档记忆管理器启动失败: {e}")
        document_memory_manager = None

    # 2. ContextManager：构造后把 _context_dir 指向临时目录，清空内存 _store
    context_manager = ContextManager(db_path=os.path.join(tmpdir, "sessions.db"))
    context_manager._context_dir = os.path.join(tmpdir, "context")
    os.makedirs(context_manager._context_dir, exist_ok=True)
    context_manager._store.clear()

    # 3. FakeLLMClient + FakeModelRouter
    llm_client = FakeLLMClient()
    model_router = FakeModelRouter(client=llm_client)
    await model_router.initialize()

    # 4. SecondaryModelRouter
    secondary_router = SecondaryModelRouter(
        memory_manager,
        llm_client,
        model_router=model_router,
        context_manager=context_manager,
    )

    # 5. acp/mcp/cxfc 模拟模式不需要，设为 None
    acp_manager = None
    mcp_manager = None
    cxfc_manager = None

    # 6. 工具注册（按真实 lifespan 顺序，失败不阻断）
    try:
        register_builtin_tools()
        logger.info("模拟模式：内置工具已注册")
    except Exception as e:
        logger.warning(f"模拟模式：内置工具注册失败: {e}")

    try:
        set_master_dependencies(
            memory_manager=memory_manager,
            secondary_router=secondary_router,
            context_manager=context_manager,
            acp_manager=acp_manager,
        )
        register_master_tools()
        logger.info("模拟模式：主模型工具已注册")
    except Exception as e:
        logger.warning(f"模拟模式：主模型工具注册失败: {e}")

    try:
        set_summary_dependencies(
            memory_manager=memory_manager,
            model_router=model_router,
            context_manager=context_manager,
        )
        register_summary_tools()
        logger.info("模拟模式：摘要模型工具已注册")
    except Exception as e:
        logger.warning(f"模拟模式：摘要模型工具注册失败: {e}")

    try:
        set_assistant_dependencies(
            memory_manager=memory_manager,
            secondary_router=secondary_router,
            context_manager=context_manager,
        )
        register_assistant_tools()
        logger.info("模拟模式：记忆管理模型工具已注册")
    except Exception as e:
        logger.warning(f"模拟模式：记忆管理模型工具注册失败: {e}")

    # 7. 图存储：注入假实现到 dependencies 注册表与 graph_tools 注册表
    try:
        gdb, gs = make_in_memory_graph_store("default")
        set_graph_dependencies(gs, agent_id="default")
        _deps._graph_databases["default"] = gdb
        _deps._graph_stores["default"] = gs
        logger.info("模拟模式：图存储已注入")
    except Exception as e:
        logger.warning(f"模拟模式：图存储注入失败: {e}")

    # 8. 构造 ServiceState
    service_state = ServiceState()
    service_state.memory_manager = memory_manager
    service_state.async_memory_manager = None  # 模拟模式不启用异步记忆管理器
    service_state.context_manager = context_manager
    service_state.acp_manager = acp_manager
    service_state.llm_client = llm_client
    service_state.secondary_router = secondary_router
    service_state.mcp_manager = mcp_manager
    service_state.model_router = model_router
    service_state.cxfc_manager = cxfc_manager
    service_state.document_memory_manager = document_memory_manager

    return service_state, tmpdir


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os as _os

    # 模拟模式分支：用假实现装配，跳过所有真实外部连接
    if _os.environ.get("CXHMS_SIMULATION"):
        service_state, _sim_tmpdir = await _build_sim_service_state(app)
        app.state.services = service_state
        set_service_state(service_state)
        app.state._sim_tmpdir = _sim_tmpdir
        # 模拟模式跳过 ReinitManager 和 ConfigWatcher（无真实配置文件监听需求）。
        # 显式置 None，让 API 端点 _get_reinit_manager 返回 None（503），
        # 避免依赖 getattr 的默认值语义。
        app.state.reinit_manager = None
        app.state.config_watcher = None
        # cxfc_router 需要显式置空，避免引用上一次启动的 manager
        try:
            cxfc_router.set_cxfc_manager(None)
        except Exception:
            pass
        logger.info("CXHMS 模拟模式已启动")

        yield

        # shutdown：清理模拟资源
        logger.info("正在关闭CXHMS模拟服务...")
        try:
            if service_state.memory_manager:
                service_state.memory_manager.shutdown()
        except Exception:
            pass
        # Phase 2: 关闭文档记忆管理器
        try:
            if service_state.document_memory_manager:
                service_state.document_memory_manager.close()
        except Exception:
            pass
        # T11: 关闭 ContextManager 后台 flush 线程，避免 lifespan 退出时 daemon 线程被强杀
        try:
            if service_state.context_manager:
                service_state.context_manager.shutdown()
        except Exception:
            pass
        try:
            import backend.dependencies as _sim_deps

            for _aid, _gdb in list(_sim_deps._graph_databases.items()):
                try:
                    _gdb.close()
                except Exception:
                    pass
            _sim_deps._graph_databases.clear()
            _sim_deps._graph_stores.clear()
        except Exception:
            pass
        try:
            if service_state.model_router:
                await service_state.model_router.close()
        except Exception:
            pass
        try:
            import shutil

            shutil.rmtree(_sim_tmpdir, ignore_errors=True)
        except Exception:
            pass
        logger.info("CXHMS模拟服务已关闭")
        return

    from backend.core.acp.manager import ACPManager
    from backend.core.context.manager import ContextManager
    from backend.core.llm.client import LLMFactory
    from backend.core.memory.manager import MemoryManager
    from backend.core.memory.secondary_router import SecondaryModelRouter
    from backend.core.model_router import model_router as mr  # 导入模型路由器
    from backend.core.tools.mcp import MCPManager
    from backend.core.tools.registry import tool_registry

    import backend.dependencies as _deps

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

    # Phase 2: 初始化文档记忆管理器（依赖 memory_manager 实例 + 配置契约）
    document_memory_manager = None
    try:
        if memory_manager:
            from backend.core.document.memory import DocumentMemoryManager

            document_memory_manager = DocumentMemoryManager(
                memory_manager=memory_manager,
                config_path=None,  # 默认加载 public/config_template/anythingllm_document_config.json
            )
            logger.info("文档记忆管理器已启动")
    except Exception as e:
        logger.warning(f"文档记忆管理器启动失败: {e}")
        document_memory_manager = None

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
            agent_id=settings.config.acp.agent_id, agent_name=settings.config.acp.agent_name
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
                max_tokens=settings.config.llm.max_tokens,
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
                context_manager=context_manager,
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
        from backend.core.tools import register_master_tools, set_master_dependencies

        set_master_dependencies(
            memory_manager=memory_manager,
            secondary_router=secondary_router,
            context_manager=context_manager,
            acp_manager=acp_manager,
        )
        register_master_tools()
        master_tools_registered = True
        logger.info("主模型工具已注册")
    except Exception as e:
        logger.warning(f"主模型工具注册失败: {e}")

    # 注册摘要模型工具
    summary_tools_registered = False
    try:
        from backend.core.tools import register_summary_tools, set_summary_dependencies

        set_summary_dependencies(
            memory_manager=memory_manager,
            model_router=model_router,
            context_manager=context_manager,
        )
        register_summary_tools()
        summary_tools_registered = True
        logger.info("摘要模型工具已注册")
    except Exception as e:
        logger.warning(f"摘要模型工具注册失败: {e}")

    # 注册记忆管理模型工具
    assistant_tools_registered = False
    try:
        from backend.core.tools import register_assistant_tools, set_assistant_dependencies

        set_assistant_dependencies(
            memory_manager=memory_manager,
            secondary_router=secondary_router,
            context_manager=context_manager,
        )
        register_assistant_tools()
        assistant_tools_registered = True
        logger.info("记忆管理模型工具已注册")
    except Exception as e:
        logger.warning(f"记忆管理模型工具注册失败: {e}")

    # 注册任务辅助工具（任务清单 + 定时提醒）
    try:
        from backend.core.tools.task_tools import (
            register_task_tools,
            set_task_tools_dependencies,
        )
        from backend.core.tasks import get_task_manager
        from backend.core.alarm import get_alarm_manager

        set_task_tools_dependencies(
            task_manager=get_task_manager(),
            alarm_manager=get_alarm_manager(),
        )
        register_task_tools()
        logger.info("任务辅助工具已注册")
    except Exception as e:
        logger.warning(f"任务辅助工具注册失败: {e}")

    # 注册记忆系统工具（save_memory 等）
    try:
        from backend.core.tools.memory_tools import (
            register_memory_tools,
            set_memory_tools_dependencies,
        )

        set_memory_tools_dependencies(memory_manager=memory_manager)
        register_memory_tools()
        logger.info("记忆系统工具已注册")
    except Exception as e:
        logger.warning(f"记忆系统工具注册失败: {e}")

    # 验证工具注册状态
    from backend.core.tools import tool_registry

    tools_stats = tool_registry.get_tool_stats()
    logger.info(
        f"工具注册统计: 总计{tools_stats['total_tools']}个, "
        f"启用{tools_stats['enabled_tools']}个, "
        f"禁用{tools_stats['disabled_tools']}个"
    )

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
                    vector_size=settings.config.memory.chroma.vector_size,
                )
            elif vector_backend == "milvus_lite":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="milvus_lite",
                    db_path=settings.config.memory.milvus_lite.db_path,
                    vector_size=settings.config.memory.milvus_lite.vector_size,
                )
            elif vector_backend == "qdrant":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="qdrant",
                    host=settings.config.memory.qdrant.host,
                    port=settings.config.memory.qdrant.port,
                    vector_size=settings.config.memory.qdrant.vector_size,
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
                    schema_class=settings.config.memory.weaviate.schema_class,
                )
            elif vector_backend == "weaviate_embedded":
                memory_manager.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="weaviate_embedded",
                    embedded=True,
                    vector_size=settings.config.memory.weaviate.vector_size,
                    schema_class=settings.config.memory.weaviate.schema_class,
                )
            logger.info(f"向量搜索已启用: {vector_backend}")

            if memory_manager.is_vector_search_enabled():
                try:
                    sync_result = await memory_manager._vector_store.sync_with_sqlite(
                        memory_manager, last_sync_time=memory_manager._last_sync_time
                    )
                    memory_manager._last_sync_time = datetime.now().isoformat()
                    logger.info(
                        f"启动时向量同步完成: checked={sync_result.total_checked}, synced={sync_result.synced}, errors={sync_result.errors}"
                    )
                except Exception as e:
                    logger.warning(f"启动时向量同步失败: {e}")
    except Exception as e:
        logger.warning(f"向量搜索启动失败: {e}")

    try:
        from backend.core.alarm import get_alarm_manager
        from backend.core.websocket.handlers import push_alarm_to_agent
        from backend.core.websocket.manager import get_websocket_manager

        alarm_manager = get_alarm_manager()
        main_loop = asyncio.get_running_loop()

        def on_alarm_trigger(agent_id: str, message: str):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    push_alarm_to_agent(agent_id, message), main_loop
                )
                future.result(timeout=5)
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"推送提醒失败: {e}")

        alarm_manager.set_trigger_callback(on_alarm_trigger)
        alarm_manager.restore_pending_alarms()
        logger.info("提醒管理器已启动")

        async def on_offline(agent_id: str):
            """离线时保存上下文到长期记忆，并清理旧消息"""
            try:
                session_id = f"agent-{agent_id}"
                cm = app.state.services.context_manager
                if cm is None:
                    return

                all_messages = cm.get_messages(session_id, limit=1000)

                if not all_messages or len(all_messages) <= 10:
                    return

                # 仅归档尚未摘要的消息：通过 get_summarizable_range 获取已摘要起点
                # （优先识别 diary_summary 标记，回退到 session.summarized_up_to）
                rng = cm.get_summarizable_range(session_id)
                start_idx = rng.get("start", 0)
                total_active = rng.get("total", 0)
                # get_messages 返回最后 limit 条；当活跃消息超过 limit 时需对齐索引
                fetched_count = len(all_messages)
                if total_active > fetched_count:
                    start_idx = max(0, start_idx - (total_active - fetched_count))

                # 保留最后 10 条作为近期上下文
                keep_recent = 10
                if start_idx >= len(all_messages) - keep_recent:
                    return  # 没有新的可归档消息

                candidates = all_messages[start_idx : len(all_messages) - keep_recent]

                # 仅归档 user/assistant 角色消息，跳过 diary_summary 标记（避免重复摘要）
                messages_to_archive = []
                for msg in candidates:
                    if msg.get("content_type") == "diary_summary":
                        continue
                    meta = msg.get("metadata") or {}
                    if meta.get("is_diary_summary"):
                        continue
                    if msg.get("role") not in ("user", "assistant"):
                        continue
                    messages_to_archive.append(msg)

                if not messages_to_archive:
                    return

                context_text = "\n".join(
                    [
                        f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
                        for msg in messages_to_archive
                    ]
                )

                summary_content = f"[离线自动保存] Agent {agent_id} 的对话上下文摘要:\n\n"
                if len(context_text) > 1000:
                    summary_content += context_text[:1000] + "..."
                else:
                    summary_content += context_text

                mm = get_memory_manager()
                if mm:
                    mm.write_memory(
                        content=summary_content,
                        memory_type="long_term",
                        importance=2,
                        tags=["offline_save", "context", agent_id],
                    )

                # 仅删除真正归档的 user/assistant 消息，保留 diary_summary 标记
                for msg in messages_to_archive:
                    cm.delete_message(msg.get("id"))

                logger.info(
                    f"离线保存上下文成功: agent={agent_id}, 归档 {len(messages_to_archive)} 条消息"
                )
            except Exception as e:
                logger.error(f"离线保存上下文失败: {e}")

        ws_manager = get_websocket_manager()
        ws_manager.set_offline_callback(on_offline)
        await ws_manager.start_cleanup_task(interval_seconds=30)
        logger.info("WebSocket 离线保存已启用")
    except Exception as e:
        logger.warning(f"提醒管理器启动失败: {e}")

    # Initialize AsyncMemoryManager
    async_memory_manager = None
    try:
        from backend.core.memory.async_manager import AsyncMemoryManager
        async_memory_manager = AsyncMemoryManager(db_path=db_config.memories_db)
        # B1: 必须显式 initialize()，否则 _pool 永远为 None，get_async_memory_manager() 后任何调用都会抛 AttributeError
        await async_memory_manager.initialize()
        logger.info("异步记忆管理器已启动")
    except Exception as e:
        logger.warning(f"异步记忆管理器启动失败: {e}")
        async_memory_manager = None

    # 图数据库改为按助手按需创建，启动时不再全局初始化

    # Initialize CXFCManager
    cxfc_manager = None
    try:
        if getattr(settings.config, 'cxfc', None) and settings.config.cxfc.enabled:
            from backend.core.cxfc.manager import CXFCManager
            cxfc_manager = CXFCManager()
            await cxfc_manager.start()
            logger.info("CXFC管理器已启动")
    except Exception as e:
        logger.warning(f"CXFC管理器启动失败: {e}")

    # 启动自动日记摘要任务
    try:
        if context_manager and model_router:
            from backend.core.session.auto_summary import start_auto_summary
            await start_auto_summary(
                context_manager=context_manager,
                model_router=model_router,
                check_interval_minutes=10,
                summary_threshold=20,
            )
    except Exception as e:
        logger.warning(f"自动摘要任务启动失败: {e}")

    # 将CXFC管理器注入到cxfc路由器
    cxfc_router.set_cxfc_manager(cxfc_manager)

    # Register graph tools (图数据库实例按需创建，工具调用时解析)
    try:
        from backend.core.tools.graph_tools import register_graph_tools
        register_graph_tools()
        logger.info("图数据库工具已注册")
    except Exception as e:
        logger.warning(f"图数据库工具注册失败: {e}")

    # Set up ServiceState for dependency injection
    service_state = ServiceState()
    service_state.memory_manager = memory_manager
    service_state.async_memory_manager = async_memory_manager
    service_state.context_manager = context_manager
    service_state.acp_manager = acp_manager
    service_state.llm_client = llm_client
    service_state.secondary_router = secondary_router
    service_state.mcp_manager = mcp_manager
    service_state.model_router = model_router
    service_state.cxfc_manager = cxfc_manager
    service_state.document_memory_manager = document_memory_manager
    app.state.services = service_state
    set_service_state(service_state)

    # 初始化 DistillationService（RADIX-Lite v1.3.0：合并到后端 8001）
    # rules-0 §三 try-except fallback：实例化失败不阻断主服务，distillation 端点返回 503
    try:
        from modules.模块9_蒸馏服务.distillation_service import DistillationService

        distillation_service = DistillationService()
        app.state.distillation_service = distillation_service
        logger.info("DistillationService 已合并到后端（/api/v1/distillation/*）")
    except Exception as e:
        logger.warning(f"DistillationService 初始化失败（蒸馏端点将返回 503）: {e}")
        app.state.distillation_service = None

    # vLLM 预热：触发模型加载与 kernel 编译，消除首请求冷启动延迟
    try:
        if llm_client and hasattr(llm_client, "warmup"):
            logger.info("开始 vLLM 预热...")
            await llm_client.warmup(timeout=120.0)
    except Exception as e:
        logger.warning(f"vLLM 预热异常（不阻断启动）: {e}")

    # 初始化 ReinitManager 和 ConfigWatcher（配置热重载与组件重初始化）
    # 任一启动失败均不阻断主服务：reinit 仍可通过 API 手动触发（watcher 不可用时）
    reinit_manager = None
    try:
        from backend.core.config.reinit import ReinitManager

        reinit_manager = ReinitManager(service_state, settings)
        app.state.reinit_manager = reinit_manager
        logger.info("ReinitManager 已启动")
    except Exception as e:
        logger.warning(f"ReinitManager 启动失败: {e}")

    try:
        from backend.core.config.watcher import ConfigWatcher

        # 捕获主事件循环，供 watchdog 线程提交协程到主循环
        # （参考本文件 alarm_manager 的 main_loop 模式）
        main_loop = asyncio.get_running_loop()

        def _on_config_changed():
            """ConfigWatcher 回调：在 watchdog 线程中触发 async reinit。

            通过 run_coroutine_threadsafe 将协程提交到主事件循环，
            避免 watchdog 线程直接驱动 asyncio。
            """
            if reinit_manager is None:
                return
            try:
                asyncio.run_coroutine_threadsafe(
                    reinit_manager.reinit(reload_first=True),
                    main_loop,
                )
            except RuntimeError:
                # main_loop 可能已在 shutdown 中关闭，忽略
                pass

        config_watcher = ConfigWatcher(
            config_path="config/default.yaml",
            callback=_on_config_changed,
        )
        config_watcher.start()
        app.state.config_watcher = config_watcher
    except Exception as e:
        logger.warning(f"ConfigWatcher 启动失败: {e}")

    yield

    logger.info("正在关闭CXHMS服务...")

    # 停止 ConfigWatcher（最先停止，避免 shutdown 期间仍触发 reinit）
    try:
        config_watcher = getattr(app.state, "config_watcher", None)
        if config_watcher:
            config_watcher.stop()
    except Exception as e:
        logger.warning(f"ConfigWatcher 停止失败: {e}")

    # 停止自动摘要任务
    try:
        from backend.core.session.auto_summary import stop_auto_summary
        await stop_auto_summary()
    except Exception:
        pass

    # Shutdown CXFC manager
    if cxfc_manager:
        try:
            await cxfc_manager.shutdown()
        except Exception:
            pass

    # Close all per-agent graph databases
    try:
        from backend.dependencies import _graph_databases
        for _aid, _gdb in list(_graph_databases.items()):
            try:
                _gdb.close()
            except Exception:
                pass
        _graph_databases.clear()
    except Exception:
        pass

    try:
        from backend.core.alarm import get_alarm_manager

        alarm_mgr = get_alarm_manager()
        alarm_mgr.shutdown()
    except Exception:
        pass

    try:
        from backend.core.websocket.manager import get_websocket_manager

        ws_mgr = get_websocket_manager()
        await ws_mgr.stop_cleanup_task()
    except Exception:
        pass

    if acp_manager:
        await acp_manager.stop()

    if memory_manager:
        memory_manager.shutdown()

    # Phase 2: 关闭文档记忆管理器（需在 memory_manager.shutdown() 之后，
    # 因为 DocumentMemoryManager 持有 memory_manager 引用但 close() 只关闭自身 SQLite 连接）
    if document_memory_manager:
        try:
            document_memory_manager.close()
        except Exception:
            pass

    # T11: 关闭 ContextManager 后台 flush 线程，避免 lifespan 退出时 daemon 线程被强杀
    if context_manager:
        try:
            context_manager.shutdown()
        except Exception:
            pass

    # B1: 关闭异步记忆管理器连接池
    if async_memory_manager:
        try:
            await async_memory_manager.close()
        except Exception:
            pass

    # 关闭备份管理器
    try:
        from backend.core.backup.manager import get_backup_manager

        backup_mgr = get_backup_manager()
        backup_mgr.shutdown()
    except Exception:
        pass

    # 关闭插件管理器
    try:
        from backend.core.plugins.manager import get_plugin_manager

        plugin_mgr = get_plugin_manager()
        await plugin_mgr.shutdown()
    except Exception:
        pass

    # 关闭模型路由器
    if model_router:
        await model_router.close()

    logger.info("CXHMS服务已关闭")


app = FastAPI(
    title="CXHMS - CX-O History & Memory Service",
    description="AI代理中间层服务，提供记忆管理、工具调用、ACP互联等功能",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(PerformanceMiddleware)

if getattr(settings.config, "cors", None) and settings.config.cors.enabled:
    cors_origins = settings.config.cors.origins
    # CORS 规范禁止 origins=["*"] 与 allow_credentials=True 同时使用
    allow_creds = cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
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
app.include_router(memory_chat.router, prefix="/api")
app.include_router(stats_router.router, prefix="/api")
app.include_router(config_router.router, prefix="/api")
app.include_router(vector_router.router, prefix="/api")
app.include_router(graph_router.router, prefix="/api")
app.include_router(cxfc_router.router, prefix="/api")
app.include_router(anythingllm.router, prefix="/api")

# RADIX-Lite v1.3.0：DistillationService 路由静态注册（实例在 lifespan 中初始化）
try:
    from modules.模块9_蒸馏服务.api.routes import router as distillation_router
    from modules.模块9_蒸馏服务.api.batch_routes import router as distillation_batch_router

    app.include_router(distillation_router)
    app.include_router(distillation_batch_router)
except Exception as e:
    import logging as _logging
    _logging.getLogger(__name__).warning(f"DistillationService 路由注册失败: {e}")


@app.get("/acp/health")
async def acp_health_root():
    """ACP 协议根级健康检查端点。

    供外部 ACP Agent 通过 GET /acp/health 验证主系统是否在线。
    """
    from backend.dependencies import get_acp_manager

    acp_mgr = get_acp_manager()
    if not acp_mgr:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "error": "ACP 管理器不可用"},
        )

    return {
        "status": "ok",
        "agent_id": acp_mgr._local_agent_id,
        "agent_name": acp_mgr._local_agent_name,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/acp/info")
async def acp_info_root():
    """ACP 协议根级节点信息端点。

    返回主系统 Agent 的基本信息（id/name/host/port/capabilities/version）。
    """
    from backend.dependencies import get_acp_manager

    acp_mgr = get_acp_manager()
    if not acp_mgr:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "error": "ACP 管理器不可用"},
        )

    return {
        "agent_id": acp_mgr._local_agent_id,
        "agent_name": acp_mgr._local_agent_name,
        "host": "0.0.0.0",
        "port": acp_mgr.local_http_port,
        "capabilities": ["chat", "tools"],
        "version": "1.0.0",
    }


@app.post("/acp/message")
async def acp_message_root(request: Request):
    """标准 ACP 协议端点：接收其他 ACP Agent 通过 HTTP 投递的消息。

    独立 ACP 节点（如测试工具）的 send_message 方法投递到此路径，
    而非 /api/acp/receive。此端点将消息注入主系统 Agent 的聊天上下文。
    """
    from backend.dependencies import get_acp_manager
    from backend.core.acp.manager import ACPMessageInfo, ACPAgentInfo
    import uuid

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "error": "无效的 JSON"})

    acp_mgr = get_acp_manager()
    if not acp_mgr:
        return JSONResponse(status_code=503, content={"status": "error", "error": "ACP 管理器不可用"})

    try:
        msg_id = payload.get("id") or str(uuid.uuid4())
        message = ACPMessageInfo(
            id=msg_id,
            msg_type=payload.get("msg_type", payload.get("type", "chat")),
            from_agent_id=payload.get("from_agent_id", ""),
            from_agent_name=payload.get("from_agent_name", ""),
            to_agent_id=payload.get("to_agent_id"),
            to_group_id=payload.get("to_group_id"),
            content=payload.get("content", {}),
            timestamp=payload.get("timestamp") or datetime.now().isoformat(),
            is_read=False,
            is_sent=False,
        )
        await acp_mgr.receive_external_message(message)

        # 注册/更新发送方 Agent 信息
        from_agent_id = payload.get("from_agent_id", "")
        metadata = payload.get("metadata") or {}
        ext_host = str(metadata.get("from_host", "") or request.client.host if request.client else "")
        ext_port = int(metadata.get("from_port", 0) or 0)

        if from_agent_id and from_agent_id not in acp_mgr.agents:
            external_agent = ACPAgentInfo(
                id=from_agent_id,
                name=payload.get("from_agent_name") or "External Agent",
                host=ext_host,
                port=ext_port,
                status="online",
                version="1.0.0",
                capabilities=["chat"],
                last_seen=datetime.now().isoformat(),
                metadata={"source": "acp_message"},
            )
            await acp_mgr.register_agent(external_agent)
        elif from_agent_id and (ext_host or ext_port):
            existing = acp_mgr.agents.get(from_agent_id)
            if existing:
                if ext_host and existing.host != ext_host:
                    existing.host = ext_host
                if ext_port and existing.port != ext_port:
                    existing.port = ext_port
                existing.last_seen = datetime.now()

        return {"status": "ok", "message_id": msg_id, "message": "消息已接收"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": f"内部错误: {e}"})


@app.post("/acp/receive")
async def acp_receive_root(request: Request):
    """兼容端点：与 /acp/message 行为一致。"""
    return await acp_message_root(request)

# B3: 单一 handler 覆盖所有 CXHMSException 子类（core 层与 api 层共享基类）
app.add_exception_handler(CXHMSException, cxhms_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    services = getattr(app.state, "services", None)

    def _ok(attr: str) -> bool:
        return services is not None and getattr(services, attr, None) is not None

    components = {
        "memory_manager": _ok("memory_manager"),
        "context_manager": _ok("context_manager"),
        "acp_manager": _ok("acp_manager"),
        "llm_client": _ok("llm_client"),
        "model_router": _ok("model_router"),
        "async_memory_manager": _ok("async_memory_manager"),
        "graph_database": _ok("memory_manager"),  # 图数据库依赖 memory_manager，按需创建
        "cxfc_manager": _ok("cxfc_manager"),
    }
    return HealthResponse(
        status="healthy" if all(components.values()) else "degraded",
        version="1.0.0",
        components=components,
    )


@app.get("/")
async def root():
    return {
        "service": "CXHMS",
        "version": "1.0.0",
        "description": "CX-O History & Memory Service",
        "docs": "/docs",
        "redoc": "/redoc",
    }


# 依赖注入函数（get_memory_manager / get_context_manager / get_acp_manager /
# get_llm_client / get_secondary_router / get_mcp_manager / get_model_router）
# 已统一至 backend.dependencies，通过 ServiceState + FastAPI Depends 提供。
# 路由层应使用 ``from backend.dependencies import get_xxx`` 注入依赖；
# 直接调用时由 ``_resolve_state`` 回退到 ``_service_state`` 全局。
