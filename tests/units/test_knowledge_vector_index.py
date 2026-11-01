"""模块11 独立知识库 per-agent 向量索引单元测试（Task 7）。

覆盖 spec `add-standalone-knowledge-base` Task 7 闭合判据：
1. 未启用（``vector_enabled=False``）时全部操作安全降级且不抛异常；
2. collection 命名：default → ``{prefix}``，其他 agent → ``{prefix}_{safe_id}``；
3. embedding 适配：仅有 ``get_embedding`` 时逐条调用；优先 ``get_embeddings``；
   失败条目跳过且不写零向量；
4. 非法 agent_id 清洗（``../x`` 不含 ``/``、``.``）；
5. upsert 成功条数、对象属性字段集与向量非零；delete 按 item_id 计数。

说明：本用例不依赖真实 Weaviate 服务，通过注入 fake client 覆盖写入/删除路径；
纯逻辑分支（命名、清洗、embedding 适配、未启用降级）完全不依赖网络。

运行方式：
    python -m pytest tests/units/test_knowledge_vector_index.py -q
"""

from types import SimpleNamespace

import pytest

from backend.core.knowledge.vector_index import KnowledgeVectorIndex

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# fake 客户端（模拟 weaviate-client v4 的调用面）
# --------------------------------------------------------------------------- #


class _FakeData:
    """模拟 ``collection.data``。"""

    def __init__(self, collection: "_FakeCollection"):
        self._collection = collection

    def insert(self, properties, vector=None):
        self._collection.inserted.append(
            {"properties": properties, "vector": vector}
        )
        return f"uuid-{len(self._collection.inserted)}"

    def delete_by_id(self, uuid):
        self._collection.deleted_ids.append(uuid)
        return True


class _FakeQuery:
    """模拟 ``collection.query``。"""

    def __init__(self, collection: "_FakeCollection"):
        self._collection = collection

    def fetch_objects(self, filters=None, limit=100, **kwargs):
        # upsert 先删后插路径只关心是否返回对象；这里返回预置结果
        return self._collection.fetch_result

    def near_vector(self, **kwargs):
        result = self._collection.fetch_result
        result.__dict__.setdefault("with_filters", lambda *a, **k: result)
        return result


class _FakeCollection:
    """模拟单个 collection。"""

    def __init__(self):
        self.inserted: list[dict] = []
        self.deleted_ids: list[str] = []
        self.fetch_result = SimpleNamespace(objects=[])
        self.data = _FakeData(self)
        self.query = _FakeQuery(self)


class _FakeCollections:
    """模拟 ``client.collections``。"""

    def __init__(self, exists: bool = True):
        self.exists_flag = exists
        self.created: list[str] = []
        self.deleted: list[str] = []
        self._store: dict[str, _FakeCollection] = {}

    def exists(self, name):
        return self.exists_flag

    def get(self, name):
        return self._store.setdefault(name, _FakeCollection())

    def create(self, name, **kwargs):
        self.created.append(name)
        return None

    def delete(self, name):
        self.deleted.append(name)
        return None


class _FakeClient:
    """模拟 weaviate 客户端。"""

    def __init__(self, exists: bool = True):
        self.collections = _FakeCollections(exists=exists)

    def is_ready(self):
        return True


# --------------------------------------------------------------------------- #
# fake embedding 客户端
# --------------------------------------------------------------------------- #


class _SingleEmbedding:
    """只有 ``get_embedding`` 的 embedding 客户端（对齐 llm/client.py 现状）。"""

    def __init__(self, fail_on=None):
        self.calls: list[str] = []
        self.fail_on = set(fail_on or [])

    async def get_embedding(self, text: str):
        self.calls.append(text)
        if text in self.fail_on:
            raise RuntimeError(f"embedding failed: {text}")
        return [float(len(text) + 1.0), 1.0]


class _BatchEmbedding:
    """同时具备 ``get_embeddings`` / ``get_embedding`` 的客户端。"""

    def __init__(self):
        self.batch_calls: list[list[str]] = []
        self.single_calls = 0

    async def get_embeddings(self, texts):
        self.batch_calls.append(list(texts))
        return [[float(len(text) + 1.0), 0.5] for text in texts]

    async def get_embedding(self, text: str):
        self.single_calls += 1
        raise AssertionError("存在 get_embeddings 时不得逐条调用 get_embedding")


def _attach_fake_client(index: KnowledgeVectorIndex, exists: bool = True) -> _FakeClient:
    """把 fake client 注入索引（绕过真实连接）。"""
    client = _FakeClient(exists=exists)
    index._client = client
    index._connect_failed = False
    return client


# --------------------------------------------------------------------------- #
# 1. 未启用降级
# --------------------------------------------------------------------------- #


async def test_disabled_index_degrades_safely():
    """vector_enabled=False 时所有操作安全返回且不抛。"""
    index = KnowledgeVectorIndex({"vector_enabled": False})

    assert index.is_available() is False
    assert await index.search("agent", "查询") == []
    assert await index.upsert("agent", [{"item_id": "i1", "content": "内容"}]) == 0
    assert await index.delete("agent", ["i1"]) == 0
    assert index.delete_agent_collection("agent") is False


# --------------------------------------------------------------------------- #
# 2. collection 命名
# --------------------------------------------------------------------------- #


def test_collection_naming_default_and_agent():
    """default 不加后缀；普通 agent 使用 ``{prefix}_{safe_id}``。"""
    index = KnowledgeVectorIndex({})

    assert index._safe_agent_id("default") == ""
    assert index._collection_name("default") == "CXHMSKnowledge"
    assert index._collection_name("agent_123") == "CXHMSKnowledge_agent_123"

    custom = KnowledgeVectorIndex({"collection_prefix": "MyKB"})
    assert custom._collection_name("default") == "MyKB"
    assert custom._collection_name("agent_123") == "MyKB_agent_123"


# --------------------------------------------------------------------------- #
# 3. embedding 适配
# --------------------------------------------------------------------------- #


async def test_embedding_adapter_prefers_batch():
    """存在 get_embeddings 时优先批量调用，不逐条调用。"""
    embedding = _BatchEmbedding()
    index = KnowledgeVectorIndex({}, embedding_model=embedding)

    vectors = await index._embed_texts(["a", "bb"])

    assert embedding.batch_calls == [["a", "bb"]]
    assert embedding.single_calls == 0
    assert all(vector is not None for vector in vectors)


async def test_embedding_adapter_per_item_and_skips_failure():
    """只有 get_embedding 时逐条调用；失败条目返回 None 且不产生零向量。"""
    embedding = _SingleEmbedding(fail_on={"bad"})
    index = KnowledgeVectorIndex({}, embedding_model=embedding)

    vectors = await index._embed_texts(["ok", "bad"])

    assert embedding.calls == ["ok", "bad"]
    assert vectors[0] is not None
    assert all(component != 0.0 for component in vectors[0])
    assert vectors[1] is None


async def test_upsert_uses_per_item_embedding_without_zero_vectors():
    """仅有 get_embedding 时 upsert 逐条嵌入；失败条目跳过，写入向量非零。"""
    index = KnowledgeVectorIndex({})
    _attach_fake_client(index)
    embedding = _SingleEmbedding(fail_on={"坏内容"})
    index.embedding_model = embedding

    items = [
        {
            "item_id": "i1",
            "agent_id": "agent_123",
            "item_type": "doc_chunk",
            "title": "标题1",
            "content": "好内容",
            "tags": ["tag1"],
            "document_id": "doc1",
            "created_at": "2026-11-01T00:00:00+00:00",
        },
        {
            "item_id": "i2",
            "item_type": "experience",
            "content": "坏内容",
            "tags": [],
        },
    ]

    written = await index.upsert("agent_123", items)
    collection = index._client.collections.get("CXHMSKnowledge_agent_123")

    assert written == 1
    assert embedding.calls == ["好内容", "坏内容"]
    assert len(collection.inserted) == 1

    inserted = collection.inserted[0]
    assert all(component != 0.0 for component in inserted["vector"])
    assert set(inserted["properties"].keys()) == {
        "item_id",
        "agent_id",
        "item_type",
        "title",
        "content",
        "tags",
        "document_id",
        "created_at",
    }
    assert inserted["properties"]["item_id"] == "i1"
    assert inserted["properties"]["tags"] == ["tag1"]


async def test_upsert_returns_zero_when_embedding_model_missing():
    """embedding_model 缺失时 upsert 返回 0（不伪造零向量）。"""
    index = KnowledgeVectorIndex({})
    _attach_fake_client(index)

    written = await index.upsert("agent", [{"item_id": "i1", "content": "内容"}])

    assert written == 0
    collection = index._client.collections.get("CXHMSKnowledge_agent")
    assert collection.inserted == []


# --------------------------------------------------------------------------- #
# 4. 非法 agent_id 清洗
# --------------------------------------------------------------------------- #


def test_illegal_agent_id_is_sanitized():
    """非法字符替换为下划线，且不以字母/下划线开头时补 agent_ 前缀。"""
    index = KnowledgeVectorIndex({})

    safe = index._safe_agent_id("../x")
    assert "/" not in safe
    assert "." not in safe

    digit_leading = index._safe_agent_id("123abc")
    assert digit_leading.startswith("agent_")

    assert index._collection_name("../x") == f"CXHMSKnowledge_{safe}"


# --------------------------------------------------------------------------- #
# 5. 删除与 collection 删除
# --------------------------------------------------------------------------- #


async def test_delete_counts_removed_objects():
    """delete 按 item_id 匹配删除并返回删除数量。"""
    index = KnowledgeVectorIndex({})
    client = _attach_fake_client(index)
    collection = client.collections.get("CXHMSKnowledge_agent_123")
    collection.fetch_result = SimpleNamespace(
        objects=[SimpleNamespace(uuid="u1"), SimpleNamespace(uuid="u2")]
    )

    deleted = await index.delete("agent_123", ["i1"])

    assert deleted == 2
    assert collection.deleted_ids == ["u1", "u2"]


async def test_delete_agent_collection_idempotent():
    """collection 删除幂等：存在则删除返回 True，不存在也返回 True。"""
    index = KnowledgeVectorIndex({})
    client = _attach_fake_client(index, exists=True)
    assert index.delete_agent_collection("agent_123") is True
    assert client.collections.deleted == ["CXHMSKnowledge_agent_123"]

    client_missing = _attach_fake_client(index, exists=False)
    assert index.delete_agent_collection("agent_123") is True
    assert client_missing.collections.deleted == []
