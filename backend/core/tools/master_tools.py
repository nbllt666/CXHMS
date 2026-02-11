"""
主模型工具 - 供主模型（main）调用的工具
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

from .registry import tool_registry

_MEMORY_MANAGER = None
_SECONDARY_ROUTER = None
_CONTEXT_MANAGER = None


def set_dependencies(memory_manager=None, secondary_router=None, context_manager=None):
    """设置依赖的组件"""
    global _MEMORY_MANAGER, _SECONDARY_ROUTER, _CONTEXT_MANAGER
    _MEMORY_MANAGER = memory_manager
    _SECONDARY_ROUTER = secondary_router
    _CONTEXT_MANAGER = context_manager


def get_memory_manager():
    """获取记忆管理器"""
    return _MEMORY_MANAGER


def get_secondary_router():
    """获取副模型路由器"""
    return _SECONDARY_ROUTER


def get_context_manager():
    """获取上下文管理器"""
    return _CONTEXT_MANAGER


def register_master_tools():
    """注册所有主模型工具"""

    # 1. write_long_term_memory - 写入长期记忆
    tool_registry.register(
        name="write_long_term_memory",
        description="将关键信息写入长期记忆库。这些信息会在后续对话中被检索和使用。",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要记忆的内容（用户的重要信息、偏好、事件等）"
                },
                "importance": {
                    "type": "integer",
                    "enum": [1, 2, 3, 4, 5],
                    "description": "重要性等级（1-5），5为最重要",
                    "default": 3
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签列表，用于后续检索",
                    "default": []
                }
            },
            "required": ["content"]
        },
        function=write_long_term_memory,
        category="memory",
        tags=["memory", "long_term", "save"],
        examples=[
            "记住用户喜欢蓝色",
            "保存这个重要的日期：2024年1月1日",
            "记录用户的工作是程序员"
        ]
    )

    # 2. search_all_memories - 搜索所有记忆
    tool_registry.register(
        name="search_all_memories",
        description="跨所有记忆库进行语义检索，获取与当前话题相关的记忆。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询（描述你想要找的信息）"
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["permanent", "long_term", "all"],
                    "description": "记忆类型筛选（permanent=永久记忆，long_term=长期记忆，all=全部）",
                    "default": "all"
                },
                "time_range": {
                    "type": "string",
                    "description": "时间范围筛选（如 'last_week', 'last_month', 'today'）",
                    "default": None
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量限制",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50
                }
            },
            "required": ["query"]
        },
        function=search_all_memories,
        category="memory",
        tags=["memory", "search", "recall"],
        examples=[
            "用户之前说过喜欢什么颜色？",
            "查找关于工作的记忆",
            "搜索今天的对话内容"
        ]
    )

    # 3. call_assistant - 调用记忆管理模型
    tool_registry.register(
        name="call_assistant",
        description="向记忆管理模型发送指令，获取其专业处理结果。适用于需要记忆管理模型处理的复杂任务。",
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "给记忆管理模型的消息/指令，可以是自然语言描述你想要它做什么"
                }
            },
            "required": ["message"]
        },
        function=call_assistant,
        category="system",
        tags=["assistant", "memory", "task"],
        examples=[
            "帮我总结今天的所有对话",
            "分析这条记忆的重要性",
            "提取这段文字的关键要点"
        ]
    )

    # 4. set_alarm - 设置提醒
    tool_registry.register(
        name="set_alarm",
        description="设置一个定时提醒。在指定秒数后，系统会向用户发送提醒消息。",
        parameters={
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "integer",
                    "description": "多少秒后提醒（最小1秒，最大86400秒即24小时）"
                },
                "message": {
                    "type": "string",
                    "description": "提醒消息内容"
                }
            },
            "required": ["seconds", "message"]
        },
        function=set_alarm,
        category="reminder",
        tags=["alarm", "reminder", "schedule"],
        examples=[
            "5分钟后提醒我喝水",
            "1小时后提醒我开会",
            "设置一个30秒后的测试提醒"
        ]
    )

    # 5. mono - 保持上下文
    tool_registry.register(
        name="mono",
        description="将某些信息保持在接下来的对话上下文中。这对于需要跨多轮记住的信息很有用。",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要保持在上下文中的信息"
                },
                "session_id": {
                    "type": "string",
                    "description": "会话ID（可选，如果不提供则记录到当前对话）"
                },
                "rounds": {
                    "type": "integer",
                    "description": "保持的对话轮数（默认1轮）",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["content"]
        },
        function=mono,
        category="context",
        tags=["context", "mono", "remember"],
        examples=[
            "记住我们现在在讨论项目A",
            "保持这个信息：在接下来的对话中用户叫张三"
        ]
    )


def write_long_term_memory(content: str, importance: int = 3, tags: List[str] = None) -> Dict[str, Any]:
    """写入长期记忆"""
    mm = get_memory_manager()
    if not mm:
        return {"error": "记忆管理器不可用"}
    
    try:
        memory_id = mm.write_memory(
            content=content,
            memory_type="long_term",
            importance=importance,
            tags=tags or []
        )
        return {
            "status": "success",
            "message": f"记忆已保存",
            "memory_id": memory_id,
            "content_preview": content[:100] + "..." if len(content) > 100 else content
        }
    except Exception as e:
        return {"error": f"保存记忆失败: {str(e)}"}


def search_all_memories(
    query: str,
    memory_type: str = "all",
    time_range: str = None,
    limit: int = 10
) -> Dict[str, Any]:
    """搜索所有记忆"""
    mm = get_memory_manager()
    if not mm:
        return {"error": "记忆管理器不可用"}
    
    try:
        memories = mm.search_memories(
            query=query,
            memory_type=memory_type if memory_type != "all" else None,
            time_range=time_range,
            limit=limit
        )
        return {
            "status": "success",
            "query": query,
            "count": len(memories),
            "memories": [
                {
                    "id": m.get("id"),
                    "content": m.get("content", "")[:200],
                    "importance": m.get("importance"),
                    "created_at": m.get("created_at")
                }
                for m in memories
            ]
        }
    except Exception as e:
        return {"error": f"搜索记忆失败: {str(e)}"}


async def call_assistant(message: str) -> Dict[str, Any]:
    """调用记忆管理模型"""
    router = get_secondary_router()
    if not router:
        return {"error": "记忆管理模型不可用"}
    
    try:
        from backend.core.memory.secondary_router import SecondaryInstruction, SecondaryCommand
        
        instruction = SecondaryInstruction(
            command="custom",  # 自定义指令
            parameters={"user_message": message},
            priority=1
        )
        
        result = await router.execute_command(instruction, is_from_main=True)
        
        return {
            "status": result.status,
            "message": message,
            "response": result.output.get("response", "") or str(result.output),
            "execution_time_ms": result.execution_time_ms
        }
    except Exception as e:
        return {"error": f"调用记忆管理模型失败: {str(e)}"}


def set_alarm(seconds: int, message: str) -> Dict[str, Any]:
    """设置提醒"""
    if not (1 <= seconds <= 86400):
        return {"error": "秒数必须在1-86400之间（24小时内）"}
    
    try:
        alarm_id = f"alarm_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return {
            "status": "scheduled",
            "alarm_id": alarm_id,
            "seconds": seconds,
            "message": message,
            "scheduled_time": (datetime.now() + timedelta(seconds=seconds)).isoformat()
        }
    except Exception as e:
        return {"error": f"设置提醒失败: {str(e)}"}


def mono(content: str, session_id: str = None, rounds: int = 1) -> Dict[str, Any]:
    """保持上下文"""
    cm = get_context_manager()
    if not cm:
        return {"error": "上下文管理器不可用"}
    
    # 如果没有提供 session_id，尝试从当前上下文中获取
    if not session_id:
        return {
            "status": "info",
            "message": "内容已记录，将在后续对话中保持",
            "content": content,
            "rounds": rounds
        }
    
    try:
        result = cm.add_mono_context(session_id=session_id, content=content, rounds=rounds)
        return {
            "status": "added" if result else "failed",
            "content": content,
            "rounds": rounds,
            "session_id": session_id
        }
    except Exception as e:
        return {"error": f"添加上下文信息失败: {str(e)}"}
