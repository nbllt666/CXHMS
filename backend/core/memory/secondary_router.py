from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


class SecondaryCommand(Enum):
    """副模型可执行的指令"""
    SUMMARIZE_MEMORY = "summarize_memory"
    ARCHIVE_MEMORY = "archive_memory"
    CLEANUP_MEMORIES = "cleanup_memories"
    ANALYZE_IMPORTANCE = "analyze_importance"
    DECAY_MEMORIES = "decay_memories"
    GET_MEMORY_INSIGHTS = "get_memory_insights"
    BATCH_PROCESS = "batch_process"
    SUMMARIZE_CONVERSATION = "summarize_conversation"
    EXTRACT_KEY_POINTS = "extract_key_points"
    GENERATE_MEMORY_REPORT = "generate_memory_report"


@dataclass
class SecondaryInstruction:
    """副模型指令"""
    command: str
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    parameters: Dict = field(default_factory=dict)
    context: Dict = field(default_factory=dict)
    priority: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SecondaryResult:
    """副模型执行结果"""
    status: str
    command: str
    output: Dict
    execution_time_ms: float
    suggestions: List[str] = field(default_factory=list)


class SecondaryModelRouter:
    """副模型指令路由器"""
    COMMAND_DESCRIPTIONS = {
        SecondaryCommand.SUMMARIZE_MEMORY.value: {
            "description": "将长记忆内容摘要为简洁版本",
            "parameters": {
                "memory_id": {"type": "int", "required": True, "description": "记忆ID"},
                "max_length": {"type": "int", "required": False, "default": 200, "description": "摘要最大长度"}
            },
            "example": {"memory_id": 123, "max_length": 150}
        },
        SecondaryCommand.ARCHIVE_MEMORY.value: {
            "description": "将记忆标记为归档",
            "parameters": {
                "memory_id": {"type": "int", "required": True, "description": "记忆ID"},
                "reason": {"type": "str", "required": False, "description": "归档原因"}
            },
            "example": {"memory_id": 123, "reason": "内容已过时"}
        },
        SecondaryCommand.CLEANUP_MEMORIES.value: {
            "description": "清理低价值或过期的记忆",
            "parameters": {
                "threshold": {"type": "float", "required": False, "default": 0.1, "description": "重要性阈值"},
                "max_count": {"type": "int", "required": False, "default": 100, "description": "最大清理数量"}
            },
            "example": {"threshold": 0.05, "max_count": 50}
        },
        SecondaryCommand.ANALYZE_IMPORTANCE.value: {
            "description": "分析记忆的重要性并给出评分",
            "parameters": {
                "memory_id": {"type": "int", "required": True, "description": "记忆ID"},
                "context": {"type": "str", "required": False, "description": "分析上下文"}
            },
            "example": {"memory_id": 123, "context": "用户多次提及"}
        },
        SecondaryCommand.DECAY_MEMORIES.value: {
            "description": "对所有记忆执行衰减计算",
            "parameters": {
                "dry_run": {"type": "bool", "required": False, "default": True, "description": "仅预览不实际执行"}
            },
            "example": {"dry_run": False}
        },
        SecondaryCommand.GET_MEMORY_INSIGHTS.value: {
            "description": "获取记忆系统的统计和洞察",
            "parameters": {
                "time_range": {"type": "str", "required": False, "description": "时间范围 (7d, 30d, 90d)"},
                "metrics": {"type": "list", "required": False, "description": "需要的指标列表"}
            },
            "example": {"time_range": "30d", "metrics": ["importance_distribution", "decay_rate"]}
        },
        SecondaryCommand.BATCH_PROCESS.value: {
            "description": "批量处理多个记忆",
            "parameters": {
                "action": {"type": "str", "required": True, "description": "操作 (summarize, archive, delete)"},
                "memory_ids": {"type": "list", "required": True, "description": "记忆ID列表"},
                "criteria": {"type": "str", "required": False, "description": "选择标准"}
            },
            "example": {"action": "archive", "memory_ids": [1, 2, 3]}
        },
        SecondaryCommand.SUMMARIZE_CONVERSATION.value: {
            "description": "将对话历史摘要为记忆",
            "parameters": {
                "conversation_id": {"type": "str", "required": True, "description": "对话ID"},
                "max_points": {"type": "int", "required": False, "default": 5, "description": "最大要点数"}
            },
            "example": {"conversation_id": "session_123", "max_points": 5}
        },
        SecondaryCommand.EXTRACT_KEY_POINTS.value: {
            "description": "从文本中提取关键信息点",
            "parameters": {
                "text": {"type": "str", "required": True, "description": "输入文本"},
                "max_points": {"type": "int", "required": False, "default": 5, "description": "最大要点数"}
            },
            "example": {"text": "用户说...", "max_points": 5}
        },
        SecondaryCommand.GENERATE_MEMORY_REPORT.value: {
            "description": "生成记忆系统报告",
            "parameters": {
                "report_type": {"type": "str", "required": False, "default": "summary", "description": "报告类型 (summary, detailed, trends)"},
                "time_range": {"type": "str", "required": False, "description": "时间范围"}
            },
            "example": {"report_type": "trends", "time_range": "30d"}
        }
    }

    PROHIBITED_COMMANDS = [
        "add_permanent_memory",
        "delete_permanent_memory",
        "update_permanent_memory",
        "get_permanent_memories"
    ]

    def __init__(self, memory_manager, llm_client=None):
        self.memory_manager = memory_manager
        self.llm_client = llm_client
        self._execution_history = []

    def set_llm_client(self, llm_client):
        """设置LLM客户端（用于生成摘要、分析等）"""
        self.llm_client = llm_client

    def get_available_commands(self) -> Dict[str, Dict]:
        """获取所有可用命令的描述"""
        return self.COMMAND_DESCRIPTIONS

    def validate_permission(self, command: str, is_from_main: bool = True) -> bool:
        """验证命令权限"""
        if is_from_main:
            return True

        if command in self.PROHIBITED_COMMANDS:
            logger.warning(f"副模型无权执行命令: {command}")
            return False

        return True

    async def execute_command(
        self,
        instruction: SecondaryInstruction,
        is_from_main: bool = True
    ) -> SecondaryResult:
        """执行副模型指令"""
        start_time = datetime.now()

        if not self.validate_permission(instruction.command, is_from_main):
            return SecondaryResult(
                status="error",
                command=instruction.command,
                output={"error": "Permission denied"},
                execution_time_ms=0.0,
                suggestions=["请使用主模型执行此操作"]
            )

        try:
            result = await self._execute_command_impl(instruction)
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            self._execution_history.append({
                "command": instruction.command,
                "status": result.status,
                "execution_time_ms": execution_time,
                "timestamp": datetime.now().isoformat()
            })

            result.execution_time_ms = execution_time
            return result
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"执行命令失败: {instruction.command}, 错误: {e}")

            return SecondaryResult(
                status="error",
                command=instruction.command,
                output={"error": str(e)},
                execution_time_ms=execution_time,
                suggestions=["检查参数是否正确", "查看命令文档"]
            )

    async def _execute_command_impl(self, instruction: SecondaryInstruction) -> SecondaryResult:
        """实现具体的命令执行逻辑"""
        command = instruction.command
        params = instruction.parameters

        if command == SecondaryCommand.SUMMARIZE_MEMORY.value:
            return await self._summarize_memory(params)
        elif command == SecondaryCommand.ARCHIVE_MEMORY.value:
            return await self._archive_memory(params)
        elif command == SecondaryCommand.CLEANUP_MEMORIES.value:
            return await self._cleanup_memories(params)
        elif command == SecondaryCommand.ANALYZE_IMPORTANCE.value:
            return await self._analyze_importance(params)
        elif command == SecondaryCommand.DECAY_MEMORIES.value:
            return await self._decay_memories(params)
        elif command == SecondaryCommand.GET_MEMORY_INSIGHTS.value:
            return await self._get_memory_insights(params)
        elif command == SecondaryCommand.BATCH_PROCESS.value:
            return await self._batch_process(params)
        elif command == SecondaryCommand.SUMMARIZE_CONVERSATION.value:
            return await self._summarize_conversation(params)
        elif command == SecondaryCommand.EXTRACT_KEY_POINTS.value:
            return await self._extract_key_points(params)
        elif command == SecondaryCommand.GENERATE_MEMORY_REPORT.value:
            return await self._generate_memory_report(params)
        else:
            return SecondaryResult(
                status="error",
                command=command,
                output={"error": f"Unknown command: {command}"},
                execution_time_ms=0.0
            )

    async def _summarize_memory(self, params: Dict) -> SecondaryResult:
        """摘要记忆"""
        memory_id = params.get("memory_id")
        max_length = params.get("max_length", 200)

        memory = self.memory_manager.get_memory(memory_id)
        if not memory:
            return SecondaryResult(
                status="error",
                command="summarize_memory",
                output={"error": "Memory not found"},
                execution_time_ms=0.0
            )

        content = memory.get("content", "")
        summary = content[:max_length] + "..." if len(content) > max_length else content

        return SecondaryResult(
            status="success",
            command="summarize_memory",
            output={
                "memory_id": memory_id,
                "original_length": len(content),
                "summary": summary,
                "summary_length": len(summary)
            },
            execution_time_ms=0.0
        )

    async def _archive_memory(self, params: Dict) -> SecondaryResult:
        """归档记忆"""
        memory_id = params.get("memory_id")
        reason = params.get("reason", "")

        success = self.memory_manager.update_memory(
            memory_id=memory_id,
            new_metadata={"archived": True, "archive_reason": reason}
        )

        if success:
            return SecondaryResult(
                status="success",
                command="archive_memory",
                output={"memory_id": memory_id, "archived": True},
                execution_time_ms=0.0
            )
        else:
            return SecondaryResult(
                status="error",
                command="archive_memory",
                output={"error": "Failed to archive memory"},
                execution_time_ms=0.0
            )

    async def _cleanup_memories(self, params: Dict) -> SecondaryResult:
        """清理低价值记忆"""
        threshold = params.get("threshold", 0.1)
        max_count = params.get("max_count", 100)

        memories = self.memory_manager.search_memories(limit=max_count)
        low_value_ids = [
            m["id"] for m in memories
            if m.get("importance_score", 0.0) < threshold
        ]

        result = self.memory_manager.batch_delete_memories(
            memory_ids=low_value_ids,
            soft_delete=True
        )

        return SecondaryResult(
            status="success",
            command="cleanup_memories",
            output={
                "threshold": threshold,
                "deleted_count": result["success"],
                "failed_count": result["failed"]
            },
            execution_time_ms=0.0
        )

    async def _analyze_importance(self, params: Dict) -> SecondaryResult:
        """分析记忆重要性"""
        memory_id = params.get("memory_id")
        context = params.get("context", "")

        memory = self.memory_manager.get_memory(memory_id)
        if not memory:
            return SecondaryResult(
                status="error",
                command="analyze_importance",
                output={"error": "Memory not found"},
                execution_time_ms=0.0
            )

        current_importance = memory.get("importance_score", 0.0)
        current_importance_level = memory.get("importance", 3)

        analysis = {
            "memory_id": memory_id,
            "current_importance": current_importance,
            "importance_level": current_importance_level,
            "context": context,
            "suggested_importance": current_importance,
            "reason": "基于当前重要性分数"
        }

        return SecondaryResult(
            status="success",
            command="analyze_importance",
            output=analysis,
            execution_time_ms=0.0
        )

    async def _decay_memories(self, params: Dict) -> SecondaryResult:
        """执行衰减计算"""
        dry_run = params.get("dry_run", True)

        if dry_run:
            stats = self.memory_manager.get_decay_statistics()
            return SecondaryResult(
                status="success",
                command="decay_memories",
                output={
                    "dry_run": True,
                    "statistics": stats,
                    "message": "预览模式，未实际更新"
                },
                execution_time_ms=0.0
            )
        else:
            result = self.memory_manager.sync_decay_values()
            return SecondaryResult(
                status="success",
                command="decay_memories",
                output={
                    "dry_run": False,
                    "updated": result["updated"],
                    "failed": result["failed"],
                    "total": result["total"]
                },
                execution_time_ms=0.0
            )

    async def _get_memory_insights(self, params: Dict) -> SecondaryResult:
        """获取记忆洞察"""
        time_range = params.get("time_range", "30d")
        metrics = params.get("metrics", [])

        stats = self.memory_manager.get_decay_statistics()
        basic_stats = self.memory_manager.get_statistics()

        insights = {
            "time_range": time_range,
            "basic_statistics": basic_stats,
            "decay_statistics": stats
        }

        if "importance_distribution" in metrics:
            insights["importance_distribution"] = stats.get("importance_distribution", {})
        if "reactivation_stats" in metrics:
            insights["reactivation_stats"] = stats.get("reactivation_stats", {})

        return SecondaryResult(
            status="success",
            command="get_memory_insights",
            output=insights,
            execution_time_ms=0.0
        )

    async def _batch_process(self, params: Dict) -> SecondaryResult:
        """批量处理记忆"""
        action = params.get("action")
        memory_ids = params.get("memory_ids", [])

        if action == "delete":
            result = self.memory_manager.batch_delete_memories(
                memory_ids=memory_ids,
                soft_delete=True
            )
            return SecondaryResult(
                status="success",
                command="batch_process",
                output={
                    "action": action,
                    "deleted_count": result["success"],
                    "failed_count": result["failed"]
                },
                execution_time_ms=0.0
            )
        else:
            return SecondaryResult(
                status="error",
                command="batch_process",
                output={"error": f"Unsupported action: {action}"},
                execution_time_ms=0.0
            )

    async def _summarize_conversation(self, params: Dict) -> SecondaryResult:
        """摘要对话"""
        conversation_id = params.get("conversation_id")
        max_points = params.get("max_points", 5)

        return SecondaryResult(
            status="success",
            command="summarize_conversation",
            output={
                "conversation_id": conversation_id,
                "summary": f"对话摘要（最多{max_points}个要点）",
                "points": []
            },
            execution_time_ms=0.0
        )

    async def _extract_key_points(self, params: Dict) -> SecondaryResult:
        """提取关键点"""
        text = params.get("text", "")
        max_points = params.get("max_points", 5)

        sentences = text.split("。")
        key_points = [s.strip() for s in sentences[:max_points] if s.strip()]

        return SecondaryResult(
            status="success",
            command="extract_key_points",
            output={
                "text_length": len(text),
                "key_points": key_points,
                "point_count": len(key_points)
            },
            execution_time_ms=0.0
        )

    async def _generate_memory_report(self, params: Dict) -> SecondaryResult:
        """生成记忆报告"""
        report_type = params.get("report_type", "summary")
        time_range = params.get("time_range", "30d")

        stats = self.memory_manager.get_decay_statistics()
        basic_stats = self.memory_manager.get_statistics()

        report = {
            "report_type": report_type,
            "time_range": time_range,
            "generated_at": datetime.now().isoformat(),
            "statistics": {
                "total_memories": basic_stats.get("total", 0),
                "by_type": basic_stats.get("by_type", {}),
                "decay_stats": stats
            }
        }

        return SecondaryResult(
            status="success",
            command="generate_memory_report",
            output=report,
            execution_time_ms=0.0
        )

    def get_execution_history(self, limit: int = 10) -> List[Dict]:
        """获取执行历史"""
        return self._execution_history[-limit:]
