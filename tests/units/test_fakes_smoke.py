"""fakes smoke 测试：验证每个 fake 可独立实例化且关键方法可调用。

覆盖 tests/fakes/ 下 4 个 Fake 类 + InMemoryGraphDatabase 底层原语：
    - FakeLLMClient          chat / stream_chat / model_name / is_available / get_embedding
    - FakeEmbeddingModel     get_embedding / get_embeddings / dimension / name
    - InMemoryVectorStore    is_available / add_memory_vector / search_similar / get_collection_info
    - InMemoryGraphStore     create_entity / get_entity / get_stats
    - InMemoryGraphDatabase  initialize / health_check / add_node / search_nodes
    - FakeModelRouter        initialize / get_client / model_name / close

设计原则：仅验证"可实例化 + 关键方法可调用"，不验证业务逻辑（业务逻辑由
simulation scenarios 与 G3 单元测试覆盖）。
"""

import asyncio

import pytest


# --------------------------------------------------------------------------- #
# FakeLLMClient
# --------------------------------------------------------------------------- #


def test_fake_llm_instantiable():
    """FakeLLMClient 可无参实例化。"""
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient()
    assert client is not None
    assert client.model == "fake-llm"


def test_fake_llm_inherits_real_abc():
    """FakeLLMClient 继承 backend.core.llm.client.LLMClient。"""
    from backend.core.llm.client import LLMClient
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient()
    assert isinstance(client, LLMClient)


def test_fake_llm_model_name():
    """model_name 属性返回 fake/{model}。"""
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient(model="test-model")
    assert client.model_name == "fake/test-model"


@pytest.mark.asyncio
async def test_fake_llm_is_available():
    """is_available() 返回 True（无网络 IO）。"""
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient()
    assert await client.is_available() is True


@pytest.mark.asyncio
async def test_fake_llm_chat_returns_response():
    """chat() 返回 LLMResponse，含 content 与 finish_reason。"""
    from backend.core.llm.client import LLMResponse
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient()
    messages = [{"role": "user", "content": "你好"}]
    response = await client.chat(messages)
    assert isinstance(response, LLMResponse)
    assert response.content
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_fake_llm_stream_chat_yields_chunks():
    """stream_chat() 是异步生成器，至少 yield 一个 chunk。"""
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient()
    messages = [{"role": "user", "content": "测试流式"}]
    chunks = []
    async for chunk in client.stream_chat(messages):
        chunks.append(chunk)
    assert len(chunks) >= 2  # 至少 thinking + content
    assert chunks[0]["type"] == "thinking"


@pytest.mark.asyncio
async def test_fake_llm_get_embedding():
    """get_embedding() 返回非空向量列表。"""
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient()
    embedding = await client.get_embedding("测试文本")
    assert embedding is not None
    assert len(embedding) > 0


@pytest.mark.asyncio
async def test_fake_llm_tool_call_loop():
    """FakeLLMClient 工具调用循环：含算式时返回 tool_calls，tool 消息回传后生成最终 content。"""
    from fakes.fake_llm import FakeLLMClient

    client = FakeLLMClient()
    # 第一轮：触发 calculator 工具调用
    messages = [{"role": "user", "content": "计算 1+2*3"}]
    first = await client.chat(messages)
    assert first.finish_reason == "tool_calls"
    assert first.tool_calls
    # 第二轮：回传 tool 结果，应生成最终 content（不再 tool_calls）
    messages.append(
        {
            "role": "tool",
            "tool_call_id": first.tool_calls[0]["id"],
            "content": '{"success": true, "result": 7, "expression": "1+2*3"}',
        }
    )
    second = await client.chat(messages)
    assert second.finish_reason == "stop"
    assert "7" in second.content


# --------------------------------------------------------------------------- #
# FakeEmbeddingModel
# --------------------------------------------------------------------------- #


def test_fake_embedding_instantiable():
    """FakeEmbeddingModel 可无参实例化。"""
    from fakes.fake_embedding import FakeEmbeddingModel

    model = FakeEmbeddingModel()
    assert model is not None


def test_fake_embedding_inherits_real_abc():
    """FakeEmbeddingModel 继承 EmbeddingModel。"""
    from backend.core.memory.embedding import EmbeddingModel
    from fakes.fake_embedding import FakeEmbeddingModel

    model = FakeEmbeddingModel()
    assert isinstance(model, EmbeddingModel)


def test_fake_embedding_dimension_and_name():
    """dimension=256，name=fake/n-gram。"""
    from fakes.fake_embedding import FakeEmbeddingModel

    model = FakeEmbeddingModel()
    assert model.dimension == 256
    assert model.name == "fake/n-gram"


@pytest.mark.asyncio
async def test_fake_embedding_get_embedding():
    """get_embedding() 返回 256 维归一化向量，相同文本确定性。"""
    from fakes.fake_embedding import FakeEmbeddingModel

    model = FakeEmbeddingModel()
    vec1 = await model.get_embedding("测试")
    vec2 = await model.get_embedding("测试")
    assert len(vec1) == 256
    assert vec1 == vec2  # 确定性


@pytest.mark.asyncio
async def test_fake_embedding_get_embeddings_batch():
    """get_embeddings() 批量返回，数量与输入一致。"""
    from fakes.fake_embedding import FakeEmbeddingModel

    model = FakeEmbeddingModel()
    texts = ["你好", "世界", "测试"]
    embeddings = await model.get_embeddings(texts)
    assert len(embeddings) == 3
    for emb in embeddings:
        assert len(emb) == 256


# --------------------------------------------------------------------------- #
# InMemoryVectorStore
# --------------------------------------------------------------------------- #


def test_vector_store_instantiable():
    """InMemoryVectorStore 可无参实例化。"""
    from fakes.fake_vector_store import InMemoryVectorStore

    store = InMemoryVectorStore()
    assert store is not None
    assert store.is_available() is True


def test_vector_store_inherits_real_base():
    """InMemoryVectorStore 继承 VectorStoreBase。"""
    from backend.core.memory.vector_store import VectorStoreBase
    from fakes.fake_vector_store import InMemoryVectorStore

    store = InMemoryVectorStore()
    assert isinstance(store, VectorStoreBase)


@pytest.mark.asyncio
async def test_vector_store_add_and_search():
    """add_memory_vector + search_similar 可调用且返回合理结果。"""
    from fakes.fake_embedding import FakeEmbeddingModel
    from fakes.fake_vector_store import InMemoryVectorStore

    store = InMemoryVectorStore()
    embedding_model = FakeEmbeddingModel()
    emb = await embedding_model.get_embedding("测试记忆内容")
    ok = await store.add_memory_vector(
        memory_id=1, content="测试记忆内容", embedding=emb, metadata={"agent_id": "default"}
    )
    assert ok is True
    results = await store.search_similar(query_embedding=emb, limit=5, min_score=0.0)
    assert isinstance(results, list)
    assert len(results) >= 1
    assert results[0]["memory_id"] == 1


def test_vector_store_collection_info():
    """get_collection_info 返回含 count 的 dict。"""
    from fakes.fake_vector_store import InMemoryVectorStore

    store = InMemoryVectorStore()
    info = store.get_collection_info()
    assert isinstance(info, dict)
    assert "count" in info
    assert info["status"] == "available"


# --------------------------------------------------------------------------- #
# InMemoryGraphStore / InMemoryGraphDatabase
# --------------------------------------------------------------------------- #


def test_graph_store_instantiable():
    """make_in_memory_graph_store 工厂返回 (db, store) 元组，store 可用。"""
    from fakes.fake_graph import InMemoryGraphDatabase, InMemoryGraphStore, make_in_memory_graph_store

    gdb, store = make_in_memory_graph_store(agent_id="default")
    assert isinstance(gdb, InMemoryGraphDatabase)
    assert isinstance(store, InMemoryGraphStore)


def test_graph_store_inherits_real_abc():
    """InMemoryGraphStore 继承 GraphStoreBase。"""
    from backend.core.memory.graph_store import GraphStoreBase
    from fakes.fake_graph import InMemoryGraphStore, make_in_memory_graph_store

    _gdb, store = make_in_memory_graph_store()
    assert isinstance(store, GraphStoreBase)


def test_graph_database_health_check():
    """InMemoryGraphDatabase.health_check 返回健康状态 dict。"""
    from fakes.fake_graph import InMemoryGraphDatabase

    gdb = InMemoryGraphDatabase(agent_id="default")
    gdb.initialize()
    health = gdb.health_check()
    assert isinstance(health, dict)
    assert health.get("overall") == "healthy"


def test_graph_store_create_and_get_entity():
    """create_entity + get_entity 可调用且返回 Entity。

    注意：create_entity 让底层 DB 生成节点 id（对齐 SQLiteGraphStore 行为），
    输入 Entity.entity_id 不被使用；应使用返回的 created.entity_id 查询。
    """
    from backend.core.memory.graph_store import Entity, GraphLibrary
    from fakes.fake_graph import make_in_memory_graph_store

    _gdb, store = make_in_memory_graph_store()
    entity = Entity(
        entity_id="ignored-by-create",
        name="测试实体",
        entity_type="concept",
        properties={"key": "value"},
    )
    created = store.create_entity(entity, GraphLibrary.CONCEPT)
    assert created is not None
    assert created.entity_id  # DB 生成的 id 非空
    fetched = store.get_entity(created.entity_id, GraphLibrary.CONCEPT)
    assert fetched is not None
    assert fetched.name == "测试实体"


def test_graph_store_get_stats():
    """get_stats 返回含 entity_count/relation_count 的 dict。"""
    from backend.core.memory.graph_store import Entity, GraphLibrary
    from fakes.fake_graph import make_in_memory_graph_store

    _gdb, store = make_in_memory_graph_store()
    entity = Entity(
        entity_id="stat-entity", name="统计实体", entity_type="concept"
    )
    store.create_entity(entity, GraphLibrary.CONCEPT)
    stats = store.get_stats(GraphLibrary.CONCEPT)
    assert isinstance(stats, dict)
    assert stats["entity_count"] >= 1


# --------------------------------------------------------------------------- #
# FakeModelRouter
# --------------------------------------------------------------------------- #


def test_fake_model_router_instantiable():
    """FakeModelRouter 可无参实例化。"""
    from fakes.fake_llm import FakeLLMClient, FakeModelRouter

    router = FakeModelRouter()
    assert router is not None
    # get_client 任意 name 返回 FakeLLMClient
    client = router.get_client("main")
    assert isinstance(client, FakeLLMClient)


@pytest.mark.asyncio
async def test_fake_model_router_initialize_and_close():
    """initialize + close 生命周期可调用。"""
    from fakes.fake_llm import FakeModelRouter

    router = FakeModelRouter()
    await router.initialize()
    assert router.is_available("main") is True
    await router.close()


def test_fake_model_router_model_name():
    """model_name 透传底层 FakeLLMClient。"""
    from fakes.fake_llm import FakeModelRouter

    router = FakeModelRouter()
    assert router.model_name == "fake/fake-llm"
