"""直接测试 MemoryManager.hybrid_search 是否能找到 memory_id=1388"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 设置工作目录
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from backend.dependencies import get_memory_manager

    mm = get_memory_manager()
    if not mm:
        print("[FAIL] memory_manager 不可用")
        return

    print(f"[INFO] vector_search_enabled: {mm.is_vector_search_enabled()}")

    # 测试 1: hybrid_search
    print("\n=== 测试 1: hybrid_search(query='系统功能测试') ===")
    results = await mm.hybrid_search(query="系统功能测试", limit=5)
    print(f"结果数: {len(results)}")
    for r in results:
        print(f"  - memory_id={r.get('memory_id')}, score={r.get('score')}, source={r.get('source')}, fallback={r.get('fallback')}")
        print(f"    content={r.get('content', '')[:80]}...")

    # 测试 2: semantic_search
    print("\n=== 测试 2: semantic_search(query='系统功能测试') ===")
    results = await mm.semantic_search(query="系统功能测试", limit=5)
    print(f"结果数: {len(results)}")
    for r in results:
        print(f"  - {r}")

    # 测试 3: 直接调用 search_all_memories 工具
    print("\n=== 测试 3: 工具 search_all_memories ===")
    from backend.core.tools.master_tools import search_all_memories
    result = await search_all_memories(query="系统功能测试", limit=5)
    print(f"工具返回: {result}")


if __name__ == "__main__":
    asyncio.run(main())
