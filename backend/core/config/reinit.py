"""组件重新初始化管理器。

提供 ReinitResult dataclass 与 ReinitManager 类，用于在配置热重载后
按依赖顺序对受影响的组件执行增量重新初始化。

设计要点：
    - decide_components 是纯同步逻辑：根据 ConfigDiff 决定哪些组件需要 reinit
    - reinit / reinit_component 是 async：因为各组件 initialize/start 是协程
    - 组件替换通过 ServiceState.update_component 原子完成（线程安全）
    - 旧实例的安全关闭由 ServiceState._safe_close 在锁外执行；async close
      由本模块在事件循环中显式 await 关闭

依赖顺序（REINIT_ORDER）：
    model_router → llm_client → memory_manager → context_manager
    → secondary_router → acp_manager → cxfc_manager

特殊规则：
    - database 段变化 → 跳过（需进程重启）
    - PURE_PARAM_FIELDS 中的字段变化 → 仅刷新内存参数，不触发 reinit
    - memory 段只有 PURE_PARAM_FIELDS 中的字段 → 不触发 memory_manager reinit
"""

import asyncio
import inspect
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from backend.core.config.diff import ConfigDiff

logger = logging.getLogger(__name__)


@dataclass
class ReinitResult:
    """重初始化结果。

    Attributes:
        affected: 成功重初始化的组件名列表。
        failed: 失败的组件名列表。
        success: 是否全部成功（无失败）。
        skipped: 是否跳过（如纯阈值变化或 database 段变化）。
        errors: 失败原因映射 {component: error_msg}。
        warnings: 警告信息列表（如 ACP/CXFC 连接中断）。
        started_at: 开始时间 ISO 字符串。
        finished_at: 结束时间 ISO 字符串。
    """

    affected: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    success: bool = True
    skipped: bool = False
    errors: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    @property
    def partial(self) -> bool:
        """是否部分失败（存在 failed 项）。"""
        return bool(self.failed)


class ReinitManager:
    """组件重新初始化管理器。

    根据 ConfigDiff 决定哪些组件需要重新初始化，按依赖顺序逐个替换实例。
    """

    # 可重初始化的组件（按依赖顺序）
    REINIT_ORDER: List[str] = [
        "model_router",
        "llm_client",
        "memory_manager",  # 含 vector_store
        "context_manager",
        "secondary_router",
        "acp_manager",
        "cxfc_manager",
    ]

    # diff 段 → 组件映射
    SECTION_TO_COMPONENTS: Dict[str, Set[str]] = {
        "models": {"model_router", "llm_client"},
        "llm": {"model_router", "llm_client"},
        "memory": {"memory_manager"},  # 需进一步判断是否纯阈值
        "vector": {"memory_manager"},
        "context": {"context_manager"},
        "acp": {"acp_manager"},
        "cxfc": {"cxfc_manager"},
        # database/graph/system/cors/rate_limit 不触发 reinit
    }

    # 纯参数字段（不触发 reinit，仅刷新内存）
    PURE_PARAM_FIELDS: Set[str] = {
        "memory.dedup_threshold",
        "memory.archive_enabled",
        "memory.archive_compression_enabled",
        "memory.decay_enabled",
        "memory.batch_interval",
        "memory.permanent_threshold",
        "memory.max_short_term_age_days",
        "memory.max_long_term_age_days",
        "context.max_messages",
        "context.summary_threshold",
        "context.window_size",
        "context.enable_summary",
        "context.max_summaries_in_context",
    }

    def __init__(self, service_state: Any, settings: Any) -> None:
        """
        Args:
            service_state: ServiceState 实例，用于 update_component 替换组件。
            settings: Settings 实例，用于读取 config 配置（如 db_path、acp 配置等）。
        """
        self._service_state = service_state
        self._settings = settings
        self._lock = threading.Lock()
        # 重入标志（M8-a）：reinit 进行中为 True，读写由 _lock 保护，
        # 兼容 watcher 线程与 API 事件循环的跨线程并发场景
        self._reinit_in_progress: bool = False
        # 兼容保留：service.py 路由层会写入此属性跟踪后台任务；
        # get_status 已改由 _reinit_in_progress 驱动，不再读取它
        self._current_task: Optional[asyncio.Task] = None
        self._current_component: Optional[str] = None
        self._last_result: Optional[ReinitResult] = None
        self._last_at: Optional[str] = None
        # 决策阶段临时存储 skipped 原因（database 段变化时设置）
        self._skip_reason: Optional[str] = None

    # ------------------------------------------------------------------ #
    # 决策：根据 diff 计算需要 reinit 的组件集合（纯同步逻辑）
    # ------------------------------------------------------------------ #

    def decide_components(self, diff: ConfigDiff) -> Set[str]:
        """根据 ConfigDiff 决定需要 reinit 的组件集合。

        逻辑：
            1. diff 为空 → 返回空集合
            2. changed_sections 含 database → 返回空集合，设置 skipped=True，
               记录 errors={"database": "requires process restart"}
            3. 所有 field_changes 都属于 PURE_PARAM_FIELDS → 返回空集合，
               设置 skipped=True
            4. memory 段变化但只有 PURE_PARAM_FIELDS 中的字段 → 不触发
               memory_manager reinit
            5. 其余段按 SECTION_TO_COMPONENTS 映射累加组件

        Args:
            diff: 配置差异描述。

        Returns:
            需要重新初始化的组件名集合。
        """
        self._skip_reason = None

        # 1. 空 diff
        if diff.is_empty():
            return set()

        # 2. database 段变化 → 跳过
        if "database" in diff.changed_sections:
            self._skip_reason = "database"
            return set()

        # 3. 纯参数变化 → 跳过
        if diff.field_changes and all(
            fc in self.PURE_PARAM_FIELDS for fc in diff.field_changes
        ):
            self._skip_reason = "pure_param"
            return set()

        # 4. 按段映射累加组件
        components: Set[str] = set()
        for section in diff.changed_sections:
            mapped = self.SECTION_TO_COMPONENTS.get(section)
            if mapped is None:
                continue
            # 特殊处理 memory 段：仅纯参数时不触发 memory_manager reinit
            if section == "memory":
                memory_fields = [
                    fc for fc in diff.field_changes if fc.startswith("memory.")
                ]
                if memory_fields and all(
                    fc in self.PURE_PARAM_FIELDS for fc in memory_fields
                ):
                    # memory 段只有纯参数 → 跳过 memory_manager
                    continue
                # memory 段同时含 vector_backend/weaviate 等子字段 → 需 reinit
                components |= mapped
            else:
                components |= mapped

        return components

    # ------------------------------------------------------------------ #
    # 执行：reinit 主流程（async）
    # ------------------------------------------------------------------ #

    async def reinit(
        self,
        components: Optional[Set[str]] = None,
        diff: Optional[ConfigDiff] = None,
        reload_first: bool = False,
    ) -> ReinitResult:
        """对指定组件集合执行重新初始化（带重入保护）。

        重入语义（M8-a）：检测到上一次 reinit 仍在进行中时，拒绝并发请求
        （记录 warning 并返回 success=False 的 ReinitResult），不等待、不排队。
        标志读写由 threading.Lock 保护，兼容 watcher 线程与 API 事件循环的
        跨线程并发场景。

        Args:
            components: 显式指定的组件集合（优先）。
            diff: 配置差异，用于自动决策组件集合。
            reload_first: 是否先 reload 配置文件再决策。仅当 diff 为 None 时生效，
                调用 settings.reload_config_with_diff() 获取新 diff。默认 False，
                保持向后兼容。

        Returns:
            ReinitResult: 本次重初始化的结果；并发重入被拒绝时 success=False，
            errors["reinit"] 说明原因。
        """
        started_at = datetime.now().isoformat()

        # 重入保护：进行中则拒绝并发 reinit（拒绝比等待更安全，避免排队风暴）
        with self._lock:
            if self._reinit_in_progress:
                logger.warning(
                    "拒绝并发 reinit：上一次重初始化仍在进行中（started at %s）",
                    self._last_at or "unknown",
                )
                rejected = ReinitResult(started_at=started_at, success=False)
                rejected.errors["reinit"] = "another reinit is in progress"
                rejected.finished_at = started_at
                return rejected
            self._reinit_in_progress = True

        try:
            return await self._do_reinit(
                components=components, diff=diff, reload_first=reload_first
            )
        finally:
            with self._lock:
                self._reinit_in_progress = False
                self._current_component = None

    async def _do_reinit(
        self,
        components: Optional[Set[str]] = None,
        diff: Optional[ConfigDiff] = None,
        reload_first: bool = False,
    ) -> ReinitResult:
        """reinit 主流程（由 reinit 在重入保护内调用）。

        逻辑：
            1. 若 reload_first=True 且 diff 为 None → 先 reload 配置获取 diff
            2. 若 components 为 None 且 diff 不为 None → 调用 decide_components
            3. 若 components 为 None 且 diff 为 None → 全量 REINIT_ORDER
            4. 按依赖顺序排序组件
            5. 逐个 reinit：成功加 affected，失败加 failed + errors
            6. 更新 _last_result 和 _last_at

        Args:
            components: 显式指定的组件集合（优先）。
            diff: 配置差异，用于自动决策组件集合。
            reload_first: 是否先 reload 配置文件再决策。仅当 diff 为 None 时生效，
                调用 settings.reload_config_with_diff() 获取新 diff。默认 False，
                保持向后兼容。

        Returns:
            ReinitResult: 本次重初始化的结果。
        """
        result = ReinitResult(started_at=datetime.now().isoformat())

        # reload_first：先 reload 配置获取 diff（用于 ConfigWatcher 触发场景）
        if reload_first and diff is None:
            from config.settings import settings

            diff = settings.reload_config_with_diff()

        # 决策组件集合
        if components is None:
            if diff is not None:
                components = self.decide_components(diff)
                # database 段变化 → skipped
                if self._skip_reason == "database":
                    result.skipped = True
                    result.errors["database"] = "requires process restart"
                    result.success = False
                    result.finished_at = datetime.now().isoformat()
                    with self._lock:
                        self._last_result = result
                        self._last_at = result.finished_at
                    return result
                # 纯参数变化 → skipped（success 保持 True）
                if self._skip_reason == "pure_param":
                    result.skipped = True
                    result.finished_at = datetime.now().isoformat()
                    with self._lock:
                        self._last_result = result
                        self._last_at = result.finished_at
                    return result
            else:
                components = set(self.REINIT_ORDER)

        # 空集合 → 直接返回（skipped=True）
        if not components:
            result.skipped = True
            result.finished_at = datetime.now().isoformat()
            with self._lock:
                self._last_result = result
                self._last_at = result.finished_at
            return result

        # 按依赖顺序排序
        ordered = [c for c in self.REINIT_ORDER if c in components]
        # 兜底：未在 REINIT_ORDER 中的组件追加到末尾
        extras = [c for c in components if c not in self.REINIT_ORDER]
        ordered.extend(extras)

        # 逐个 reinit
        for name in ordered:
            with self._lock:
                self._current_component = name
            try:
                await self.reinit_component(name)
                result.affected.append(name)
                logger.info(f"组件 [{name}] 重初始化成功")
            except Exception as e:
                result.failed.append(name)
                result.errors[name] = f"{type(e).__name__}: {e}"
                result.success = False
                logger.warning(f"组件 [{name}] 重初始化失败: {e}")
                # 单点失败不阻断后续组件（隔离）

        result.finished_at = datetime.now().isoformat()

        with self._lock:
            self._last_result = result
            self._last_at = result.finished_at
            self._current_component = None

        return result

    # ------------------------------------------------------------------ #
    # 执行：单组件 reinit（async，可能抛异常）
    # ------------------------------------------------------------------ #

    async def reinit_component(self, name: str) -> None:
        """重新初始化单个组件。

        步骤：
            1. 从 ServiceState 获取旧实例
            2. 按组件类型创建新实例（参考 backend/api/app.py lifespan）
            3. 调用 ServiceState.update_component 原子替换并返回旧实例
            4. 异步关闭旧实例（若有 async close/shutdown）

        Args:
            name: 组件名（必须在 REINIT_ORDER 中或为已知组件）。

        Raises:
            ValueError: 未知组件名。
            Exception: 组件创建/初始化过程中的异常。
        """
        # 局部 import：避免顶层循环导入
        # （model_router 模块导入 settings，settings 又可能反向引用）

        if name not in self.REINIT_ORDER:
            raise ValueError(f"未知组件名: {name}")

        old_instance = getattr(self._service_state, name, None)

        # 按组件类型创建新实例
        if name == "model_router":
            new_instance = await self._reinit_model_router()
        elif name == "llm_client":
            new_instance = await self._reinit_llm_client()
        elif name == "memory_manager":
            new_instance = await self._reinit_memory_manager()
        elif name == "context_manager":
            new_instance = await self._reinit_context_manager()
        elif name == "secondary_router":
            new_instance = self._reinit_secondary_router()
        elif name == "acp_manager":
            new_instance = await self._reinit_acp_manager()
        elif name == "cxfc_manager":
            new_instance = await self._reinit_cxfc_manager()
        else:
            raise ValueError(f"未知组件名: {name}")

        # 原子替换并返回旧实例
        replaced_old = self._service_state.update_component(name, new_instance)

        # 异步关闭旧实例（同步 close 已由 _safe_close 处理，这里只处理 async close）
        # 单例组件（如 model_router）replaced_old 与 new_instance 是同一对象，
        # reinit 方法已自行 close/reinitialize，跳过避免关闭刚初始化的实例
        if replaced_old is not None and replaced_old is not new_instance:
            await self._async_close(replaced_old)

    # ------------------------------------------------------------------ #
    # 各组件具体重建逻辑（参考 backend/api/app.py lifespan L270-340）
    # ------------------------------------------------------------------ #

    def _get_config(self) -> Any:
        """从 settings 获取当前 CXHMSConfig。"""
        if self._settings is None:
            from config.settings import settings as _settings

            return _settings.config
        if hasattr(self._settings, "config"):
            return self._settings.config
        # 兼容直接传 CXHMSConfig 的情况
        return self._settings

    async def _reinit_model_router(self) -> Any:
        """重建 model_router（单例，需先 close 再 initialize）。"""
        from backend.core.model_router import model_router as mr

        # 单例先重置：close 后 _initialized=False，再次 initialize 才会重建客户端
        try:
            await mr.close()
        except Exception as e:
            logger.warning(f"model_router close 失败（继续重建）: {e}")
        await mr.initialize()
        return mr

    async def _reinit_llm_client(self) -> Any:
        """重建 llm_client（从新的 model_router 获取）。"""
        model_router = getattr(self._service_state, "model_router", None)
        if model_router is None:
            raise RuntimeError("model_router 未初始化，无法获取 llm_client")
        client = model_router.get_client("main")
        if client is None:
            raise RuntimeError("model_router.get_client('main') 返回 None")
        return client

    async def _reinit_memory_manager(self) -> Any:
        """重建 memory_manager（含 vector_store）。"""
        from backend.core.memory.manager import MemoryManager

        config = self._get_config()
        db_config = config.database
        mm = MemoryManager(db_path=db_config.memories_db)

        # 启用向量搜索（参考 app.py L449-508）
        llm_client = getattr(self._service_state, "llm_client", None)
        if llm_client and config.memory.vector_enabled:
            vector_backend = config.memory.vector_backend
            if vector_backend == "chroma":
                mm.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="chroma",
                    db_path=config.memory.chroma.db_path,
                    collection_name=config.memory.chroma.collection_name,
                    vector_size=config.memory.chroma.vector_size,
                )
            elif vector_backend == "milvus_lite":
                mm.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="milvus_lite",
                    db_path=config.memory.milvus_lite.db_path,
                    vector_size=config.memory.milvus_lite.vector_size,
                )
            elif vector_backend == "qdrant":
                mm.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="qdrant",
                    host=config.memory.qdrant.host,
                    port=config.memory.qdrant.port,
                    vector_size=config.memory.qdrant.vector_size,
                )
            elif vector_backend == "weaviate":
                mm.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="weaviate",
                    host=config.memory.weaviate.host,
                    port=config.memory.weaviate.port,
                    grpc_port=config.memory.weaviate.grpc_port,
                    embedded=False,
                    vector_size=config.memory.weaviate.vector_size,
                    schema_class=config.memory.weaviate.schema_class,
                )
            elif vector_backend == "weaviate_embedded":
                mm.enable_vector_search(
                    embedding_model=llm_client,
                    vector_backend="weaviate_embedded",
                    embedded=True,
                    vector_size=config.memory.weaviate.vector_size,
                    schema_class=config.memory.weaviate.schema_class,
                )
        return mm

    async def _reinit_context_manager(self) -> Any:
        """重建 context_manager。"""
        from backend.core.context.manager import ContextManager

        config = self._get_config()
        return ContextManager(db_path=config.database.sessions_db)

    def _reinit_secondary_router(self) -> Any:
        """重建 secondary_router（同步构造）。"""
        from backend.core.memory.secondary_router import SecondaryModelRouter

        memory_manager = getattr(self._service_state, "memory_manager", None)
        llm_client = getattr(self._service_state, "llm_client", None)
        model_router = getattr(self._service_state, "model_router", None)
        context_manager = getattr(self._service_state, "context_manager", None)
        return SecondaryModelRouter(
            memory_manager,
            llm_client,
            model_router=model_router,
            context_manager=context_manager,
        )

    async def _reinit_acp_manager(self) -> Any:
        """重建 acp_manager。"""
        from backend.core.acp.manager import ACPManager

        config = self._get_config()
        acp_manager = ACPManager(data_dir=config.database.acp_db)
        acp_manager.initialize(
            agent_id=config.acp.agent_id,
            agent_name=config.acp.agent_name,
        )
        await acp_manager.start()
        return acp_manager

    async def _reinit_cxfc_manager(self) -> Any:
        """重建 cxfc_manager。"""
        from backend.core.cxfc.manager import CXFCManager

        config = self._get_config()
        cxfc_manager = CXFCManager(
            storage_path=config.cxfc.storage_path,
            heartbeat_timeout=config.cxfc.heartbeat_timeout,
        )
        await cxfc_manager.start()
        return cxfc_manager

    # ------------------------------------------------------------------ #
    # 异步关闭旧实例（补充 _safe_close 未处理的 async close）
    # ------------------------------------------------------------------ #

    async def _async_close(self, instance: Any) -> None:
        """异步关闭旧实例。

        优先级：shutdown (async) > close (async)。
        若只有同步 close/shutdown，则跳过（_safe_close 已处理）。
        """
        try:
            if hasattr(instance, "shutdown") and inspect.iscoroutinefunction(
                instance.shutdown
            ):
                await instance.shutdown()
            elif hasattr(instance, "close") and inspect.iscoroutinefunction(
                instance.close
            ):
                await instance.close()
        except Exception as e:
            logger.warning(
                f"异步关闭旧实例失败 [{type(instance).__name__}/{type(e).__name__}]: {e}"
            )

    # ------------------------------------------------------------------ #
    # 状态查询（同步）
    # ------------------------------------------------------------------ #

    def get_status(self) -> Dict[str, Any]:
        """获取当前 reinit 状态。

        Returns:
            运行中: {"status": "running", "current_component": ..., "progress": "N/M"}
            空闲:   {"status": "idle", "last_result": ..., "last_at": ...}
        """
        with self._lock:
            # M8-a：由重入标志驱动 running 状态
            # （原 _current_task 从不赋值，属死代码判断，已替换）
            if self._reinit_in_progress:
                affected_count = (
                    len(self._last_result.affected) if self._last_result else 0
                )
                return {
                    "status": "running",
                    "current_component": self._current_component,
                    "progress": f"{affected_count}/{len(self.REINIT_ORDER)}",
                }
            return {
                "status": "idle",
                "last_result": (
                    self._last_result.__dict__ if self._last_result else None
                ),
                "last_at": self._last_at,
            }
