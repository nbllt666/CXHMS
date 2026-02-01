import gradio as gr


def create_message_bubble(role: str, content: str, timestamp: str = ""):
    """创建消息气泡组件"""
    if role == "user":
        emoji = "👤"
        bg_color = "#e3f2fd"
        align = "flex-end"
    else:
        emoji = "🤖"
        bg_color = "#f5f5f5"
        align = "flex-start"

    return f"""
    <div style="display: flex; flex-direction: column; align-items: {align}; margin: 8px 0;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span style="font-size: 20px;">{emoji}</span>
            <span style="color: #666; font-size: 12px;">{timestamp}</span>
        </div>
        <div style="background: {bg_color}; padding: 12px 16px; border-radius: 12px; max-width: 80%; word-wrap: break-word;">
            {content}
        </div>
    </div>
    """


def create_typing_indicator():
    """创建打字指示器"""
    return """
    <div style="display: flex; align-items: center; gap: 8px; padding: 8px 0;">
        <span style="font-size: 20px;">🤖</span>
        <div style="display: flex; gap: 4px;">
            <div class="typing-dot" style="width: 8px; height: 8px; background: #999; border-radius: 50%; animation: typing 1.4s infinite;"></div>
            <div class="typing-dot" style="width: 8px; height: 8px; background: #999; border-radius: 50%; animation: typing 1.4s infinite 0.2s;"></div>
            <div class="typing-dot" style="width: 8px; height: 8px; background: #999; border-radius: 50%; animation: typing 1.4s infinite 0.4s;"></div>
        </div>
        <style>
            @keyframes typing {
                0%, 60%, 100% { transform: translateY(0); }
                30% { transform: translateY(-10px); }
            }
        </style>
    </div>
    """


def create_streaming_indicator():
    """创建流式响应指示器"""
    return """
    <div style="display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: #f5f5f5; border-radius: 12px; max-width: 80%;">
        <span style="font-size: 20px;">🤖</span>
        <span style="color: #666;">正在生成</span>
        <div style="display: flex; gap: 3px;">
            <span style="animation: blink 1s infinite;">●</span>
            <span style="animation: blink 1s infinite 0.2s;">●</span>
            <span style="animation: blink 1s infinite 0.4s;">●</span>
        </div>
        <style>
            @keyframes blink {
                0%, 100% { opacity: 0.3; }
                50% { opacity: 1; }
            }
        </style>
    </div>
    """


def create_chat_header(session_id: str = None):
    """创建聊天头部"""
    session_info = f"会话: {session_id[:8] if session_id else '新会话'}" if session_id else "新会话"
    return f"""
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; margin-bottom: 16px;">
        <span style="color: white; font-weight: bold;">💬 AI对话</span>
        <span style="color: white; opacity: 0.9; font-size: 14px;">{session_info}</span>
    </div>
    """


def create_empty_chat():
    """创建空聊天提示"""
    return """
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 300px; color: #999;">
        <span style="font-size: 48px; margin-bottom: 16px;">💬</span>
        <p style="margin: 0;">开始与AI助手对话吧</p>
        <p style="margin: 8px 0 0 0; font-size: 14px;">输入消息并发送</p>
    </div>
    """
