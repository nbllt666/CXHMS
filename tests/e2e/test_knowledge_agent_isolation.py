"""模块11 Agent 知识库隔离与删除清理 E2E（simulation 模式）。"""

import json
import os
import time

import pytest

from backend.api.routers.agents import _cleanup_agent_knowledge
from backend.core.knowledge.config import resolve_project_path
from backend.core.knowledge.manager import safe_agent_id

KNOWLEDGE = "/api/knowledge"


def _upload(client, agent_id: str, filename: str, text: str):
    return client.post(
        f"{KNOWLEDGE}/upload",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
        data={"agent_id": agent_id, "tags": json.dumps(["isolation"])},
    )


def _wait_parsed(client, agent_id: str, document_id: str, timeout: float = 5.0) -> dict:
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
    pytest.fail(f"文档 {document_id} 未完成解析: {latest}")


def test_agent_a_and_b_are_isolated(client):
    upload_a = _upload(client, "agent_a", "a.txt", "ALPHA_ONLY agent A 的专属知识")
    upload_b = _upload(client, "agent_b", "b.txt", "BETA_ONLY agent B 的专属知识")
    assert upload_a.status_code == 200, upload_a.text
    assert upload_b.status_code == 200, upload_b.text
    document_a = upload_a.json()["document_id"]
    document_b = upload_b.json()["document_id"]
    _wait_parsed(client, "agent_a", document_a)
    _wait_parsed(client, "agent_b", document_b)

    docs_a = client.get(f"{KNOWLEDGE}/documents", params={"agent_id": "agent_a"}).json()
    docs_b = client.get(f"{KNOWLEDGE}/documents", params={"agent_id": "agent_b"}).json()
    docs_default = client.get(f"{KNOWLEDGE}/documents").json()

    assert {row["document_id"] for row in docs_a["documents"]} == {document_a}
    assert {row["document_id"] for row in docs_b["documents"]} == {document_b}
    assert docs_default["documents"] == []

    # 交叉查询返回 404（不同 SQLite）
    assert (
        client.get(f"{KNOWLEDGE}/documents/{document_b}", params={"agent_id": "agent_a"}).status_code
        == 404
    )

    # 检索不跨 agent 泄漏（查询串与 agent A 文档无共享 n-gram）
    hits_a = client.post(
        f"{KNOWLEDGE}/search",
        json={"agent_id": "agent_a", "query": "ZZZQQQ", "top_k": 5},
    ).json()["hits"]
    assert hits_a == []


def test_cleanup_removes_agent_storage_and_is_idempotent(client):
    uploaded = _upload(client, "agent_cleanup", "cleanup.txt", "待清理的 agent 知识")
    assert uploaded.status_code == 200
    _wait_parsed(client, "agent_cleanup", uploaded.json()["document_id"])

    registry = client.app.state.services.knowledge_registry
    safe = safe_agent_id("agent_cleanup")
    db_path = os.path.join(
        resolve_project_path(str(registry.config["db_dir"])),
        f"{registry.config['db_filename_prefix']}_{safe}.db",
    )
    files_root = os.path.join(
        resolve_project_path(str(registry.config["files_dir"])), safe
    )
    assert os.path.exists(db_path)
    assert os.path.isdir(files_root)

    _cleanup_agent_knowledge("agent_cleanup")
    assert not os.path.exists(db_path)
    assert not os.path.exists(f"{db_path}-wal")
    assert not os.path.exists(f"{db_path}-shm")
    assert not os.path.exists(files_root)

    # 幂等：重复清理不抛异常
    _cleanup_agent_knowledge("agent_cleanup")


def test_cleanup_protects_default_agent(client):
    uploaded = _upload(client, "default", "keep.txt", "default agent 必须被保留的知识")
    assert uploaded.status_code == 200
    document_id = uploaded.json()["document_id"]
    _wait_parsed(client, "default", document_id)

    _cleanup_agent_knowledge("default")

    documents = client.get(f"{KNOWLEDGE}/documents").json()["documents"]
    assert any(row["document_id"] == document_id for row in documents)
