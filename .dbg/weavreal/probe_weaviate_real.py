"""weaviate 真实后端验证探针（人类授权：写入 + 清理）。

目标（验证此前仅由 mock 单测覆盖的行为在**真实 weaviate** 上的表现）：
    1. 「先删后插」幂等：同一 memory_id 连续 add 两次 → 至多 1 条对象（无重复实体）
    2. update_memory_vector：更新后内容一致且仍为 1 条对象
    3. 空向量防御：embedding=None → 返回 False 且对象数不变（真实服务上复测）
    4. delete_by_memory_id：清理后目标对象归零、集合总数回到基线

安全：
    - 使用专用测试 memory_id = 9901（真实数据 MAX(id)=1385，无冲突）
    - 仅操作 collection CXHMSMemory / agent "default"
    - 结束时按 UUID 删除本次创建的全部对象，并复核总数回到基线
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # c:\CXHMS
sys.path.insert(0, str(ROOT))

from backend.core.memory.weaviate_store import WeaviateVectorStore  # noqa: E402

TEST_ID = 9901
VECTOR_SIZE = 1024  # 与配置 vector.embedding_dimension / 真实索引维度一致（Qwen3-Embedding-0.6B）
AGENT = "default"


def _count_and_ids(store: WeaviateVectorStore):
    """返回 (总数, 目标 memory_id 的 uuid 列表)。只读。"""
    collection = store._client.collections.get("CXHMSMemory")
    total = collection.aggregate.over_all(total_count=True).total_count

    from weaviate.classes.query import Filter

    objs = collection.query.fetch_objects(
        filters=Filter.by_property("memory_id").equal(TEST_ID), limit=100
    )
    return total, [str(o.uuid) for o in objs.objects]


async def main() -> None:
    store = WeaviateVectorStore(
        host="localhost", port=8090, grpc_port=50061, embedded=False,
        vector_size=VECTOR_SIZE, schema_class="CXHMSMemory",
    )
    print(f"is_available={store.is_available()}")
    if not store.is_available():
        print("RESULT: SKIP（weaviate 不可用）")
        return

    results = {}
    base_total, base_target = _count_and_ids(store)
    print(f"BASELINE: total={base_total}, target({TEST_ID})={len(base_target)}")
    results["baseline_total"] = base_total

    emb = [0.1] * VECTOR_SIZE
    meta = {"agent_id": AGENT, "type": "long_term", "importance": 3}

    # 1) 先删后插幂等：连续两次 add 同一 memory_id
    r1 = await store.add_memory_vector(TEST_ID, "[weavreal] 幂等验证 A", emb, meta, agent_id=AGENT)
    t_after_first, ids_first = _count_and_ids(store)
    r2 = await store.add_memory_vector(TEST_ID, "[weavreal] 幂等验证 B", emb, meta, agent_id=AGENT)
    t_after_second, ids_second = _count_and_ids(store)
    print(f"ADD x2: r1={r1} r2={r2} | target={len(ids_first)} -> {len(ids_second)}")
    results["add_ok"] = (r1 is True and r2 is True)
    results["idempotent_target_count"] = len(ids_second)

    # 2) 更新路径
    upd = await store.update_memory_vector(
        TEST_ID, "[weavreal] 更新后内容", emb, meta, agent_id=AGENT
    )
    got = await store.get_vector_by_id(TEST_ID, agent_id=AGENT)
    t_after_update, ids_update = _count_and_ids(store)
    print(f"UPDATE: ok={upd} | target={len(ids_update)} | content={got.get('content') if got else None}")
    results["update_ok"] = upd is True
    results["updated_content_ok"] = bool(got and got.get("content") == "[weavreal] 更新后内容")

    # 3) 空向量防御（真实服务复测）
    rej = await store.add_memory_vector(TEST_ID, "[weavreal] 空向量", None, meta, agent_id=AGENT)
    t_after_reject, ids_after_reject = _count_and_ids(store)
    print(f"EMPTY-DEFENSE: ret={rej} | target={len(ids_after_reject)}")
    results["empty_defense_returns_false"] = (rej is False)
    results["empty_defense_no_write"] = (len(ids_after_reject) == len(ids_update))

    # 4) 清理（按 memory_id 删除本次测试对象）
    deleted = await store.delete_by_memory_id(TEST_ID, agent_id=AGENT)
    final_total, final_target = _count_and_ids(store)
    print(f"CLEANUP: deleted={deleted} | total={final_total} | target={len(final_target)}")
    results["cleanup_ok"] = (len(final_target) == 0)
    results["baseline_restored"] = (final_total == base_total)

    store.close()

    print("=" * 60)
    for k, v in results.items():
        print(f"  {k} = {v}")
    verdict = (
        results.get("add_ok") is True
        and results.get("idempotent_target_count") == 1
        and results.get("updated_content_ok") is True
        and results.get("empty_defense_returns_false") is True
        and results.get("empty_defense_no_write") is True
        and results.get("cleanup_ok") is True
        and results.get("baseline_restored") is True
    )
    print(f"RESULT: {'PASS' if verdict else 'CHECK-FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())