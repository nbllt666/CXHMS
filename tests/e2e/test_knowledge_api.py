"""模块11 独立知识库 API E2E（simulation 模式，无外部依赖）。

覆盖：健康检查、上传→后台解析→详情、SHA-256 去重、经验写入、混合检索降级、
条目/文档删除、415 类型拦截、413 体积拦截、per-agent 隔离。
"""

import json
import os
import time

import pytest

KNOWLEDGE = "/api/knowledge"


def _files_root(client, agent_id: str = "default") -> str:
    """返回指定 agent 的知识库文件目录。"""
    manager = client.app.state.services.knowledge_registry.get_manager(agent_id)
    return manager.files_root


def _list_files(client, agent_id: str = "default") -> list[str]:
    """列出 agent 知识库目录下的文件（用于断言失败路径不落盘）。"""
    root = _files_root(client, agent_id)
    return sorted(os.listdir(root)) if os.path.isdir(root) else []


def _wait_parsed(client, document_id: str, timeout: float = 5.0, agent_id: str = "default") -> dict:
    """轮询文档直到进入终态（parsed/failed/unsupported）。"""
    deadline = time.time() + timeout
    latest: dict = {}
    while time.time() < deadline:
        response = client.get(
            f"{KNOWLEDGE}/documents/{document_id}", params={"agent_id": agent_id}
        )
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest.get("parse_status") in ("parsed", "failed", "unsupported"):
            return latest
        time.sleep(0.05)
    pytest.fail(f"文档 {document_id} 未在 {timeout}s 内完成解析: {latest}")


def _upload(client, filename: str, payload: bytes, mime: str, agent_id: str = "default"):
    """以 multipart 上传文件。"""
    return client.post(
        f"{KNOWLEDGE}/upload",
        files={"file": (filename, payload, mime)},
        data={"agent_id": agent_id, "tags": json.dumps(["e2e"]), "title": ""},
    )


def test_health_reports_module_flags(client):
    response = client.get(f"{KNOWLEDGE}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["vector_enabled"] is False  # 模拟模式显式关闭向量，降级 FTS
    assert set(body) >= {"enabled", "vector_enabled", "fts_enabled", "asr_provider", "ffmpeg_available"}


def test_upload_parse_and_preview(client):
    response = _upload(client, "note.txt", "独立知识库 E2E 测试内容。".encode("utf-8"), "text/plain")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deduplicated"] is False
    assert body["parse_status"] in ("pending", "parsed")

    document = _wait_parsed(client, body["document_id"])
    assert document["parse_status"] == "parsed"
    assert document["chunk_count"] >= 1
    assert "独立知识库" in (document.get("text_preview") or "")


def test_upload_deduplicates_by_sha256(client):
    payload = "重复内容去重验证。".encode("utf-8")
    first = _upload(client, "dup.txt", payload, "text/plain")
    assert first.status_code == 200
    second = _upload(client, "dup-copy.txt", payload, "text/plain")
    assert second.status_code == 200
    body = second.json()
    assert body["deduplicated"] is True
    assert body["document_id"] == first.json()["document_id"]


def test_experience_create_list_search_and_delete(client):
    created = client.post(
        f"{KNOWLEDGE}/entries",
        json={
            "agent_id": "default",
            "title": "可复用经验",
            "content": "独立知识库经验：混合检索应优先向量，不可用时降级 FTS。",
            "tags": ["e2e", "经验"],
            "importance": 4,
        },
    )
    assert created.status_code == 200, created.text
    item = created.json()
    assert item["item_type"] == "experience"
    assert item["importance"] == 4

    listed = client.get(f"{KNOWLEDGE}/items", params={"item_type": "experience"})
    assert listed.status_code == 200
    assert any(row["item_id"] == item["item_id"] for row in listed.json()["items"])

    searched = client.post(
        f"{KNOWLEDGE}/search",
        json={"agent_id": "default", "query": "混合检索", "top_k": 5},
    )
    assert searched.status_code == 200, searched.text
    payload = searched.json()
    assert payload["fallback"] is True
    assert any(hit["item_id"] == item["item_id"] for hit in payload["hits"])

    deleted = client.delete(f"{KNOWLEDGE}/items/{item['item_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert client.get(f"{KNOWLEDGE}/items/{item['item_id']}").status_code == 404


def test_delete_document_cascades(client):
    upload = _upload(client, "delete-me.md", "# 待删除文档\n\n内容用于删除级联验证。".encode("utf-8"), "text/markdown")
    assert upload.status_code == 200
    document_id = upload.json()["document_id"]
    _wait_parsed(client, document_id)

    deleted = client.delete(f"{KNOWLEDGE}/documents/{document_id}")
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert client.get(f"{KNOWLEDGE}/documents/{document_id}").status_code == 404
    assert client.delete(f"{KNOWLEDGE}/documents/{document_id}").status_code == 404


def test_upload_rejects_unsupported_mime(client):
    before = _list_files(client)
    response = _upload(client, "malware.exe", b"MZ\x90\x00", "application/octet-stream")
    assert response.status_code == 415, response.text
    # 失败路径不得落盘
    assert _list_files(client) == before


def test_upload_rejects_oversized_document(client):
    registry = client.app.state.services.knowledge_registry
    registry.config["max_document_size_mb"] = 1
    registry.get_manager("default").config["max_document_size_mb"] = 1

    before = _list_files(client)
    response = _upload(client, "big.txt", b"x" * (2 * 1024 * 1024), "text/plain")
    assert response.status_code == 413, response.text
    # 失败路径不得落盘
    assert _list_files(client) == before


def test_upload_requires_file_field(client):
    before = _list_files(client)
    response = client.post(f"{KNOWLEDGE}/upload", data={"agent_id": "default"})
    assert response.status_code == 422, response.text
    assert _list_files(client) == before


def test_disabled_module_returns_503(client):
    """`enabled=false` 时所有知识库端点统一 503。"""
    registry = client.app.state.services.knowledge_registry
    registry.config["enabled"] = False
    registry.get_manager("default").config["enabled"] = False

    assert client.get(f"{KNOWLEDGE}/health").status_code == 503
    assert client.get(f"{KNOWLEDGE}/documents").status_code == 503
    assert client.post(f"{KNOWLEDGE}/search", json={"query": "任意"}).status_code == 503


def test_agent_isolation(client):
    uploaded = _upload(client, "agent-a.txt", "agent A 专属知识。".encode("utf-8"), "text/plain", agent_id="agent_a")
    assert uploaded.status_code == 200
    document_id = uploaded.json()["document_id"]
    _wait_parsed(client, document_id, agent_id="agent_a")

    # default agent 不可见 agent_a 的文档与条目
    assert client.get(f"{KNOWLEDGE}/documents/{document_id}").status_code == 404
    default_documents = client.get(f"{KNOWLEDGE}/documents").json()
    assert all(row["document_id"] != document_id for row in default_documents["documents"])

    # agent_a 自己可见
    agent_documents = client.get(f"{KNOWLEDGE}/documents", params={"agent_id": "agent_a"}).json()
    assert any(row["document_id"] == document_id for row in agent_documents["documents"])
