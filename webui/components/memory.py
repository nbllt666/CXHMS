import gradio as gr


def create_memory_card(
    memory_id: int,
    content: str,
    memory_type: str,
    importance: int,
    tags: list,
    created_at: str
):
    """创建记忆卡片组件"""

    type_colors = {
        "permanent": "#4caf50",
        "long_term": "#2196f3",
        "short_term": "#ff9800"
    }

    type_labels = {
        "permanent": "永久",
        "long_term": "长期",
        "short_term": "短期"
    }

    color = type_colors.get(memory_type, "#999")
    label = type_labels.get(memory_type, memory_type)

    stars = "⭐" * importance

    tags_html = ""
    if tags:
        tags_html = '<div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px;">'
        for tag in tags[:5]:
            tags_html += f'<span style="background: #e0e0e0; padding: 2px 8px; border-radius: 12px; font-size: 12px;">{tag}</span>'
        tags_html += '</div>'

    return f"""
    <div style="border: 1px solid #e0e0e0; border-radius: 12px; padding: 16px; margin: 8px 0; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="background: {color}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px;">{label}</span>
                <span style="color: #666; font-size: 12px;">{created_at[:10]}</span>
            </div>
            <span style="color: #ffc107;">{stars}</span>
        </div>
        <p style="margin: 0; color: #333; line-height: 1.6;">{content[:200]}{'...' if len(content) > 200 else ''}</p>
        {tags_html}
    </div>
    """


def create_memory_list(memories: list):
    """创建记忆列表"""
    if not memories:
        return """
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #999;">
            <span style="font-size: 48px; margin-bottom: 16px;">🧠</span>
            <p style="margin: 0;">暂无记忆</p>
            <p style="margin: 8px 0 0 0; font-size: 14px;">添加第一个记忆吧</p>
        </div>
        """

    html = ""
    for m in memories:
        html += create_memory_card(
            memory_id=m.get("id", 0),
            content=m.get("content", ""),
            memory_type=m.get("type", "short_term"),
            importance=m.get("importance", 3),
            tags=m.get("tags", []),
            created_at=m.get("created_at", "")
        )

    return html


def create_memory_stats(total: int, permanent: int, long_term: int, short_term: int):
    """创建记忆统计"""
    return f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px;">
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{total}</div>
            <div style="font-size: 12px; opacity: 0.9;">总记忆</div>
        </div>
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{permanent}</div>
            <div style="font-size: 12px; opacity: 0.9;">永久</div>
        </div>
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{long_term}</div>
            <div style="font-size: 12px; opacity: 0.9;">长期</div>
        </div>
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{short_term}</div>
            <div style="font-size: 12px; opacity: 0.9;">短期</div>
        </div>
    </div>
    """


def create_empty_memory():
    """创建空记忆提示"""
    return """
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #999;">
        <span style="font-size: 48px; margin-bottom: 16px;">🧠</span>
        <p style="margin: 0;">未找到相关记忆</p>
        <p style="margin: 8px 0 0 0; font-size: 14px;">尝试其他关键词</p>
    </div>
    """
