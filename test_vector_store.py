import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.memory.vector_store import create_vector_store


async def test_milvus_lite():
    """测试 Milvus Lite 向量存储"""
    print("=" * 60)
    print("Milvus Lite 向量存储测试")
    print("=" * 60)

    try:
        print("\n1. 创建 Milvus Lite 向量存储...")
        vector_store = create_vector_store(
            backend="milvus_lite",
            db_path="data/test_milvus_lite.db",
            vector_size=768
        )

        if not vector_store.is_available():
            print("   ✗ Milvus Lite 不可用")
            return False

        print("   ✓ Milvus Lite 初始化成功")

        print("\n2. 测试添加向量...")
        test_embedding = [0.1] * 768
        success = await vector_store.add_memory_vector(
            memory_id=1,
            content="测试记忆内容",
            embedding=test_embedding,
            metadata={"type": "test", "importance": 3}
        )

        if success:
            print("   ✓ 向量添加成功")
        else:
            print("   ✗ 向量添加失败")
            return False

        print("\n3. 测试搜索相似向量...")
        results = await vector_store.search_similar(
            query_embedding=test_embedding,
            limit=5,
            min_score=0.5
        )

        if results:
            print(f"   ✓ 找到 {len(results)} 个结果")
            for i, result in enumerate(results[:3], 1):
                print(f"     {i}. ID: {result['memory_id']}, Score: {result['score']:.4f}")
        else:
            print("   ✗ 未找到结果")
            return False

        print("\n4. 测试获取向量...")
        vector = await vector_store.get_vector_by_id(1)
        if vector:
            print(f"   ✓ 获取向量成功: {vector['content'][:20]}...")
        else:
            print("   ✗ 获取向量失败")
            return False

        print("\n5. 测试检查向量是否存在...")
        exists = await vector_store.check_exists(1)
        if exists:
            print("   ✓ 向量存在")
        else:
            print("   ✗ 向量不存在")
            return False

        print("\n6. 获取集合信息...")
        info = vector_store.get_collection_info()
        if "error" not in info:
            print(f"   ✓ 集合信息: {info}")
        else:
            print(f"   ✗ 获取集合信息失败: {info['error']}")
            return False

        print("\n7. 测试删除向量...")
        success = await vector_store.delete_by_memory_id(1)
        if success:
            print("   ✓ 向量删除成功")
        else:
            print("   ✗ 向量删除失败")
            return False

        print("\n8. 清空集合...")
        success = vector_store.clear_collection()
        if success:
            print("   ✓ 集合已清空")
        else:
            print("   ✗ 清空集合失败")
            return False

        print("\n9. 关闭连接...")
        vector_store.close()
        print("   ✓ 连接已关闭")

        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        return True

    except ImportError as e:
        print(f"\n   ✗ 导入错误: {e}")
        print("   提示: 请安装 pymilvus (pip install pymilvus>=2.3.0)")
        return False
    except Exception as e:
        print(f"\n   ✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_qdrant():
    """测试 Qdrant 向量存储"""
    print("\n" + "=" * 60)
    print("Qdrant 向量存储测试")
    print("=" * 60)

    try:
        print("\n1. 创建 Qdrant 向量存储...")
        vector_store = create_vector_store(
            backend="qdrant",
            host="localhost",
            port=6333,
            vector_size=768
        )

        if not vector_store.is_available():
            print("   ✗ Qdrant 不可用")
            print("   提示: 请确保 Qdrant 服务正在运行")
            return False

        print("   ✓ Qdrant 初始化成功")

        print("\n2. 测试添加向量...")
        test_embedding = [0.1] * 768
        success = await vector_store.add_memory_vector(
            memory_id=1,
            content="测试记忆内容",
            embedding=test_embedding,
            metadata={"type": "test", "importance": 3}
        )

        if success:
            print("   ✓ 向量添加成功")
        else:
            print("   ✗ 向量添加失败")
            return False

        print("\n3. 测试搜索相似向量...")
        results = await vector_store.search_similar(
            query_embedding=test_embedding,
            limit=5,
            min_score=0.5
        )

        if results:
            print(f"   ✓ 找到 {len(results)} 个结果")
            for i, result in enumerate(results[:3], 1):
                print(f"     {i}. ID: {result['memory_id']}, Score: {result['score']:.4f}")
        else:
            print("   ✗ 未找到结果")
            return False

        print("\n4. 关闭连接...")
        vector_store.close()
        print("   ✓ 连接已关闭")

        print("\n" + "=" * 60)
        print("✓ Qdrant 测试通过！")
        print("=" * 60)
        return True

    except ImportError as e:
        print(f"\n   ✗ 导入错误: {e}")
        print("   提示: 请安装 qdrant-client (pip install qdrant-client>=1.7.0)")
        return False
    except Exception as e:
        print(f"\n   ✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("\n选择要测试的向量存储后端:")
    print("1. Milvus Lite (推荐，无需额外服务)")
    print("2. Qdrant (需要 Qdrant 服务)")
    print("3. 全部测试")
    print("0. 退出")

    choice = input("\n请输入选项 (0-3): ").strip()

    if choice == "1":
        await test_milvus_lite()
    elif choice == "2":
        await test_qdrant()
    elif choice == "3":
        milvus_success = await test_milvus_lite()
        qdrant_success = await test_qdrant()
        
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        print(f"Milvus Lite: {'✓ 通过' if milvus_success else '✗ 失败'}")
        print(f"Qdrant:       {'✓ 通过' if qdrant_success else '✗ 失败'}")
        print("=" * 60)
    elif choice == "0":
        print("退出测试")
    else:
        print("无效的选项")


if __name__ == "__main__":
    asyncio.run(main())
