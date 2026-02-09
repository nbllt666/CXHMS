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
