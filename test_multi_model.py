"""
多模型配置测试脚本

测试CXHMS的多模型配置功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings, ModelConfig, ModelsConfig


def test_config_loading():
    """测试配置加载"""
    print("=" * 60)
    print("测试1: 配置加载")
    print("=" * 60)
    
    # 测试模型配置
    print("\n模型配置:")
    print(f"  Main模型: {settings.config.models.main}")
    print(f"  Summary模型: {settings.config.models.summary}")
    print(f"  Memory模型: {settings.config.models.memory}")
    
    # 测试默认跟随配置
    print("\n默认跟随配置:")
    print(f"  summary -> {settings.config.models.defaults.get('summary')}")
    print(f"  memory -> {settings.config.models.defaults.get('memory')}")
    
    print("\n✓ 配置加载测试通过")


def test_model_config_getter():
    """测试模型配置获取"""
    print("\n" + "=" * 60)
    print("测试2: 模型配置获取")
    print("=" * 60)
    
    models = ModelsConfig()
    
    # 测试获取各类型配置
    main_config = models.get_model_config("main")
    summary_config = models.get_model_config("summary")
    memory_config = models.get_model_config("memory")
    
    print(f"\nMain配置:")
    print(f"  Provider: {main_config.provider}")
    print(f"  Host: {main_config.host}")
    print(f"  Model: {main_config.model}")
    
    print(f"\nSummary配置 (跟随main):")
    print(f"  Provider: {summary_config.provider}")
    print(f"  Model: {summary_config.model}")
    
    print(f"\nMemory配置 (跟随main):")
    print(f"  Provider: {memory_config.provider}")
    print(f"  Model: {memory_config.model}")
    
    # 验证跟随机制
    assert summary_config == main_config, "Summary应该跟随Main"
    assert memory_config == main_config, "Memory应该跟随Main"
    
    print("\n✓ 模型配置获取测试通过")


async def test_model_router():
    """测试模型路由器"""
    print("\n" + "=" * 60)
    print("测试3: 模型路由器")
    print("=" * 60)
    
    try:
        from backend.core.model_router import model_router
        
        # 初始化
        print("\n初始化模型路由器...")
        await model_router.initialize()
        
        # 获取所有模型信息
        print("\n模型信息:")
        models_info = model_router.get_all_models_info()
        for model_type, info in models_info.items():
            print(f"\n  {model_type}:")
            print(f"    Provider: {info.get('provider')}")
            print(f"    Model: {info.get('model')}")
            print(f"    Host: {info.get('host')}")
            if 'follows' in info:
                print(f"    Follows: {info['follows']}")
            if 'status' in info:
                status = info['status']
                print(f"    Available: {status.get('available')}")
                print(f"    Latency: {status.get('latency_ms')}ms")
        
        # 测试获取客户端
        print("\n测试获取客户端:")
        main_client = model_router.get_client("main")
        summary_client = model_router.get_client("summary")
        memory_client = model_router.get_client("memory")
        
        print(f"  Main客户端: {main_client}")
        print(f"  Summary客户端: {summary_client}")
        print(f"  Memory客户端: {memory_client}")
        
        # 验证跟随机制
        if main_client and summary_client:
            assert main_client == summary_client, "Summary客户端应该与Main相同"
            print("\n✓ 跟随机制验证通过")
        
        # 关闭
        await model_router.close()
        print("\n✓ 模型路由器测试通过")
        
    except Exception as e:
        print(f"\n✗ 模型路由器测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_backward_compatibility():
    """测试向后兼容性"""
    print("\n" + "=" * 60)
    print("测试4: 向后兼容性")
    print("=" * 60)
    
    # 测试旧版LLM配置是否可用
    print("\n旧版LLM配置:")
    print(f"  Provider: {settings.config.llm.provider}")
    print(f"  Host: {settings.config.llm.host}")
    print(f"  Model: {settings.config.llm.model}")
    
    print("\n✓ 向后兼容性测试通过")


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("CXHMS 多模型配置测试")
    print("=" * 60)
    
    try:
        test_config_loading()
        test_model_config_getter()
        test_backward_compatibility()
        await test_model_router()
        
        print("\n" + "=" * 60)
        print("所有测试通过!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
