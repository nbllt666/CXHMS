"""
任务辅助工具 - 供记忆管理模型（assistant）调用的任务清单 + 定时提醒工具
参照 backend/core/tools/assistant_tools.py 的实现模式
"""

from typing import Any, Dict

from .registry import tool_registry

# 与 alarm 保持一致的 agent_id
_TASK_AGENT_ID = "cxhms_agent_001"

_TASK_MANAGER = None
_ALARM_MANAGER = None


def set_task_tools_dependencies(task_manager=None, alarm_manager=None):
    """设置依赖的组件"""
    global _TASK_MANAGER, _ALARM_MANAGER
    _TASK_MANAGER = task_manager
    _ALARM_MANAGER = alarm_manager


def get_task_manager():
    """获取任务管理器"""
    return _TASK_MANAGER


def get_alarm_manager():
    """获取提醒管理器"""
    return _ALARM_MANAGER


# ============================================================
# 任务工具函数
# ============================================================


def create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: str = None,
) -> Dict[str, Any]:
    """创建任务"""
    tm = get_task_manager()
    if not tm:
        return {"error": "任务管理器不可用"}

    try:
        task_id = tm.create_task(
            agent_id=_TASK_AGENT_ID,
            title=title,
            description=description,
            priority=priority,
            due_date=due_date,
        )
        return {
            "success": True,
            "task_id": task_id,
            "title": title,
            "priority": priority,
            "status": "pending",
            "due_date": due_date,
        }
    except Exception as e:
        return {"success": False, "error": f"创建任务失败: {str(e)}"}


def list_tasks(status: str = None, priority: str = None) -> Dict[str, Any]:
    """列出任务"""
    tm = get_task_manager()
    if not tm:
        return {"error": "任务管理器不可用"}

    try:
        tasks = tm.list_tasks(
            agent_id=_TASK_AGENT_ID, status=status, priority=priority
        )
        return {
            "success": True,
            "count": len(tasks),
            "filters": {"status": status, "priority": priority},
            "tasks": tasks,
        }
    except Exception as e:
        return {"success": False, "error": f"列出任务失败: {str(e)}"}


def update_task(
    task_id: str,
    title: str = None,
    description: str = None,
    priority: str = None,
    status: str = None,
    due_date: str = None,
) -> Dict[str, Any]:
    """更新任务"""
    tm = get_task_manager()
    if not tm:
        return {"error": "任务管理器不可用"}

    try:
        existing = tm.get_task(task_id)
        if not existing:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        success = tm.update_task(
            task_id=task_id,
            title=title,
            description=description,
            priority=priority,
            status=status,
            due_date=due_date,
        )
        if not success:
            return {"success": False, "error": "没有需要更新的字段"}

        updated = tm.get_task(task_id)
        return {
            "success": True,
            "task_id": task_id,
            "task": updated,
        }
    except Exception as e:
        return {"success": False, "error": f"更新任务失败: {str(e)}"}


def complete_task(task_id: str) -> Dict[str, Any]:
    """完成任务"""
    tm = get_task_manager()
    if not tm:
        return {"error": "任务管理器不可用"}

    try:
        existing = tm.get_task(task_id)
        if not existing:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        success = tm.complete_task(task_id=task_id)
        if not success:
            return {"success": False, "error": "完成任务失败"}

        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
        }
    except Exception as e:
        return {"success": False, "error": f"完成任务失败: {str(e)}"}


def delete_task(task_id: str) -> Dict[str, Any]:
    """删除任务"""
    tm = get_task_manager()
    if not tm:
        return {"error": "任务管理器不可用"}

    try:
        existing = tm.get_task(task_id)
        if not existing:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        success = tm.delete_task(task_id=task_id)
        if not success:
            return {"success": False, "error": "删除任务失败"}

        return {
            "success": True,
            "task_id": task_id,
            "deleted": True,
        }
    except Exception as e:
        return {"success": False, "error": f"删除任务失败: {str(e)}"}


# ============================================================
# 提醒工具函数（复用 AlarmManager）
# ============================================================


def create_reminder(message: str, delay_seconds: int = 60) -> Dict[str, Any]:
    """创建定时提醒"""
    am = get_alarm_manager()
    if not am:
        return {"error": "提醒管理器不可用"}

    try:
        alarm_id = am.create_alarm(
            agent_id=_TASK_AGENT_ID,
            seconds=delay_seconds,
            message=message,
        )
        return {
            "success": True,
            "alarm_id": alarm_id,
            "message": message,
            "delay_seconds": delay_seconds,
        }
    except Exception as e:
        return {"success": False, "error": f"创建提醒失败: {str(e)}"}


def list_reminders(include_triggered: bool = False) -> Dict[str, Any]:
    """列出提醒"""
    am = get_alarm_manager()
    if not am:
        return {"error": "提醒管理器不可用"}

    try:
        alarms = am.get_alarms_by_agent(
            agent_id=_TASK_AGENT_ID, include_triggered=include_triggered
        )
        return {
            "success": True,
            "count": len(alarms),
            "include_triggered": include_triggered,
            "reminders": alarms,
        }
    except Exception as e:
        return {"success": False, "error": f"列出提醒失败: {str(e)}"}


def cancel_reminder(alarm_id: str) -> Dict[str, Any]:
    """取消提醒"""
    am = get_alarm_manager()
    if not am:
        return {"error": "提醒管理器不可用"}

    try:
        success = am.cancel_alarm(alarm_id=alarm_id)
        if not success:
            return {
                "success": False,
                "error": "取消提醒失败（可能不存在或已触发）",
                "alarm_id": alarm_id,
            }
        return {
            "success": True,
            "alarm_id": alarm_id,
            "cancelled": True,
        }
    except Exception as e:
        return {"success": False, "error": f"取消提醒失败: {str(e)}"}


# ============================================================
# 注册函数
# ============================================================


def register_task_tools():
    """注册所有任务辅助工具（任务清单 + 定时提醒）"""

    # 1. create_task - 创建任务
    tool_registry.register(
        name="create_task",
        description="创建一个新的任务（待办事项），可指定优先级和截止时间。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "任务标题"},
                "description": {"type": "string", "description": "任务详细描述"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "优先级：low/medium/high/urgent",
                    "default": "medium",
                },
                "due_date": {
                    "type": "string",
                    "description": "截止时间（ISO 格式字符串，如 2026-12-31T23:59:59）",
                },
            },
            "required": ["title"],
        },
        function=create_task,
        category="assistant",
        tags=["task", "create", "todo"],
        examples=["创建一个高优先级任务：完成项目报告", "添加待办事项：明天回复客户邮件"],
    )

    # 2. list_tasks - 列出任务
    tool_registry.register(
        name="list_tasks",
        description="列出当前所有任务，可按状态或优先级过滤。",
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                    "description": "按状态过滤",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "按优先级过滤",
                },
            },
        },
        function=list_tasks,
        category="assistant",
        tags=["task", "list", "todo"],
        examples=["列出所有待办任务", "查看高优先级任务", "查看已完成的任务"],
    )

    # 3. update_task - 更新任务
    tool_registry.register(
        name="update_task",
        description="更新指定任务的内容、优先级、状态或截止时间。",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "要更新的任务ID"},
                "title": {"type": "string", "description": "新的任务标题"},
                "description": {"type": "string", "description": "新的任务描述"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "新的优先级",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                    "description": "新的状态",
                },
                "due_date": {
                    "type": "string",
                    "description": "新的截止时间（ISO 格式字符串）",
                },
            },
            "required": ["task_id"],
        },
        function=update_task,
        category="assistant",
        tags=["task", "update", "edit", "todo"],
        examples=["将任务ID为xxx的任务标记为进行中", "更新任务的截止时间"],
    )

    # 4. complete_task - 完成任务
    tool_registry.register(
        name="complete_task",
        description="将指定任务标记为已完成。",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "要完成的任务ID"}
            },
            "required": ["task_id"],
        },
        function=complete_task,
        category="assistant",
        tags=["task", "complete", "done", "todo"],
        examples=["完成任务ID为xxx的任务", "标记待办事项为已完成"],
    )

    # 5. delete_task - 删除任务
    tool_registry.register(
        name="delete_task",
        description="物理删除指定任务（不可恢复，请谨慎使用）。",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "要删除的任务ID"}
            },
            "required": ["task_id"],
        },
        function=delete_task,
        category="assistant",
        tags=["task", "delete", "remove", "todo"],
        examples=["删除任务ID为xxx的任务", "移除已取消的待办事项"],
    )

    # 6. create_reminder - 创建提醒
    tool_registry.register(
        name="create_reminder",
        description="创建一个定时提醒，经过指定秒数后触发。",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "提醒消息内容"},
                "delay_seconds": {
                    "type": "integer",
                    "description": "延迟触发的秒数（默认60秒）",
                    "default": 60,
                    "minimum": 1,
                },
            },
            "required": ["message"],
        },
        function=create_reminder,
        category="assistant",
        tags=["reminder", "alarm", "create", "timer"],
        examples=["5分钟后提醒我开会（delay_seconds=300）", "1小时后提醒我喝水"],
    )

    # 7. list_reminders - 列出提醒
    tool_registry.register(
        name="list_reminders",
        description="列出当前的所有提醒，可选择是否包含已触发的提醒。",
        parameters={
            "type": "object",
            "properties": {
                "include_triggered": {
                    "type": "boolean",
                    "description": "是否包含已触发的提醒（默认 false，仅返回待触发的）",
                    "default": False,
                },
            },
        },
        function=list_reminders,
        category="assistant",
        tags=["reminder", "alarm", "list"],
        examples=["列出所有待触发的提醒", "查看所有提醒（包含已触发）"],
    )

    # 8. cancel_reminder - 取消提醒
    tool_registry.register(
        name="cancel_reminder",
        description="取消指定的定时提醒。",
        parameters={
            "type": "object",
            "properties": {
                "alarm_id": {"type": "string", "description": "要取消的提醒ID"}
            },
            "required": ["alarm_id"],
        },
        function=cancel_reminder,
        category="assistant",
        tags=["reminder", "alarm", "cancel"],
        examples=["取消提醒ID为xxx的提醒"],
    )
