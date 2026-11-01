"""模块11 独立知识库存储层单元测试（Task 2）。

覆盖 spec `add-standalone-knowledge-base` Task 2 闭合判据：
1. 文档 SHA-256 去重返回既有记录 + `deduplicated=True`；
2. `doc_chunk` 跨文档相同片段不被合并，`experience` 同内容合并；
3. 软删除后 `list/get/search` 均不可见（文档删除级联条目）；
4. FTS5 trigram 中文 2 字查询可召回（如「知识库经验沉淀」查「经验」）；
5. tags 过滤与分页 total 正确；
6. jsonschema 不合规（缺 document_id / 缺 content）抛 `KnowledgeValidationError` 且不落库。

降级说明：若本机 SQLite 不支持 FTS5 trigram，检索自动降级 LIKE；用例断言
降级路径仍可召回（不做静默 skip）。

运行方式：
    python -m pytest tests/units/test_knowledge_store.py -q
"""

import hashlib

import pytest

from backend.core.knowledge.exceptions import KnowledgeValidationError
from backend.core.knowledge.models import SEARCH_HIT_FIELDS
from backend.core.knowledge.store import KnowledgeStore

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# fixtures 与构造辅助
# --------------------------------------------------------------------------- #


@pytest.fixture
def store(tmp_path):
    """构造临时库 store（外部注入 db_path，测试结束关闭连接）。"""
    instance = KnowledgeStore(str(tmp_path / "knowledge.db"))
    try:
        yield instance
    finally:
        instance.close()


def _document(
    document_id: str,
    content: bytes,
    agent_id: str = "default",
    filename: str = "note.txt",
    created_at: str = "2026-11-01T00:00:00+00:00",
) -> dict:
    """构造符合 knowledge_document 契约的文档记录。"""
    return {
        "document_id": document_id,
        "agent_id": agent_id,
        "filename": filename,
        "mime": "text/plain",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "parse_status": "parsed",
        "created_at": created_at,
    }


def _chunk(
    item_id: str,
    document_id: str,
    content: str,
    chunk_index: int,
    agent_id: str = "default",
    tags: list[str] | None = None,
    created_at: str = "2026-11-01T00:00:00+00:00",
) -> dict:
    """构造 doc_chunk 条目记录（指纹由 store 计算）。"""
    return {
        "item_id": item_id,
        "agent_id": agent_id,
        "document_id": document_id,
        "item_type": "doc_chunk",
        "title": None,
        "content": content,
        "tags": list(tags or []),
        "importance": 3,
        "chunk_index": chunk_index,
        "created_at": created_at,
    }


def _experience(
    item_id: str,
    content: str,
    agent_id: str = "default",
    tags: list[str] | None = None,
    title: str | None = None,
    created_at: str = "2026-11-01T00:00:00+00:00",
) -> dict:
    """构造 experience 条目记录（指纹由 store 计算）。"""
    return {
        "item_id": item_id,
        "agent_id": agent_id,
        "item_type": "experience",
        "title": title,
        "content": content,
        "tags": list(tags or []),
        "importance": 3,
        "chunk_index": None,
        "created_at": created_at,
    }


# --------------------------------------------------------------------------- #
# 1. 文档 SHA-256 去重
# --------------------------------------------------------------------------- #


def test_upsert_document_sha256_deduplicated(store):
    """同一 agent 内相同 SHA-256 再次写入 → 返回既有记录 + deduplicated=True。"""
    first = store.upsert_document(_document("doc-a", b"same-bytes"))
    assert first["deduplicated"] is False
    assert first["document_id"] == "doc-a"

    second = store.upsert_document(
        _document("doc-b", b"same-bytes", filename="copy.txt")
    )
    assert second["deduplicated"] is True
    assert second["document_id"] == "doc-a"
    assert second["filename"] == "note.txt"

    listing = store.list_documents()
    assert listing["total"] == 1
    assert listing["documents"][0]["document_id"] == "doc-a"


# --------------------------------------------------------------------------- #
# 2. 指纹语义：doc_chunk 跨文档不合并 / experience 合并
# --------------------------------------------------------------------------- #


def test_doc_chunk_not_merged_across_documents(store):
    """不同文档的相同片段指纹不同，不合并。"""
    store.upsert_document(_document("doc-1", b"file-one"))
    store.upsert_document(_document("doc-2", b"file-two"))

    first = store.insert_item(_chunk("chunk-1", "doc-1", "共同片段内容", 0))
    second = store.insert_item(_chunk("chunk-2", "doc-2", "共同片段内容", 0))

    assert first["deduplicated"] is False
    assert second["deduplicated"] is False
    assert first["item_id"] == "chunk-1"
    assert second["item_id"] == "chunk-2"
    assert first["fingerprint"] != second["fingerprint"]
    assert store.list_items(item_type="doc_chunk")["total"] == 2


def test_experience_same_content_merged(store):
    """experience 相同规范化内容 → 返回既有条目 + deduplicated=True。"""
    first = store.insert_item(_experience("exp-1", "用户偏好 简洁回答"))
    second = store.insert_item(_experience("exp-2", "  用户偏好   简洁回答  "))

    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert second["item_id"] == "exp-1"
    assert store.list_items(item_type="experience")["total"] == 1


# --------------------------------------------------------------------------- #
# 3. 软删除可见性
# --------------------------------------------------------------------------- #


def test_soft_delete_item_hidden_everywhere(store):
    """软删除条目后 get/list/search 均不可见。"""
    store.insert_item(_experience("exp-1", "知识库经验沉淀内容", tags=["alpha"]))
    assert store.get_item("exp-1") is not None

    assert store.soft_delete_item("exp-1") is True
    assert store.get_item("exp-1") is None
    assert store.list_items()["total"] == 0
    assert store.keyword_search("沉淀") == []
    assert store.soft_delete_item("exp-1") is False


def test_soft_delete_document_cascades_items(store):
    """文档软删除 → 文档与分块均从 list/get/search 消失。"""
    store.upsert_document(_document("doc-1", b"file-one"))
    store.insert_item(_chunk("chunk-1", "doc-1", "知识库经验沉淀", 0))
    store.insert_item(_chunk("chunk-2", "doc-1", "另一段文本", 1))

    assert store.get_document("doc-1") is not None
    assert store.count_items_by_document("doc-1") == 2

    assert store.soft_delete_document("doc-1") is True
    assert store.get_document("doc-1") is None
    assert store.list_documents()["total"] == 0
    assert store.count_items_by_document("doc-1") == 0
    assert store.get_item("chunk-1") is None
    assert store.list_items()["total"] == 0
    assert store.keyword_search("经验") == []
    assert store.soft_delete_document("doc-1") is False


# --------------------------------------------------------------------------- #
# 4. 中文 2 字查询召回
# --------------------------------------------------------------------------- #


def test_keyword_search_chinese_two_char_recall(store):
    """「知识库经验沉淀」查「经验」（2 字）必须召回；FTS 不可用时走 LIKE 亦召回。"""
    store.insert_item(_experience("exp-1", "知识库经验沉淀，可复用"))

    hits = store.keyword_search("经验")
    print(
        f"[自测] FTS5 trigram 可用 = {store._fts5_available}，"
        f"keyword_search('经验') 命中 {len(hits)} 条"
    )
    assert len(hits) >= 1
    assert hits[0]["item_id"] == "exp-1"
    assert hits[0]["score"] >= 1.0
    assert set(hits[0].keys()) == set(SEARCH_HIT_FIELDS)

    # 3 字以上查询走 trigram 或 LIKE，同样可召回
    longer = store.keyword_search("知识库经验")
    assert any(hit["item_id"] == "exp-1" for hit in longer)


# --------------------------------------------------------------------------- #
# 5. tags 过滤与分页 total
# --------------------------------------------------------------------------- #


def test_tags_filter_and_pagination_total(store):
    """tags 子集过滤与分页 total 正确，keyword_search 同样遵守 tags。"""
    for index in range(1, 4):
        store.insert_item(
            _experience(
                f"exp-a{index}",
                f"分页样本 {index}：知识库经验沉淀",
                tags=["alpha"],
                created_at=f"2026-11-01T00:00:0{index}+00:00",
            )
        )
    for index in range(1, 3):
        store.insert_item(
            _experience(
                f"exp-b{index}",
                f"分页样本 {index}：其他内容",
                tags=["beta"],
                created_at=f"2026-11-01T00:00:1{index}+00:00",
            )
        )

    alpha_listing = store.list_items(tags=["alpha"])
    assert alpha_listing["total"] == 3

    page = store.list_items(tags=["alpha"], limit=1, offset=1)
    assert page["total"] == 3
    assert page["limit"] == 1
    assert page["offset"] == 1
    assert len(page["items"]) == 1
    # created_at 倒序：alpha3 → alpha2 → alpha1
    assert page["items"][0]["item_id"] == "exp-a2"

    searched = store.keyword_search("分页样本", tags=["alpha"])
    assert len(searched) == 3
    assert all("alpha" in hit["tags"] for hit in searched)

    assert store.list_items(item_type="doc_chunk")["total"] == 0


# --------------------------------------------------------------------------- #
# 6. 契约校验：不合规数据不落库
# --------------------------------------------------------------------------- #


def test_validation_error_blocks_document_insert(store):
    """缺 document_id 的文档 → KnowledgeValidationError，且不落库。"""
    invalid = _document("doc-1", b"payload")
    invalid.pop("document_id")

    with pytest.raises(KnowledgeValidationError) as excinfo:
        store.upsert_document(invalid)
    assert "document_id" in str(excinfo.value)
    assert excinfo.value.error_code == "KNOWLEDGE_VALIDATION_ERROR"
    assert store.list_documents()["total"] == 0


def test_validation_error_blocks_item_insert(store):
    """缺 content 的条目 → KnowledgeValidationError，且不落库。"""
    invalid = _experience("exp-1", "")
    invalid.pop("content")

    with pytest.raises(KnowledgeValidationError):
        store.insert_item(invalid)
    assert store.list_items()["total"] == 0

    # SHA-256 格式不合规同样阻断（64 位十六进制约束）
    bad_hash = _document("doc-x", b"payload")
    bad_hash["sha256"] = "not-a-sha256"
    with pytest.raises(KnowledgeValidationError):
        store.upsert_document(bad_hash)
    assert store.list_documents()["total"] == 0
