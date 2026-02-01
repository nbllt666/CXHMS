import pytest
import asyncio
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.core.memory.manager import MemoryManager
from backend.core.memory.decay import DecayCalculator
from backend.core.memory.secondary_router import SecondaryModelRouter, SecondaryCommand, SecondaryInstruction
from backend.core.context.manager import ContextManager


class TestMemoryManagerBasics:
    """测试记忆管理器基础功能"""

    def test_write_memory(self):
        """测试写入记忆"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_memory(
            content="测试记忆内容",
            memory_type="long_term",
            importance=3,
            tags=["test", "unit"],
            metadata={"source": "test"}
        )

        assert memory_id > 0, "记忆ID应该大于0"

        memory = manager.get_memory(memory_id)
        assert memory is not None, "应该能获取到记忆"
        assert memory["content"] == "测试记忆内容", "记忆内容应该匹配"

        manager.shutdown()

    def test_update_memory(self):
        """测试更新记忆"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_memory(
            content="原始内容",
            memory_type="long_term",
            importance=2
        )

        success = manager.update_memory(
            memory_id=memory_id,
            new_content="更新后的内容",
            new_importance=4
        )

        assert success, "更新应该成功"

        memory = manager.get_memory(memory_id)
        assert memory["content"] == "更新后的内容", "内容应该已更新"
        assert memory["importance"] == 4, "重要性应该已更新"

        manager.shutdown()

    def test_delete_memory(self):
        """测试删除记忆"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_memory(
            content="待删除的记忆",
            memory_type="short_term"
        )

        success = manager.delete_memory(memory_id, soft_delete=True)
        assert success, "删除应该成功"

        memory = manager.get_memory(memory_id)
        assert memory is None, "软删除后不应该能获取到记忆"

        manager.shutdown()


class TestPermanentMemories:
    """测试永久记忆功能"""

    def test_write_permanent_memory(self):
        """测试写入永久记忆"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_permanent_memory(
            content="永久记忆内容",
            tags=["permanent", "important"],
            metadata={"priority": "high"},
            emotion_score=0.8,
            source="user",
            is_from_main=True
        )

        assert memory_id > 0, "永久记忆ID应该大于0"

        memory = manager.get_permanent_memory(memory_id)
        assert memory is not None, "应该能获取到永久记忆"
        assert memory["content"] == "永久记忆内容", "内容应该匹配"
        assert memory["verified"] == True, "应该已验证"

        manager.shutdown()

    def test_get_permanent_memories(self):
        """测试获取永久记忆列表"""
        manager = MemoryManager("test_memories.db")

        manager.write_permanent_memory(
            content="永久记忆1",
            tags=["tag1"]
        )

        manager.write_permanent_memory(
            content="永久记忆2",
            tags=["tag2"]
        )

        memories = manager.get_permanent_memories(limit=10)
        assert len(memories) >= 2, "应该至少有2条永久记忆"

        manager.shutdown()

    def test_update_permanent_memory(self):
        """测试更新永久记忆"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_permanent_memory(
            content="原始永久记忆"
        )

        success = manager.update_permanent_memory(
            memory_id=memory_id,
            content="更新后的永久记忆",
            tags=["updated"]
        )

        assert success, "更新应该成功"

        memory = manager.get_permanent_memory(memory_id)
        assert memory["content"] == "更新后的永久记忆", "内容应该已更新"

        manager.shutdown()

    def test_delete_permanent_memory(self):
        """测试删除永久记忆"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_permanent_memory(
            content="待删除的永久记忆"
        )

        success = manager.delete_permanent_memory(memory_id, is_from_main=True)
        assert success, "删除应该成功"

        memory = manager.get_permanent_memory(memory_id)
        assert memory is None, "删除后不应该能获取到记忆"

        manager.shutdown()

    def test_secondary_model_permission(self):
        """测试副模型权限"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_permanent_memory(
            content="测试权限"
        )

        success = manager.delete_permanent_memory(memory_id, is_from_main=False)
        assert not success, "副模型不应该能删除永久记忆"

        manager.shutdown()


class TestMemorySearch:
    """测试记忆搜索功能"""

    def test_search_memories_3d(self):
        """测试三维评分搜索"""
        manager = MemoryManager("test_memories.db")

        manager.write_memory(
            content="重要记忆",
            importance=5,
            tags=["important"]
        )

        manager.write_memory(
            content="普通记忆",
            importance=3,
            tags=["normal"]
        )

        memories = manager.search_memories_3d(
            query="记忆",
            limit=10,
            weights=(0.35, 0.25, 0.4)
        )

        assert len(memories) >= 2, "应该能搜索到记忆"

        for memory in memories:
            assert "final_score" in memory, "应该包含最终分数"
            assert "component_scores" in memory, "应该包含组件分数"
            assert "applied_weights" in memory, "应该包含应用权重"

        manager.shutdown()


class TestMemoryRecall:
    """测试记忆召回功能"""

    def test_recall_memory(self):
        """测试记忆召回"""
        manager = MemoryManager("test_memories.db")

        memory_id = manager.write_memory(
            content="待召回的记忆",
            importance=4,
            emotion_score=0.5
        )

        result = manager.recall_memory(memory_id, emotion_intensity=0.8)

        assert result is not None, "应该能召回记忆"
        assert "reactivation_details" in result, "应该包含重激活详情"

        memory = manager.get_memory(memory_id)
        assert memory["reactivation_count"] == 1, "重激活次数应该为1"

        manager.shutdown()


class TestMemoryBatchOperations:
    """测试批量操作功能"""

    def test_batch_write_memories(self):
        """测试批量写入"""
        manager = MemoryManager("test_memories.db")

        memories = [
            {"content": f"批量记忆{i}", "importance": 3}
            for i in range(5)
        ]

        result = manager.batch_write_memories(memories)

        assert result["success"] == 5, "应该成功写入5条记忆"
        assert len(result["memory_ids"]) == 5, "应该返回5个记忆ID"

        manager.shutdown()

    def test_batch_update_memories(self):
        """测试批量更新"""
        manager = MemoryManager("test_memories.db")

        memory_ids = []
        for i in range(3):
            memory_id = manager.write_memory(
                content=f"待更新的记忆{i}",
                importance=2
            )
            memory_ids.append(memory_id)

        updates = [
            {"memory_id": mid, "importance": 4}
            for mid in memory_ids
        ]

        result = manager.batch_update_memories(updates)

        assert result["success"] == 3, "应该成功更新3条记忆"

        manager.shutdown()

    def test_batch_delete_memories(self):
        """测试批量删除"""
        manager = MemoryManager("test_memories.db")

        memory_ids = []
        for i in range(3):
            memory_id = manager.write_memory(
                content=f"待删除的记忆{i}"
            )
            memory_ids.append(memory_id)

        result = manager.batch_delete_memories(memory_ids, soft_delete=True)

        assert result["success"] == 3, "应该成功删除3条记忆"

        manager.shutdown()


class TestMemoryDecay:
    """测试记忆衰减功能"""

    def test_calculate_exponential_decay(self):
        """测试指数衰减"""
        calculator = DecayCalculator()

        decay_score = calculator.calculate_exponential_decay(
            importance=0.8,
            days_elapsed=30
        )

        assert 0 < decay_score <= 1.0, "衰减分数应该在0-1之间"
        assert decay_score < 0.8, "衰减后分数应该小于初始值"

    def test_calculate_ebbinghaus_decay(self):
        """测试艾宾浩斯衰减"""
        calculator = DecayCalculator()

        decay_score = calculator.calculate_ebbinghaus_decay(
            importance=0.8,
            days_elapsed=30,
            t50=30.0,
            k=2.0
        )

        assert 0 < decay_score <= 1.0, "衰减分数应该在0-1之间"

    def test_calculate_network_effect(self):
        """测试网络效应"""
        calculator = DecayCalculator()

        base_score = 0.5
        active_count = 9

        enhanced_score = calculator.calculate_network_effect(
            base_score=base_score,
            active_memory_count=active_count
        )

        assert enhanced_score > base_score, "网络效应应该增强分数"
        assert enhanced_score <= 1.0, "增强后分数不应超过1"

    def test_calculate_relevance_score(self):
        """测试相关性评分"""
        calculator = DecayCalculator()

        memory = {
            "content": "测试记忆",
            "tags": ["test"]
        }

        relevance_score = calculator.calculate_relevance_score(
            memory=memory,
            context_score=0.7,
            keyword_match_count=3
        )

        assert 0 <= relevance_score <= 1.0, "相关性分数应该在0-1之间"

    def test_sync_decay_values(self):
        """测试同步衰减值"""
        manager = MemoryManager("test_memories.db")

        manager.write_memory(
            content="测试衰减",
            importance=4
        )

        result = manager.sync_decay_values()

        assert "updated" in result, "应该包含更新数量"
        assert result["updated"] >= 1, "应该至少更新1条记忆"

        manager.shutdown()

    def test_get_decay_statistics(self):
        """测试获取衰减统计"""
        manager = MemoryManager("test_memories.db")

        stats = manager.get_decay_statistics()

        assert "total_memories" in stats, "应该包含总记忆数"
        assert "avg_time_score" in stats, "应该包含平均时间分数"
        assert "importance_distribution" in stats, "应该包含重要性分布"

        manager.shutdown()


class TestSecondaryRouter:
    """测试副模型路由器"""

    def test_get_available_commands(self):
        """测试获取可用命令"""
        manager = MemoryManager("test_memories.db")
        router = SecondaryModelRouter(manager)

        commands = router.get_available_commands()

        assert len(commands) > 0, "应该有可用命令"
        assert SecondaryCommand.SUMMARIZE_MEMORY.value in commands, "应该包含摘要命令"

        manager.shutdown()

    def test_validate_permission(self):
        """测试权限验证"""
        manager = MemoryManager("test_memories.db")
        router = SecondaryModelRouter(manager)

        assert router.validate_permission("summarize_memory", is_from_main=True), "主模型应该有权限"
        assert not router.validate_permission("delete_permanent_memory", is_from_main=False), "副模型不应该有删除永久记忆权限"

        manager.shutdown()

    async def test_execute_command(self):
        """测试执行命令"""
        manager = MemoryManager("test_memories.db")
        router = SecondaryModelRouter(manager)

        memory_id = manager.write_memory(
            content="待摘要的记忆",
            importance=4
        )

        instruction = SecondaryInstruction(
            command=SecondaryCommand.SUMMARIZE_MEMORY.value,
            parameters={"memory_id": memory_id, "max_length": 50}
        )

        result = await router.execute_command(instruction, is_from_main=True)

        assert result.status == "success", "命令应该执行成功"
        assert "output" in result, "应该包含输出"

        manager.shutdown()


class TestContextManager:
    """测试上下文管理器"""

    def test_create_session(self):
        """测试创建会话"""
        ctx_manager = ContextManager("test_memories.db")

        session_id = ctx_manager.create_session(
            workspace_id="test",
            title="测试会话"
        )

        assert session_id is not None, "应该创建会话"

        session = ctx_manager.get_session(session_id)
        assert session is not None, "应该能获取到会话"
        assert session["title"] == "测试会话", "标题应该匹配"

    def test_add_message(self):
        """测试添加消息"""
        ctx_manager = ContextManager("test_memories.db")

        session_id = ctx_manager.create_session()

        message_id = ctx_manager.add_message(
            session_id=session_id,
            role="user",
            content="测试消息"
        )

        assert message_id is not None, "应该添加消息"

        messages = ctx_manager.get_messages(session_id)
        assert len(messages) >= 1, "应该至少有1条消息"

    def test_add_mono_context(self):
        """测试添加Mono上下文"""
        ctx_manager = ContextManager("test_memories.db")

        session_id = ctx_manager.create_session()

        success = ctx_manager.add_mono_context(
            session_id=session_id,
            content="Mono上下文内容",
            rounds=2
        )

        assert success, "应该成功添加Mono上下文"

        mono_contexts = ctx_manager.get_mono_context(session_id)
        assert len(mono_contexts) >= 1, "应该能获取到Mono上下文"

    def test_clear_expired_mono(self):
        """测试清理过期Mono上下文"""
        ctx_manager = ContextManager("test_memories.db")

        session_id = ctx_manager.create_session()

        ctx_manager.add_mono_context(
            session_id=session_id,
            content="即将过期的上下文",
            rounds=0
        )

        deleted_count = ctx_manager.clear_expired_mono(session_id)
        assert deleted_count >= 0, "应该能清理过期上下文"


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始运行记忆系统测试")
    print("=" * 60)

    test_classes = [
        TestMemoryManagerBasics,
        TestPermanentMemories,
        TestMemorySearch,
        TestMemoryRecall,
        TestMemoryBatchOperations,
        TestMemoryDecay,
        TestContextManager
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    for test_class in test_classes:
        print(f"\n测试类: {test_class.__name__}")
        print("-" * 60)

        instance = test_class()

        for method_name in dir(instance):
            if method_name.startswith("test_"):
                total_tests += 1
                test_method = getattr(instance, method_name)

                try:
                    if asyncio.iscoroutinefunction(test_method):
                        asyncio.run(test_method())
                    else:
                        test_method()
                    passed_tests += 1
                    print(f"✓ {method_name}")
                except Exception as e:
                    failed_tests += 1
                    print(f"✗ {method_name}: {e}")

    print("\n" + "=" * 60)
    print(f"测试完成: 总计 {total_tests}, 通过 {passed_tests}, 失败 {failed_tests}")
    print("=" * 60)

    return failed_tests == 0


if __name__ == "__main__":
    import os
    test_db = "test_memories.db"

    if os.path.exists(test_db):
        os.remove(test_db)

    success = run_tests()

    if os.path.exists(test_db):
        os.remove(test_db)

    sys.exit(0 if success else 1)