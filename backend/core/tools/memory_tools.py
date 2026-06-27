"""
记忆系统工具 - 提供记忆管理功能
"""
from typing import Any, Dict, List

from .registry import tool_registry


# 依赖注入（由 app.py 启动时设置）
_MEMORY_MANAGER = None


def set_memory_tools_dependencies(memory_manager=None):
    """设置记忆工具依赖的组件"""
    global _MEMORY_MANAGER
    _MEMORY_MANAGER = memory_manager


def _get_memory_manager():
    """获取记忆管理器"""
    return _MEMORY_MANAGER


def register_memory_tools():
    """注册记忆系统工具"""

    # 保存记忆工具
    tool_registry.register(
        name="save_memory",
        description="保存一条记忆到记忆系统",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "记忆内容，要保存的信息",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["short_term", "long_term", "permanent"],
                    "description": "记忆类型：短期、长期或永久",
                    "default": "long_term",
                },
                "importance": {
                    "type": "integer",
                    "description": "重要性等级（1-5，5为最重要）",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 5,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签列表，用于后续检索",
                    "default": [],
                },
            },
            "required": ["content"],
        },
        function=save_memory,
        category="memory",
        tags=["memory", "save"],
        examples=["记住用户喜欢蓝色", "保存这个重要信息"],
    )


def save_memory(
    content: str = None,
    memory_type: str = "long_term",
    importance: int = 3,
    tags: List[str] = None,
    # 别名参数（兼容模型不同调用方式）
    message: str = None,
    text: str = None,
    tag: str = None,
) -> Dict[str, Any]:
    """保存一条记忆到记忆系统

    Args:
        content: 记忆内容
        memory_type: 记忆类型（short_term/long_term/permanent）
        importance: 重要性等级（1-5）
        tags: 标签列表
        message: content 的别名
        text: content 的别名
        tag: 单个标签（兼容旧调用方式）

    Returns:
        保存结果
    """
    # 参数别名映射
    content = content or message or text
    if tag and not tags:
        tags = [tag]

    if not content:
        return {"success": False, "error": "内容不能为空"}

    mm = _get_memory_manager()
    if not mm:
        return {"success": False, "error": "记忆管理器不可用"}

    try:
        # 根据记忆类型选择写入方法
        if memory_type == "permanent":
            memory_id = mm.write_permanent_memory(
                content=content, tags=tags or [], is_from_main=False
            )
        else:
            memory_id = mm.write_memory(
                content=content,
                memory_type=memory_type,
                importance=importance,
                tags=tags or [],
            )

        return {
            "success": True,
            "status": "success",
            "message": "记忆已保存",
            "memory_id": memory_id,
            "memory_type": memory_type,
            "content_preview": content[:100] + "..." if len(content) > 100 else content,
        }
    except Exception as e:
        return {"success": False, "error": f"保存记忆失败: {str(e)}"}
