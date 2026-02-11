"""
摘要模型工具 - 供摘要模型（summary）调用的工具
"""
from typing import Dict, Any, Optional, List

from .registry import tool_registry

_MEMORY_MANAGER = None
_MODEL_ROUTER = None


def set_dependencies(memory_manager=None, model_router=None):
    """设置依赖的组件"""
    global _MEMORY_MANAGER, _MODEL_ROUTER
    _MEMORY_MANAGER = memory_manager
    _MODEL_ROUTER = model_router


def get_summary_client():
    """获取摘要模型客户端"""
    if _MODEL_ROUTER:
        client = _MODEL_ROUTER.get_client("summary")
        if client:
            return client
    return None


def register_summary_tools():
    """注册所有摘要模型工具"""

    # 1. summarize_content - 生成摘要
    tool_registry.register(
        name="summarize_content",
        description="使用摘要模型对内容进行摘要，生成简洁的摘要版本。",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要摘要的内容（对话、文本、记忆等）"
                },
                "max_length": {
                    "type": "integer",
                    "description": "摘要最大长度（字符数）",
                    "default": 200,
                    "minimum": 50,
                    "maximum": 1000
                }
            },
            "required": ["content"]
        },
        function=summarize_content,
        category="summary",
        tags=["summary", "summarize", "extract"],
        examples=[
            "摘要这段对话的主要内容",
            "总结这段文字的核心观点",
            "提取这段内容的要点"
        ]
    )

    # 2. save_summary_memory - 保存摘要记忆
    tool_registry.register(
        name="save_summary_memory",
        description="将摘要内容保存为长期记忆。可以保存多条记忆，每条包含内容、重要性(1-10)和时间戳(yyyymmddhhmm格式)。",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "记忆内容，简洁明了地描述要点"
                },
                "importance": {
                    "type": "integer",
                    "description": "重要性等级 (1-10, 10为最重要)",
                    "minimum": 1,
                    "maximum": 10
                },
                "timestamp": {
                    "type": "string",
                    "description": "时间戳，格式为 yyyymmddhhmm，如 202602112235"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签列表（可选）",
                    "default": ["summary"]
                }
            },
            "required": ["content", "importance", "timestamp"]
        },
        function=save_summary_memory,
        category="summary",
        tags=["summary", "memory", "save", "store"],
        examples=[
            "保存这条记忆：用户喜欢喝咖啡，重要性8，时间202602112300",
            "记录：用户明天要开会，重要性9，时间202602111200"
        ]
    )


async def summarize_content(content: str, max_length: int = 200) -> Dict[str, Any]:
    """生成摘要"""
    summary_client = get_summary_client()
    if not summary_client:
        return {"error": "摘要模型不可用"}
    
    try:
        prompt = f"""请对以下内容进行摘要，长度不超过{max_length}字：

{content}

要求：
1. 保留核心信息
2. 语言简洁明了
3. 直接返回摘要文本，不要添加额外说明"""

        response = await summary_client.chat(
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )

        summary = ""
        if hasattr(response, 'content') and response.content:
            summary = response.content.strip()
        elif isinstance(response, dict) and response.get("content"):
            summary = response.get("content").strip()
        else:
            summary = str(response)

        return {
            "status": "success",
            "original_length": len(content),
            "summary_length": len(summary),
            "summary": summary
        }
    except Exception as e:
        return {"error": f"生成摘要失败: {str(e)}"}


async def save_summary_memory(content: str, importance: int, timestamp: str, tags: list = None) -> Dict[str, Any]:
    """保存摘要记忆
    
    Args:
        content: 记忆内容
        importance: 重要性 (1-10, 10为最重要)
        timestamp: 时间戳 (格式: yyyymmddhhmm, 如 202602112235)
        tags: 标签列表 (可选)
    
    Returns:
        保存结果
    """
    if not _MEMORY_MANAGER:
        return {"error": "记忆管理器未初始化"}
    
    try:
        # 验证参数
        if not content or len(content.strip()) == 0:
            return {"error": "记忆内容不能为空"}
        
        if not isinstance(importance, int) or importance < 1 or importance > 10:
            return {"error": "重要性必须是 1-10 之间的整数"}
        
        # 解析时间戳
        from datetime import datetime
        try:
            if len(timestamp) == 12:  # yyyymmddhhmm
                dt = datetime.strptime(timestamp, "%Y%m%d%H%M")
            elif len(timestamp) == 8:  # yyyymmdd
                dt = datetime.strptime(timestamp, "%Y%m%d")
            else:
                return {"error": "时间戳格式错误，应为 yyyymmddhhmm 或 yyyymmdd"}
        except ValueError:
            return {"error": "时间戳格式错误，应为 yyyymmddhhmm 或 yyyymmdd"}
        
        # 将重要性转换为 0-1 范围
        importance_normalized = importance / 10.0
        
        # 保存记忆
        memory_id = await _MEMORY_MANAGER.add_memory(
            content=content,
            memory_type="long_term",
            importance=importance_normalized,
            tags=tags or ["summary"],
            metadata={
                "source": "summary",
                "original_timestamp": timestamp,
                "importance_level": importance
            }
        )
        
        return {
            "status": "success",
            "memory_id": memory_id,
            "content": content,
            "importance": importance,
            "timestamp": timestamp,
            "message": f"记忆已保存 (ID: {memory_id})"
        }
        
    except Exception as e:
        return {"error": f"保存记忆失败: {str(e)}"}
