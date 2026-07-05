"""CXHMS 测试根 conftest。

G2 任务产物：补全公共 fixtures，对齐 spec tasks.md Task G2 要求。

fixtures 清单（供 G3/G5/G7 等下游测试任务使用）：
    - mock_settings       测试配置 dict（含 default.yaml 关键字段）
    - fake_llm            FakeLLMClient 实例（继承 backend.core.llm.client.LLMClient）
    - fake_embedding      FakeEmbeddingModel 实例（继承 EmbeddingModel）
    - fake_vector_store   InMemoryVectorStore 实例（继承 VectorStoreBase）
    - fake_graph_store    InMemoryGraphStore 实例（继承 GraphStoreBase）
    - memory_manager      MemoryManager 实例（tmp_path db + fakes 注入，D2 按 db_path 实例化）
    - sim_app             模拟模式 FastAPI TestClient（CXHMS_SIMULATION 触发 lifespan 装配 ServiceState）
    - client              同步 TestClient（复用 sim_app）
    - async_client        httpx.AsyncClient（ASGITransport，复用 sim_app 已启动的 app）
    - sim_actor           SimUserActor（业务语义驱动 sim_app）

依赖注入说明（D1 ServiceState 模式）：
    backend/dependencies.py 的 ServiceState 在 lifespan 中初始化并挂到
    app.state.services；路由通过 Depends(get_service_state) 获取。
    sim_app 通过 CXHMS_SIMULATION=1 触发 lifespan 的模拟分支
    （_build_sim_service_state），由 lifespan 装配 ServiceState 并注入
    fakes 到 app.state.services，符合 D1 注入模式（非模块级全局实例）。
"""

import os
import sys
from typing import AsyncGenerator, Generator

import pytest

# --------------------------------------------------------------------------- #
# sys.path 锚点（rules-0 §三：用 os.path.dirname(os.path.abspath(__file__)) 解析）
# --------------------------------------------------------------------------- #
# tests/ 无 __init__.py，pytest prepend 模式仅把 tests/ 加入 sys.path，
# 但 fakes 与 conftest 内部需要 import backend... / config... / simulation...，
# 故需把项目根 c:\CXHMS\ 显式加入 sys.path。
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# --------------------------------------------------------------------------- #
# 配置 fixture
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_settings() -> dict:
    """提供 mock 配置对象，含 default.yaml 关键字段。

    返回 dict 形式，字段结构对齐 config/default.yaml 的 llm/memory/database
    三大节，供需要 settings 的单元测试使用（不依赖 config.settings 全局单例）。
    """
    return {
        "llm": {
            "provider": "vllm",
            "host": "http://localhost:8002",
            "model": "gemma4-e4b",
            "temperature": 0.7,
            "max_tokens": 4096,
            "max_tool_rounds": 10,
        },
        "memory": {
            "enabled": True,
            "vector_enabled": True,
            "vector_backend": "memory",
            "decay_enabled": True,
            "decay_rate": 0.1,
            "default_importance": 3,
            "max_memories": 10000,
        },
        "database": {
            "type": "sqlite",
            "memories_db": "data/memories.db",
            "sessions_db": "data/sessions.db",
        },
        "embedding": {
            "provider": "vllm",
            "host": "http://localhost:8101",
            "model": "fake/n-gram",
            "dimension": 256,
        },
    }


# --------------------------------------------------------------------------- #
# fakes fixtures（直接实例化 tests/fakes/ 下的 Fake 类）
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_llm():
    """提供 FakeLLMClient 实例（继承 backend.core.llm.client.LLMClient）。

    确定性假 LLM，无网络 IO，支持脚本化回复与工具调用循环。
    """
    from fakes.fake_llm import FakeLLMClient

    return FakeLLMClient()


@pytest.fixture
def fake_embedding():
    """提供 FakeEmbeddingModel 实例（继承 EmbeddingModel）。

    256 维字符级 n-gram 词袋 + sha1 哈希分桶，确定性归一化向量。
    """
    from fakes.fake_embedding import FakeEmbeddingModel

    return FakeEmbeddingModel()


@pytest.fixture
def fake_vector_store():
    """提供 InMemoryVectorStore 实例（继承 VectorStoreBase）。

    线程安全内存向量存储，不依赖 Qdrant/Chroma/Milvus 等外部服务。
    """
    from fakes.fake_vector_store import InMemoryVectorStore

    return InMemoryVectorStore()


@pytest.fixture
def fake_graph_store():
    """提供 InMemoryGraphStore 实例（继承 GraphStoreBase）。

    返回 InMemoryGraphStore（底层 InMemoryGraphDatabase 已 initialize）。
    用 make_in_memory_graph_store 工厂保证底层图数据库已初始化。
    """
    from fakes.fake_graph import make_in_memory_graph_store

    _gdb, graph_store = make_in_memory_graph_store(agent_id="default")
    return graph_store


# --------------------------------------------------------------------------- #
# memory_manager fixture（D2 按 db_path 实例化，fakes 注入）
# --------------------------------------------------------------------------- #


@pytest.fixture
def memory_manager(tmp_path, fake_llm, fake_embedding, fake_vector_store):
    """提供 MemoryManager 实例（用临时 db + fakes 注入）。

    关键：遵循 D1/D2 约束——
      - D2：MemoryManager 按 db_path 实例化，不触碰 _instance 单例。
      - D1：用 enable_vector_search 注入 fakes，而非模块级全局实例。

    Args:
        tmp_path: pytest 内置临时目录（每个测试函数独立）。
        fake_llm: FakeLLMClient（保留参数以匹配 spec G2 签名，供需要 LLM 的
                  集成测试扩展使用；本 fixture 主要用 fake_embedding 注入向量搜索）。
        fake_embedding: FakeEmbeddingModel，注入 enable_vector_search。
        fake_vector_store: InMemoryVectorStore，注入 enable_vector_search。
    """
    from backend.core.memory.manager import MemoryManager

    db_path = os.path.join(str(tmp_path), "memories.db")
    mm = MemoryManager(db_path=db_path)
    mm.enable_vector_search(
        embedding_model=fake_embedding,
        vector_store=fake_vector_store,
    )
    yield mm
    # teardown：关闭记忆管理器，释放资源
    try:
        mm.shutdown()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# sim_app / client / async_client fixtures（CXHMS_SIMULATION + ServiceState）
# --------------------------------------------------------------------------- #


@pytest.fixture
def sim_app(monkeypatch) -> Generator:
    """提供 simulation 模式的 FastAPI TestClient（所有外部依赖用 fakes 替换）。

    通过 CXHMS_SIMULATION=1 环境变量触发 backend.api.app lifespan 的模拟分支
    （_build_sim_service_state），由 lifespan 装配 ServiceState 并注入 fakes 到
    app.state.services（符合 D1 ServiceState + Depends 注入模式）。

    function scope：每个测试函数独立隔离，避免图注册表与工具注册残留。
    teardown 清理 backend.dependencies 的图注册表，对齐 backend/tests/conftest.py。
    """
    import backend.dependencies as _deps
    from backend.api.app import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CXHMS_SIMULATION", "1")

    # 重置图注册表，防止上一次启动残留
    _deps._graph_databases.clear()
    _deps._graph_stores.clear()

    with TestClient(app) as test_client:
        yield test_client

    # teardown：重置图注册表，清空 data/context 目录
    _deps._graph_databases.clear()
    _deps._graph_stores.clear()
    try:
        ctx_dir = os.path.join(_PROJECT_ROOT, "data", "context")
        if os.path.isdir(ctx_dir):
            import shutil

            shutil.rmtree(ctx_dir, ignore_errors=True)
        os.makedirs(ctx_dir, exist_ok=True)
    except Exception:
        pass


@pytest.fixture
def client(sim_app):
    """提供 FastAPI TestClient（同步）。

    复用 sim_app（模拟模式 TestClient），避免无外部依赖时另起真实服务栈。
    """
    return sim_app


@pytest.fixture
async def async_client(sim_app) -> AsyncGenerator:
    """提供 httpx.AsyncClient 测试客户端（FastAPI TestClient 的 async 版本）。

    关键：基于 sim_app 已启动的 app 用 httpx.AsyncClient + ASGITransport 构造
    异步客户端。sim_app 已触发 lifespan，app.state.services 已装配 ServiceState
    （含 fakes），故 ASGITransport 的请求能正常路由到 Depends(get_service_state)。
    """
    from httpx import ASGITransport, AsyncClient

    # sim_app 是 TestClient，其 .app 指向被包装的 FastAPI app
    fastapi_app = sim_app.app
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as ac:
        yield ac


# --------------------------------------------------------------------------- #
# sim_actor fixture（行为驱动测试）
# --------------------------------------------------------------------------- #


@pytest.fixture
def sim_actor(sim_app):
    """提供 SimulationActor 实例（用于行为驱动测试）。

    用 tests/simulation/actor.py 的 SimUserActor 包裹 sim_app，提供
    send_message / send_streaming_message / search_memory 等业务语义方法，
    让测试以业务语义而非裸 HTTP 调用编写断言。
    """
    from simulation.actor import SimUserActor

    return SimUserActor(sim_app)


# --------------------------------------------------------------------------- #
# E2E fixtures (G7): vllm_available / real_app / real_actor
# --------------------------------------------------------------------------- #
#
# 与 sim_app / sim_actor 的区别：
#   - vllm_available: session 级探测 vLLM 服务（http://localhost:8002），不可用时
#     返回 False，供 E2E 测试在开头 pytest.skip 跳过，避免误报失败。
#   - real_app: 不设 CXHMS_SIMULATION，走 backend.api.app lifespan 的真实分支
#     （连接真实 vLLM、真实 SQLite/Weaviate）。teardown 清理图注册表与
#     data/context，与 sim_app 对齐；但不动 data/memories.db、data/sessions.db
#     （真实数据库，由测试内 try/finally 自行清理临时数据）。
#   - real_actor: 用 SimUserActor 包裹 real_app，提供与 sim_actor 一致的业务语义
#     方法，让 E2E 测试以行为驱动方式编写断言。

VLLM_HOST = "http://localhost:8002"


@pytest.fixture(scope="session")
def vllm_available() -> bool:
    """探测 vLLM 服务是否可用（session 级，避免每个测试重复探测）。

    依次尝试 ``/health`` 与 ``/v1/models``，任一返回 200 即视为可用。
    探测失败（连接拒绝、超时、非 200）均返回 False，不抛异常——
    由测试函数自行 ``pytest.skip`` 跳过。
    """
    import httpx

    endpoints = [f"{VLLM_HOST}/health", f"{VLLM_HOST}/v1/models"]
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            for url in endpoints:
                try:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


@pytest.fixture
def real_app(monkeypatch) -> Generator:
    """提供真实模式的 FastAPI TestClient（不设 CXHMS_SIMULATION）。

    与 sim_app 的关键区别：
      - 不设置 ``CXHMS_SIMULATION`` 环境变量，并主动 ``delenv`` 防止上一个
        sim_app 测试残留的变量污染本测试，确保走 lifespan 真实分支。
      - 真实分支会连接真实 vLLM（8002）、真实 SQLite（data/memories.db、
        data/sessions.db）与真实 Weaviate（若配置）。各组件初始化失败时
        降级为 None，路由调用返回 503——需真实 LLM 的测试应用
        ``vllm_available`` fixture 前置 skip。
      - teardown 仅清理图注册表（``_graph_databases`` / ``_graph_stores``）
        与 ``data/context`` 临时目录，**不**删除 ``data/memories.db`` /
        ``data/sessions.db``（真实数据库，由测试内 try/finally 清理临时数据）。

    function scope：每个测试函数独立隔离，避免图注册表与上下文残留。
    """
    import backend.dependencies as _deps
    from backend.api.app import app
    from fastapi.testclient import TestClient

    # 防御性：删除可能由其他测试残留的 CXHMS_SIMULATION
    monkeypatch.delenv("CXHMS_SIMULATION", raising=False)

    # 重置图注册表，防止上一次启动残留
    _deps._graph_databases.clear()
    _deps._graph_stores.clear()

    with TestClient(app) as test_client:
        yield test_client

    # teardown：重置图注册表，清空 data/context 目录
    _deps._graph_databases.clear()
    _deps._graph_stores.clear()
    try:
        ctx_dir = os.path.join(_PROJECT_ROOT, "data", "context")
        if os.path.isdir(ctx_dir):
            import shutil

            shutil.rmtree(ctx_dir, ignore_errors=True)
        os.makedirs(ctx_dir, exist_ok=True)
    except Exception:
        pass


@pytest.fixture
def real_actor(real_app):
    """提供包裹 real_app 的 SimUserActor（用于 E2E 行为驱动测试）。

    与 sim_actor 同样使用 ``tests/simulation/actor.py`` 的 ``SimUserActor``，
    区别在于底层 ``TestClient`` 走真实 lifespan（真实 LLM/数据库/向量存储）。
    """
    from simulation.actor import SimUserActor

    return SimUserActor(real_app)
