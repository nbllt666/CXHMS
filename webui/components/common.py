import gradio as gr


def create_loading_spinner(text: str = "加载中..."):
    """创建加载动画"""
    return f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px;">
        <div style="width: 40px; height: 40px; border: 3px solid #f3f3f3; border-top: 3px solid #667eea; border-radius: 50%; animation: spin 1s linear infinite;"></div>
        <p style="margin: 16px 0 0 0; color: #666;">{text}</p>
        <style>
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
        </style>
    </div>
    """


def create_loading_bar(progress: float = 0, text: str = ""):
    """创建进度条"""
    percentage = min(100, max(0, progress * 100))
    return f"""
    <div style="width: 100%; padding: 16px;">
        <div style="background: #e0e0e0; border-radius: 8px; height: 8px; overflow: hidden;">
            <div style="width: {percentage}%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100%; transition: width 0.3s ease;"></div>
        </div>
        {f'<p style="margin: 8px 0 0 0; color: #666; font-size: 14px; text-align: center;">{text}</p>' if text else ''}
    </div>
    """


def create_confirm_dialog(title: str, message: str, confirm_text: str = "确认", cancel_text: str = "取消"):
    """创建确认对话框"""
    return f"""
    <div style="padding: 24px; background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);">
        <h3 style="margin: 0 0 16px 0; color: #333;">{title}</h3>
        <p style="margin: 0 0 24px 0; color: #666;">{message}</p>
        <div style="display: flex; gap: 12px; justify-content: flex-end;">
            <button style="padding: 8px 24px; border: none; border-radius: 8px; background: #e0e0e0; color: #333; cursor: pointer;">{cancel_text}</button>
            <button style="padding: 8px 24px; border: none; border-radius: 8px; background: #667eea; color: white; cursor: pointer;">{confirm_text}</button>
        </div>
    </div>
    """


def create_toast(message: str, toast_type: str = "info"):
    """创建提示消息"""

    type_styles = {
        "success": ("✅", "#4caf50"),
        "error": ("❌", "#f44336"),
        "warning": ("⚠️", "#ff9800"),
        "info": ("ℹ️", "#2196f3")
    }

    icon, color = type_styles.get(toast_type, type_styles["info"])

    return f"""
    <div style="display: flex; align-items: center; gap: 12px; padding: 12px 20px; background: {color}; color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
        <span style="font-size: 20px;">{icon}</span>
        <span>{message}</span>
    </div>
    """


def create_stats_card(title: str, value: str, icon: str = "📊", color: str = "#667eea"):
    """创建统计卡片"""
    return f"""
    <div style="padding: 20px; background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center;">
        <div style="font-size: 32px; margin-bottom: 8px;">{icon}</div>
        <div style="font-size: 28px; font-weight: bold; color: {color};">{value}</div>
        <div style="color: #666; font-size: 14px; margin-top: 4px;">{title}</div>
    </div>
    """


def create_status_badge(status: str, status_type: str = "status"):
    """创建状态徽章"""

    status_config = {
        "healthy": ("🟢", "#4caf50"),
        "online": ("🟢", "#4caf50"),
        "success": ("✅", "#4caf50"),
        "degraded": ("🟡", "#ff9800"),
        "busy": ("🟡", "#ff9800"),
        "warning": ("⚠️", "#ff9800"),
        "unhealthy": ("🔴", "#f44336"),
        "offline": ("🔴", "#f44336"),
        "error": ("❌", "#f44336"),
        "unknown": ("⚪", "#9e9e9e")
    }

    icon, color = status_config.get(status.lower(), status_config["unknown"])

    return f"""
    <span style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; background: {color}; color: white; border-radius: 12px; font-size: 12px;">
        {icon} {status}
    </span>
    """


def create_page_header(title: str, description: str = "", icon: str = "📄"):
    """创建页面标题"""
    return f"""
    <div style="margin-bottom: 24px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <span style="font-size: 32px;">{icon}</span>
            <h1 style="margin: 0; color: #333; font-size: 24px;">{title}</h1>
        </div>
        {f'<p style="margin: 0; color: #666;">{description}</p>' if description else ''}
    </div>
    """


def create_divider(text: str = ""):
    """创建分割线"""
    if text:
        return f"""
        <div style="display: flex; align-items: center; gap: 16px; margin: 24px 0;">
            <div style="flex: 1; height: 1px; background: #e0e0e0;"></div>
            <span style="color: #999; font-size: 14px;">{text}</span>
            <div style="flex: 1; height: 1px; background: #e0e0e0;"></div>
        </div>
        """
    return '<div style="height: 1px; background: #e0e0e0; margin: 24px 0;"></div>'


def create_empty_state(icon: str, title: str, message: str, action_text: str = ""):
    """创建空状态"""
    return f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; text-align: center;">
        <span style="font-size: 64px; margin-bottom: 24px;">{icon}</span>
        <h3 style="margin: 0 0 8px 0; color: #333;">{title}</h3>
        <p style="margin: 0 0 24px 0; color: #666;">{message}</p>
        {f'<button style="padding: 10px 24px; border: none; border-radius: 8px; background: #667eea; color: white; cursor: pointer; font-size: 14px;">{action_text}</button>' if action_text else ''}
    </div>
    """
