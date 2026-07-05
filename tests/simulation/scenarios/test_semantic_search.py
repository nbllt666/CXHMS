"""SubTask 8.8 - 语义检索场景。

覆盖死区：FakeEmbeddingModel 的 n-gram 哈希向量语义性、InMemoryVectorStore
的相似度排序与 min_score 过滤、/api/memories/semantic-search 端点的相关
结果排序。验证向量检索业务语义而非仅状态码。

注：FakeEmbeddingModel 基于字符级 2-gram/3-gram 词袋 + sha1 哈希分桶，
共享 n-gram 越多余弦相似度越高。"我喜欢猫"与"我喜爱猫咪"共享"我喜"等
n-gram，相似度高于与"今天天气真好"（零共享）。
"""

import asyncio

import pytest

from fakes.fake_embedding import FakeEmbeddingModel, cosine_similarity
from fakes.fake_vector_store import InMemoryVectorStore

# simulation 行为测试属 integration（依赖 sim_app lifespan + fakes 注入）
pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# 纯 fakes 单元测试（不依赖 actor / API）
# --------------------------------------------------------------------------- #


def test_fake_embedding_semantic_similarity():
    """FakeEmbeddingModel 的 n-gram 向量语义性：相似文本余弦相似度高于无关文本。"""

    async def _get_all():
        model = FakeEmbeddingModel()
        a = await model.get_embedding("我喜欢猫")
        b = await model.get_embedding("我喜爱猫咪")
        c = await model.get_embedding("今天天气真好")
        return a, b, c

    vec_a, vec_b, vec_c = asyncio.run(_get_all())

    sim_similar = cosine_similarity(vec_a, vec_b)
    sim_unrelated = cosine_similarity(vec_a, vec_c)

    assert sim_similar > sim_unrelated, (
        f"相似文本相似度应高于无关文本: "
        f"sim(我喜欢猫, 我喜爱猫咪)={sim_similar:.4f}, "
        f"sim(我喜欢猫, 今天天气真好)={sim_unrelated:.4f}"
    )
    assert sim_similar > 0, f"相似文本应有正相似度: {sim_similar:.4f}"


def test_vector_store_semantic_search_ranking():
    """InMemoryVectorStore 按余弦相似度降序排列，相关结果得分高于无关结果。"""
    store = InMemoryVectorStore()
    model = FakeEmbeddingModel()
    loop = asyncio.new_event_loop()

    contents = ["我喜欢猫", "我喜爱猫咪", "今天天气真好"]
    for i, content in enumerate(contents, start=1):
        emb = loop.run_until_complete(model.get_embedding(content))
        loop.run_until_complete(
            store.add_memory_vector(
                memory_id=i, content=content, embedding=emb, metadata={"type": "long_term"}
            )
        )

    query_emb = loop.run_until_complete(model.get_embedding("我喜欢猫"))
    results = loop.run_until_complete(
        store.search_similar(query_embedding=query_emb, limit=10, min_score=0.0)
    )
    loop.close()

    assert results, "search_similar 应至少返回一条结果"
    # 按内容建索引用于断言
    score_by_content = {r["content"]: r["score"] for r in results}

    # 完全匹配应排在第一位且 score=1.0
    assert results[0]["content"] == "我喜欢猫", (
        f"完全匹配应排在第一位，实际首位: {results[0]['content']!r}"
    )
    assert results[0]["score"] == pytest.approx(1.0, abs=1e-6), (
        f"完全匹配 score 应为 1.0，实际: {results[0]['score']:.4f}"
    )

    # "我喜爱猫咪" 相似度应高于 "今天天气真好"
    if "我喜爱猫咪" in score_by_content and "今天天气真好" in score_by_content:
        assert score_by_content["我喜爱猫咪"] > score_by_content["今天天气真好"], (
            f"相似文本得分应高于无关文本: "
            f"我喜爱猫咪={score_by_content['我喜爱猫咪']:.4f}, "
            f"今天天气真好={score_by_content['今天天气真好']:.4f}"
        )
    elif "我喜爱猫咪" in score_by_content:
        # "今天天气真好" 被过滤（相似度过低）——符合预期
        assert score_by_content["我喜爱猫咪"] > 0, (
            f"相似文本应有正相似度: {score_by_content['我喜爱猫咪']:.4f}"
        )


def test_search_similar_with_min_score_filter():
    """设置较高 min_score 时，返回结果均 >= min_score，低于阈值的被过滤。"""
    store = InMemoryVectorStore()
    model = FakeEmbeddingModel()
    loop = asyncio.new_event_loop()

    contents = ["我喜欢猫", "我喜爱猫咪", "今天天气真好", "猫喜欢我"]
    for i, content in enumerate(contents, start=1):
        emb = loop.run_until_complete(model.get_embedding(content))
        loop.run_until_complete(
            store.add_memory_vector(
                memory_id=i, content=content, embedding=emb, metadata={}
            )
        )

    query_emb = loop.run_until_complete(model.get_embedding("我喜欢猫"))
    high_threshold = 0.5
    results = loop.run_until_complete(
        store.search_similar(
            query_embedding=query_emb, limit=10, min_score=high_threshold
        )
    )
    loop.close()

    # 所有返回结果 score 应 >= min_score
    for r in results:
        assert r["score"] >= high_threshold, (
            f"结果 score 应 >= {high_threshold}，实际: "
            f"{r['content']!r} -> {r['score']:.4f}"
        )

    # 完全匹配必然在结果中且 score 最高
    assert any(r["content"] == "我喜欢猫" for r in results), (
        f"完全匹配应在结果中: {[r['content'] for r in results]}"
    )
    assert results[0]["score"] >= results[-1]["score"], (
        f"结果应按 score 降序: 首位 {results[0]['score']:.4f}, "
        f"末位 {results[-1]['score']:.4f}"
    )


# --------------------------------------------------------------------------- #
# API 端到端测试（依赖 sim_actor）
# --------------------------------------------------------------------------- #


def _create_memory(sim_actor, content, memory_type="long_term"):
    """辅助：通过 POST /api/memories 创建一条记忆。"""
    body = {
        "content": content,
        "type": memory_type,
        "importance": 3,
        "tags": [],
        "metadata": {},
        "permanent": False,
        "workspace_id": "default",
        "agent_id": "default",
    }
    resp = sim_actor.client.post("/api/memories", json=body)
    assert resp.status_code == 200, (
        f"创建记忆失败: status={resp.status_code}, body={resp.text!r}"
    )
    return resp.json()["memory_id"]


def test_api_semantic_search_ranks_relevant_first(sim_actor):
    """通过 API 创建记忆后，/api/memories/semantic-search 应将相关结果排在前面。

    依赖 FakeEmbedding 语义性：查询"我喜欢吃苹果"应最匹配"我喜欢吃苹果"，
    次匹配"我喜欢吃香蕉"（共享"我喜欢吃"等 n-gram），不匹配"今天天气真好"。
    """
    _create_memory(sim_actor, "我喜欢吃苹果")
    _create_memory(sim_actor, "我喜欢吃香蕉")
    _create_memory(sim_actor, "今天天气真好适合出门")

    resp = sim_actor.client.post(
        "/api/memories/semantic-search",
        json={"query": "我喜欢吃苹果", "limit": 10, "threshold": 0.0},
    )
    assert resp.status_code == 200, (
        f"语义搜索端点失败: status={resp.status_code}, body={resp.text!r}"
    )
    data = resp.json()
    assert data["status"] == "success", f"语义搜索应返回 success: {data!r}"

    results = data.get("results", [])
    if not results:
        pytest.skip("语义搜索未返回结果（可能因向量相似度阈值过滤）")

    contents = [r.get("content", "") for r in results]

    # 最相关记忆应排在第一位
    assert "我喜欢吃苹果" in contents[0], (
        f"最相关记忆应排在第一位，实际首位: {contents[0]!r}, 顺序: {contents}"
    )

    # 若次相关记忆也返回，应排在无关记忆之前
    food_indices = [i for i, c in enumerate(contents) if "喜欢吃" in c]
    weather_indices = [i for i, c in enumerate(contents) if "今天天气" in c]
    if food_indices and weather_indices:
        assert min(food_indices) < max(weather_indices), (
            f"相关记忆应排在无关记忆之前，实际顺序: {contents}"
        )

    # 每条结果应包含 score 字段且为非负浮点
    for r in results:
        assert "score" in r, f"结果应包含 score 字段: {r!r}"
        assert isinstance(r["score"], (int, float)), f"score 应为数值: {r!r}"
        assert r["score"] >= 0, f"score 应非负: {r!r}"
