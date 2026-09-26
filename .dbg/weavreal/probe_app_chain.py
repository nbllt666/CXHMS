"""端到端装配链探针（GN-004 第十八轮 V-1 / V-2 补强）。

与 `probe_weaviate_real.py` 的区别（关键）：
    旧探针用**合成向量**且**显式** `vector_size=1024` 直连 store → 只证明「1024 维时真实 weaviate 链路可用」，
    **绕过**了 manager / model_router，无法证明「配置 → 客户端维度 → 存储维度」这条注入链在真实环境被采用。
    本探针走**完整应用装配路径**：

        Settings(真实 default.yaml)
          → ModelRouter.initialize()        # 按配置构造各客户端（含 embedding 端点注入）
          → client.dimension                 # 必须来自配置 vector.embedding_dimension
          → MemoryManager.enable_vector_search(embedding_model=<真实客户端>)
          → store.vector_size                # 必须为 1024（经客户端维度优先规则）
          → _sync_vector_for_memory()        # 真实 embedding 服务 + 真实 weaviate 写入

安全：
    - 测试 `memory_id = 9903`（真实数据 MAX(id)=1385，无冲突；避免触发「先删后插」误删真实对象）
    - 结束按 memory_id 清理并复核总数回到基线
    - 同时把「真实 embedding 维度实测」落盘（V-2）
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # c:\CXHMS
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from backend.core.memory.manager import MemoryManager  # noqa: E402
from backend.core.model_router import ModelRouter  # noqa: E402
from config.settings import Settings  # noqa: E402

TEST_ID = 9903
AGENT = "default"
EVIDENCE = ROOT / ".dbg" / "weavreal" / "evidence_app_chain.txt"


def _baseline_and_target(store):
    """只读：返回 (集合总数, 目标 memory_id 的 uuid 列表)。"""
    collection = store._client.collections.get("CXHMSMemory")
    total = collection.aggregate.over_all(total_count=True).total_count
    from weaviate.classes.query import Filter

    objs = collection.query.fetch_objects(
        filters=Filter.by_property("memory_id").equal(TEST_ID), limit=100
    )
    return total, [str(o.uuid) for o in objs.objects]


async def main() -> None:
    lines = []

    def log(msg: str) -> None:
        print(msg)
        lines.append(msg)

    # V-2：实测 embedding 服务维度并落盘（绕过可能存在的代理环境变量）
    with httpx.Client(trust_env=False, timeout=60) as c:
        models = c.get("http://localhost:8101/v1/models").json()
        log(f"EMBED SERVICE models = {[m.get('id') for m in models.get('data', [])]}")
        emb = c.post(
            "http://localhost:8101/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "probe"},
        ).json()["data"][0]["embedding"]
        log(f"REAL EMBEDDING DIM = {len(emb)}")

    # 1) 真实配置
    s = Settings()
    cfg_dim = s.config.vector.embedding_dimension
    cfg_ws = s.config.memory.weaviate.vector_size
    log(f"CONFIG vector.embedding_dimension = {cfg_dim}")
    log(f"CONFIG memory.weaviate.vector_size = {cfg_ws}")

    # 2) 真实装配：ModelRouter（含 embedding 端点注入）
    mr = ModelRouter()
    await mr.initialize()
    client = mr.get_client("main")
    log(f"ASSEMBLED client.type = {type(client).__name__}")
    log(f"ASSEMBLED client.dimension = {client.dimension}")
    log(f"ASSEMBLED client.embedding_host = {getattr(client, 'embedding_host', None)}")
    log(f"ASSEMBLED client.embedding_model = {getattr(client, 'embedding_model', None)}")

    # 3) MemoryManager + enable_vector_search（不显式指定 vector_size，交由客户端维度决定）
    tmp_db = ROOT / ".dbg" / "weavreal" / "appchain.db"
    if tmp_db.exists():
        tmp_db.unlink()
    mm = MemoryManager(db_path=str(tmp_db))
    mm.enable_vector_search(
        embedding_model=client,
        vector_backend="weaviate",
        host=s.config.memory.weaviate.host,
        port=s.config.memory.weaviate.port,
        grpc_port=s.config.memory.weaviate.grpc_port,
        embedded=False,
        schema_class=s.config.memory.weaviate.schema_class,
    )
    store = mm._vector_store
    log(f"STORE vector_size = {store.vector_size}")

    base_total, base_target = _baseline_and_target(store)
    log(f"BASELINE total={base_total} target({TEST_ID})={len(base_target)}")

    # 4) 真实链路写入：真实 embedding 服务 → 真实 weaviate
    content = "[appchain] 装配链路端到端验证"
    meta = {
        "type": "long_term",
        "importance": 3,
        "importance_score": 0.6,
        "tags": [],
        "workspace_id": "default",
        "agent_id": AGENT,
    }
    ok = mm._sync_vector_for_memory(TEST_ID, content, meta)
    log(f"SYNC -> {ok!r}")

    got = await store.get_vector_by_id(TEST_ID, agent_id=AGENT)
    cur_total, cur_target = _baseline_and_target(store)
    log(f"AFTER total={cur_total} target={len(cur_target)}")
    log(f"CONTENT = {got.get('content') if got else None}")

    # 5) 清理
    deleted = await store.delete_by_memory_id(TEST_ID, agent_id=AGENT)
    fin_total, fin_target = _baseline_and_target(store)
    log(f"CLEANUP deleted={deleted} total={fin_total} target={len(fin_target)}")

    try:
        mm.shutdown()
    except Exception:
        pass
    try:
        store.close()
    except Exception:
        pass

    verdict = (
        cfg_dim == store.vector_size
        and client.dimension == cfg_dim
        and ok is True
        and got is not None
        and got.get("content") == content
        and len(cur_target) == 1
        and len(fin_target) == 0
        and fin_total == base_total
    )
    log(f"RESULT: {'PASS' if verdict else 'CHECK-FAILED'}")
    EVIDENCE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("CXHMS_DATABASE_MEMORIES_DB", str(ROOT / ".dbg" / "weavreal" / "appchain.db"))
    asyncio.run(main())