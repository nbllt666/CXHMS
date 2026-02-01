import gradio as gr


def create_agent_card(name: str, host: str, port: int, status: str, version: str = "1.0.0"):
    """创建Agent卡片"""

    status_colors = {
        "online": "#4caf50",
        "offline": "#9e9e9e",
        "busy": "#ff9800"
    }

    status_labels = {
        "online": "在线",
        "offline": "离线",
        "busy": "忙碌"
    }

    color = status_colors.get(status, "#9e9e9e")
    label = status_labels.get(status, status)

    return f"""
    <div style="border: 1px solid #e0e0e0; border-radius: 12px; padding: 16px; margin: 8px 0; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 32px;">🤖</span>
                <div>
                    <div style="font-weight: bold; font-size: 16px;">{name}</div>
                    <div style="color: #666; font-size: 12px;">v{version}</div>
                </div>
            </div>
            <span style="background: {color}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px;">{label}</span>
        </div>
        <div style="display: flex; gap: 16px; color: #666; font-size: 14px;">
            <span>📍 {host}:{port}</span>
        </div>
    </div>
    """


def create_connection_card(name: str, status: str, host: str, port: int, messages_sent: int = 0, messages_received: int = 0):
    """创建连接卡片"""

    status_colors = {
        "connected": "#4caf50",
        "connecting": "#ff9800",
        "disconnected": "#9e9e9e"
    }

    color = status_colors.get(status, "#9e9e9e")

    return f"""
    <div style="border: 1px solid #e0e0e0; border-radius: 12px; padding: 16px; margin: 8px 0; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 32px;">🔗</span>
                <div>
                    <div style="font-weight: bold; font-size: 16px;">{name}</div>
                    <div style="color: #666; font-size: 12px;">{host}:{port}</div>
                </div>
            </div>
            <span style="background: {color}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px;">{status}</span>
        </div>
        <div style="display: flex; gap: 16px; color: #666; font-size: 12px;">
            <span>📤 {messages_sent} 消息</span>
            <span>📥 {messages_received} 消息</span>
        </div>
    </div>
    """


def create_group_card(name: str, member_count: int, max_members: int, creator: str, description: str = ""):
    """创建群组卡片"""

    return f"""
    <div style="border: 1px solid #e0e0e0; border-radius: 12px; padding: 16px; margin: 8px 0; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 32px;">👥</span>
                <div>
                    <div style="font-weight: bold; font-size: 16px;">{name}</div>
                    <div style="color: #666; font-size: 12px;">创建者: {creator}</div>
                </div>
            </div>
            <span style="background: #2196f3; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px;">{member_count}/{max_members}</span>
        </div>
        {f'<p style="margin: 0; color: #666; font-size: 14px;">{description}</p>' if description else ''}
    </div>
    """


def create_message_item(from_agent: str, content: dict, timestamp: str, msg_type: str = "chat"):
    """创建消息项"""

    type_icons = {
        "chat": "💬",
        "control": "⚙️",
        "broadcast": "📢",
        "group_message": "👥"
    }

    icon = type_icons.get(msg_type, "💬")

    return f"""
    <div style="border-bottom: 1px solid #f0f0f0; padding: 12px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span>{icon}</span>
                <span style="font-weight: bold;">{from_agent}</span>
            </div>
            <span style="color: #999; font-size: 12px;">{timestamp[:16]}</span>
        </div>
        <p style="margin: 0; color: #666; font-size: 14px;">{str(content)[:100]}{'...' if len(str(content)) > 100 else ''}</p>
    </div>
    """


def create_acp_stats(agents: int, online: int, groups: int, messages: int):
    """创建ACP统计"""
    return f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px;">
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{agents}</div>
            <div style="font-size: 12px; opacity: 0.9;">🤖 Agents</div>
        </div>
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{online}</div>
            <div style="font-size: 12px; opacity: 0.9;">🟢 在线</div>
        </div>
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{groups}</div>
            <div style="font-size: 12px; opacity: 0.9;">👥 群组</div>
        </div>
        <div style="text-align: center; color: white;">
            <div style="font-size: 24px; font-weight: bold;">{messages}</div>
            <div style="font-size: 12px; opacity: 0.9;">💬 消息</div>
        </div>
    </div>
    """


def create_empty_agents():
    """创建空Agent提示"""
    return """
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #999;">
        <span style="font-size: 48px; margin-bottom: 16px;">🔍</span>
        <p style="margin: 0;">未发现Agents</p>
        <p style="margin: 8px 0 0 0; font-size: 14px;">点击"扫描网络"开始发现</p>
    </div>
    """
