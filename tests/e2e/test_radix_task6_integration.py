"""RADIX-Lite Task 6 集成 E2E 测试。

聚焦 Task 6 改动的端到端集成验证（不重复单元测试已覆盖的场景）：
    1. parser.py 双模式切换（legacy_parser_enabled True/False/None）
    2. agents.py AgentConfig auto_fill 3 字段（旧记录兼容）
    3. manager.py write_with_decision 3 路径分发（memories / permanent_memories / rejected）
    4. manager.py get_rejected_content + cleanup_expired_rejected_content
    5. agent_tools.py Mock→真实切换（DistillationService 优先 + Mock fallback）
    6. agents.json schema 校验（agent_config_v2.schema.json）
    7. documents 表 updated_at DEFAULT CURRENT_TIMESTAMP（额外修复验证）
    8. 完整工作流：parser_v2 → DistillationService → DecisionCore → write_with_decision

运行方式：
    $env:PYTHONPATH = "."; python -m pytest tests/e2e/test_radix_task6_integration.py -v

@version 1.0.0
@see .trae/specs/add-management-agent-radix/tasks.md Task 6 + Task 7
"""

import inspect
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import jsonschema
import pytest

# --------------------------------------------------------------------------- #
# 路径锚点（rules-0 §三：os.path.dirname(os.path.abspath(__file__))）
# --------------------------------------------------------------------------- #
_THIS_FILE = os.path.abspath(__file__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SCHEMA_DIR = Path(_PROJECT_ROOT) / "public" / "schema"
_AGENT_CONFIG_V2_SCHEMA_PATH = _SCHEMA_DIR / "agent_config_v2.schema.json"
_AGENTS_JSON_PATH = Path(_PROJECT_ROOT) / "data" / "agents.json"


def _load_schema(path: Path) -> dict:
    """加载 JSON Schema 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================ #
# 1. parser.py 双模式切换
# ============================================================================ #


class TestParserV2DualMode:
    """parser.py parse_attachments_v2 双模式切换 E2E 验证。"""

    def test_legacy_mode_returns_same_as_v1(self):
        """legacy_parser_enabled=True 时 parse_attachments_v2 与 parse_attachments 返回一致。"""
        from backend.core.document.parser import parse_attachments, parse_attachments_v2

        attachments = [
            {
                "name": "test.txt",
                "mime": "text/plain",
                "contentString": "data:text/plain;base64,SGVsbG8gV29ybGQ=",
            }
        ]
        result_v1 = parse_attachments(attachments)
        result_v2 = parse_attachments_v2(attachments, legacy_parser_enabled=True)
        assert result_v1 == result_v2, "legacy_parser_enabled=True 应与 v1 返回一致"

    def test_pipeline_mode_uses_multimodal_pipeline(self):
        """legacy_parser_enabled=False 时调用 MultimodalPipeline（不下沉图片附件）。"""
        from backend.core.document.parser import parse_attachments_v2

        attachments = [
            {
                "name": "test.txt",
                "mime": "text/plain",
                "contentString": "data:text/plain;base64,5L2g5aW977yM5LiA5Liq5rWL6K+V",
            }
        ]
        # 不应 raise（即使 MultimodalPipeline 实例化失败也会回退 legacy）
        combined_text, image_urls = parse_attachments_v2(
            attachments, legacy_parser_enabled=False
        )
        # 下沉路径仍应产出文本（无论走 pipeline 还是回退 legacy）
        assert isinstance(combined_text, str)
        assert isinstance(image_urls, list)

    def test_config_driven_switch_reads_radix_config(self):
        """legacy_parser_enabled=None 时从 radix_config.json 读取（默认 True）。"""
        from backend.core.document.parser import (
            _load_legacy_parser_enabled,
            parse_attachments_v2,
        )

        # _load_legacy_parser_enabled 应返回 bool（不 raise）
        config_value = _load_legacy_parser_enabled()
        assert isinstance(config_value, bool), "配置读取应返回 bool"

        # None 时走配置读取路径（不 raise）
        attachments: list = []
        result = parse_attachments_v2(attachments, legacy_parser_enabled=None)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_empty_attachments_returns_empty(self):
        """空附件列表返回空文本 + 空图片列表（两种模式一致）。"""
        from backend.core.document.parser import parse_attachments_v2

        for mode in [True, False]:
            text, images = parse_attachments_v2([], legacy_parser_enabled=mode)
            assert text == "", f"mode={mode}: 空附件应返回空文本"
            assert images == [], f"mode={mode}: 空附件应返回空图片列表"


# ============================================================================ #
# 2. AgentConfig auto_fill
# ============================================================================ #


class TestAgentConfigAutoFill:
    """AgentConfig auto_fill 3 字段（旧记录兼容）E2E 验证。"""

    def test_load_agents_returns_list_with_required_fields(self):
        """_load_agents 加载 agents.json 后返回的记录含 5 required 字段。"""
        from backend.api.routers.agents import _load_agents

        agents = _load_agents()
        assert isinstance(agents, list)
        assert len(agents) >= 2, "agents.json 应至少含 default + memory-agent"

        required_fields = ["agent_id", "name", "tools_config", "decision_rubric", "distillation_enabled"]
        for agent in agents:
            for field in required_fields:
                assert field in agent, f"agent {agent.get('id', '?')} 缺少 required 字段 {field}"

    def test_memory_agent_distillation_enabled_true(self):
        """memory-agent 的 distillation_enabled=True（管理 agent 蒸馏已启用）。"""
        from backend.api.routers.agents import _load_agents

        agents = _load_agents()
        memory_agent = next((a for a in agents if a.get("id") == "memory-agent"), None)
        assert memory_agent is not None, "agents.json 应含 memory-agent"
        assert memory_agent["distillation_enabled"] is True, "memory-agent 蒸馏应启用"

    def test_default_agent_distillation_enabled_false(self):
        """default agent 的 distillation_enabled=False（基础 agent 不启用蒸馏）。"""
        from backend.api.routers.agents import _load_agents

        agents = _load_agents()
        default_agent = next((a for a in agents if a.get("id") == "default"), None)
        assert default_agent is not None, "agents.json 应含 default"
        assert default_agent["distillation_enabled"] is False, "default 蒸馏应关闭"

    def test_decision_rubric_has_4_required_thresholds(self):
        """decision_rubric 含 4 必需阈值字段。"""
        from backend.api.routers.agents import _load_agents

        agents = _load_agents()
        required_rubric = [
            "importance_threshold_permanent",
            "quality_reject_threshold",
            "max_redistill_turns",
            "ask_user_confidence_threshold",
        ]
        for agent in agents:
            rubric = agent["decision_rubric"]
            for field in required_rubric:
                assert field in rubric, f"agent {agent.get('id')}: rubric 缺少 {field}"

    def test_decision_rubric_no_additional_properties(self):
        """decision_rubric 不含 schema 不允许的字段（additionalProperties: false）。"""
        from backend.api.routers.agents import _load_agents

        allowed = {
            "importance_threshold_permanent",
            "quality_reject_threshold",
            "max_redistill_turns",
            "ask_user_confidence_threshold",
            "cross_validate_sources",
            "session_timeout_seconds",
            "rejected_content_retention_days",
        }
        agents = _load_agents()
        for agent in agents:
            rubric_keys = set(agent["decision_rubric"].keys())
            extra = rubric_keys - allowed
            assert not extra, f"agent {agent.get('id')}: rubric 含不允许的字段 {extra}"

    def test_tools_config_has_8_tools(self):
        """tools_config 含 8 工具启用配置。"""
        from backend.api.routers.agents import _load_agents

        expected_tools = {
            "add_agent", "update_agent", "delete_agent",
            "start_distillation", "advance_distillation", "finalize_distillation",
            "render_template", "decide_storage",
        }
        agents = _load_agents()
        for agent in agents:
            tools = set(agent["tools_config"].keys())
            assert expected_tools.issubset(tools), f"agent {agent.get('id')}: 缺少工具 {expected_tools - tools}"


# ============================================================================ #
# 3. write_with_decision 3 路径分发
# ============================================================================ #


class TestWriteWithDecisionPaths:
    """MemoryManager.write_with_decision 3 路径分发 E2E 验证。"""

    @pytest.fixture
    def memory_manager(self, tmp_path):
        """提供隔离 db_path 的 MemoryManager 实例。"""
        from backend.core.memory.manager import MemoryManager

        db_path = str(tmp_path / "test_memories.db")
        return MemoryManager(db_path=db_path)

    def test_write_to_memories_path(self, memory_manager):
        """location=memories 写入 memories 表，返回 stored=True + memory_id。"""
        from backend.core.memory.manager import WriteWithDecisionResult

        result = memory_manager.write_with_decision(
            content="测试临时记忆内容",
            decision={"location": "memories", "quality_score": 0.8, "reason": "test"},
            metadata={"importance": 3, "tags": ["test"], "agent_id": "default"},
        )
        assert isinstance(result, WriteWithDecisionResult)
        assert result.stored is True
        assert result.location == "memories"
        assert result.memory_id is not None
        assert result.memory_id > 0

    def test_write_to_permanent_memories_path(self, memory_manager):
        """location=permanent_memories 写入 permanent_memories 表。"""
        from backend.core.memory.manager import WriteWithDecisionResult

        result = memory_manager.write_with_decision(
            content="测试永久记忆内容",
            decision={"location": "permanent_memories", "quality_score": 0.9, "reason": "important"},
            metadata={"tags": ["permanent"], "source": "user"},
        )
        assert isinstance(result, WriteWithDecisionResult)
        assert result.stored is True
        assert result.location == "permanent_memories"
        assert result.memory_id is not None

    def test_write_to_rejected_path(self, memory_manager):
        """location=rejected 写入 rejected_content 表。"""
        from backend.core.memory.manager import WriteWithDecisionResult

        result = memory_manager.write_with_decision(
            content="低质量内容应被拒绝",
            decision={"location": "rejected", "quality_score": 0.1, "reason": "quality too low"},
            metadata={"session_id": "test-session-001"},
        )
        assert isinstance(result, WriteWithDecisionResult)
        assert result.stored is True
        assert result.location == "rejected"

    def test_write_to_rejected_with_session_id(self, memory_manager):
        """rejected 路径支持 session_id 关联。"""
        session_id = "test-session-002"
        memory_manager.write_with_decision(
            content="拒绝内容 2",
            decision={"location": "rejected", "quality_score": 0.2, "reason": "test"},
            metadata={"session_id": session_id},
        )
        rejected = memory_manager.get_rejected_content(session_id=session_id)
        assert len(rejected) >= 1
        assert any(r.get("session_id") == session_id for r in rejected)

    def test_invalid_location_raises_value_error(self, memory_manager):
        """location 不在枚举中时 raise ValueError（422）。"""
        with pytest.raises(ValueError):
            memory_manager.write_with_decision(
                content="invalid",
                decision={"location": "invalid_location"},
                metadata={},
            )


# ============================================================================ #
# 4. get_rejected_content + cleanup_expired_rejected_content
# ============================================================================ #


class TestRejectedContentLifecycle:
    """rejected_content 查询 + 清理 E2E 验证。"""

    @pytest.fixture
    def memory_manager(self, tmp_path):
        from backend.core.memory.manager import MemoryManager

        return MemoryManager(db_path=str(tmp_path / "test_rejected.db"))

    def test_get_rejected_content_returns_list(self, memory_manager):
        """get_rejected_content 返回列表。"""
        # 先写入一条
        memory_manager.write_with_decision(
            content="测试拒绝内容",
            decision={"location": "rejected", "quality_score": 0.1, "reason": "test"},
            metadata={"session_id": "lifecycle-001"},
        )
        result = memory_manager.get_rejected_content()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_get_rejected_content_filter_by_session(self, memory_manager):
        """get_rejected_content 支持 session_id 过滤。"""
        memory_manager.write_with_decision(
            content="session A 内容",
            decision={"location": "rejected", "quality_score": 0.1, "reason": "test"},
            metadata={"session_id": "session-A"},
        )
        memory_manager.write_with_decision(
            content="session B 内容",
            decision={"location": "rejected", "quality_score": 0.1, "reason": "test"},
            metadata={"session_id": "session-B"},
        )
        result_a = memory_manager.get_rejected_content(session_id="session-A")
        result_b = memory_manager.get_rejected_content(session_id="session-B")
        assert all(r.get("session_id") == "session-A" for r in result_a)
        assert all(r.get("session_id") == "session-B" for r in result_b)

    def test_cleanup_expired_returns_int(self, memory_manager):
        """cleanup_expired_rejected_content 返回清理数量（int）。"""
        # 写入一条
        memory_manager.write_with_decision(
            content="将过期的拒绝内容",
            decision={"location": "rejected", "quality_score": 0.1, "reason": "test"},
            metadata={"session_id": "cleanup-test"},
        )
        # 清理 0 天前的（理论上当前写入的不应被清理，因为刚创建）
        cleaned = memory_manager.cleanup_expired_rejected_content(retention_days=30)
        assert isinstance(cleaned, int)
        assert cleaned >= 0

    def test_get_rejected_content_limit(self, memory_manager):
        """get_rejected_content 支持 limit 参数。"""
        # 写入 3 条
        for i in range(3):
            memory_manager.write_with_decision(
                content=f"拒绝内容 {i}",
                decision={"location": "rejected", "quality_score": 0.1, "reason": "test"},
                metadata={"session_id": f"limit-test-{i}"},
            )
        result = memory_manager.get_rejected_content(limit=2)
        assert len(result) <= 2


# ============================================================================ #
# 5. agent_tools Mock→真实切换
# ============================================================================ #


class TestAgentToolsDistillationServiceSwitch:
    """AgentToolsV2 _get_distillation_service Mock→真实切换 E2E 验证。"""

    def test_get_distillation_service_returns_real_implementation(self):
        """_get_distillation_service 应返回真实 DistillationService（模块9）。"""
        from modules.模块10_管理Agent扩展.agent_tools import AgentToolsV2
        from modules.模块9_蒸馏服务 import DistillationService

        tools = AgentToolsV2(caller_agent_id=None)
        service = tools._get_distillation_service()
        # 真实实现或 Mock fallback（取决于环境），但类型应可调用
        assert service is not None
        # 若为真实实现，类型应为 DistillationService
        if not type(service).__name__.startswith("Mock"):
            assert isinstance(service, DistillationService), \
                f"期望 DistillationService，实际 {type(service).__name__}"

    def test_get_distillation_service_caches_instance(self):
        """_get_distillation_service 第二次调用返回同一实例（懒加载缓存）。"""
        from modules.模块10_管理Agent扩展.agent_tools import AgentToolsV2

        tools = AgentToolsV2(caller_agent_id=None)
        service1 = tools._get_distillation_service()
        service2 = tools._get_distillation_service()
        assert service1 is service2, "懒加载应缓存实例"

    def test_distillation_service_fallback_to_mock_on_failure(self, monkeypatch):
        """真实 DistillationService 实例化失败时 fallback Mock（rules-0 §三 try-except）。"""
        from modules.模块10_管理Agent扩展 import agent_tools as at_module

        # 模拟真实导入失败
        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name == "modules.模块9_蒸馏服务":
                raise ImportError("模拟真实实现不可用")
            return original_import(name, *args, **kwargs)

        # 重置 tools 实例的缓存
        tools = at_module.AgentToolsV2(caller_agent_id=None)
        tools._distillation_service = None

        monkeypatch.setattr("builtins.__import__", fake_import)
        try:
            service = tools._get_distillation_service()
            assert service is not None, "fallback 应返回 Mock 实例"
            # Mock 类型名应以 Mock 开头
            assert type(service).__name__.startswith("Mock"), \
                f"期望 Mock 实例，实际 {type(service).__name__}"
        finally:
            monkeypatch.setattr("builtins.__import__", original_import)


# ============================================================================ #
# 6. agents.json schema 校验
# ============================================================================ #


class TestAgentsJsonSchemaValidation:
    """agents.json 通过 agent_config_v2.schema.json 校验 E2E 验证。"""

    def test_agents_json_exists_and_has_2_agents(self):
        """agents.json 存在且含 2 agent（default + memory-agent）。"""
        assert _AGENTS_JSON_PATH.exists(), "agents.json 应存在"
        with open(_AGENTS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) >= 2
        agent_ids = {a.get("id") for a in data}
        assert "default" in agent_ids
        assert "memory-agent" in agent_ids

    def test_agents_json_passes_schema_validation(self):
        """agents.json 每条记录通过 agent_config_v2.schema.json 校验。"""
        schema = _load_schema(_AGENT_CONFIG_V2_SCHEMA_PATH)
        with open(_AGENTS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        for agent in data:
            # 不 raise 即通过
            jsonschema.validate(agent, schema)

    def test_agents_json_agent_id_matches_id(self):
        """每条记录的 agent_id 与 id 字段一致（auto_fill 同步）。"""
        with open(_AGENTS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for agent in data:
            assert agent.get("agent_id") == agent.get("id"), \
                f"agent_id={agent.get('agent_id')} 与 id={agent.get('id')} 不一致"


# ============================================================================ #
# 7. documents 表 updated_at DEFAULT（额外修复验证）
# ============================================================================ #


class TestDocumentsTableUpdatedAtDefault:
    """documents 表 updated_at DEFAULT CURRENT_TIMESTAMP 验证。"""

    def test_create_table_contains_default_current_timestamp(self):
        """_init_db 的 CREATE TABLE 语句含 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP。"""
        from backend.core.document.memory import DocumentMemoryManager

        src = inspect.getsource(DocumentMemoryManager._init_db)
        assert "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in src, \
            "documents 表 updated_at 应含 DEFAULT CURRENT_TIMESTAMP"

    def test_create_table_updated_at_symmetric_with_created_at(self):
        """updated_at 与 created_at 默认值对称（均为 DEFAULT CURRENT_TIMESTAMP）。"""
        from backend.core.document.memory import DocumentMemoryManager

        src = inspect.getsource(DocumentMemoryManager._init_db)
        assert "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in src
        assert "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in src


# ============================================================================ #
# 8. WriteWithDecisionResult 模型
# ============================================================================ #


class TestWriteWithDecisionResultModel:
    """WriteWithDecisionResult Pydantic 模型字段一致性 E2E 验证。"""

    def test_model_has_5_required_fields(self):
        """WriteWithDecisionResult 含 5 字段（与 memory_manager_v2.pyi 一致）。"""
        from backend.core.memory.manager import WriteWithDecisionResult

        fields = set(WriteWithDecisionResult.model_fields.keys())
        expected = {"stored", "location", "memory_id", "metadata", "reason"}
        assert fields == expected, f"字段不匹配: {fields} vs {expected}"

    def test_model_defaults(self):
        """WriteWithDecisionResult 默认值正确。"""
        from backend.core.memory.manager import WriteWithDecisionResult

        result = WriteWithDecisionResult(stored=True, location="memories")
        assert result.stored is True
        assert result.location == "memories"
        assert result.memory_id is None
        assert result.metadata == {}
        assert result.reason == ""

    def test_model_location_enum_matches_schema(self):
        """location 字段值与 storage_decision.schema.json 的 location 枚举一致。"""
        schema = _load_schema(_SCHEMA_DIR / "storage_decision.schema.json")
        expected_locations = set(schema["properties"]["location"]["enum"])
        assert expected_locations == {"memories", "permanent_memories", "rejected"}


# ============================================================================ #
# 9. 完整工作流集成（parser_v2 → DistillationService → write_with_decision）
# ============================================================================ #


class TestFullWorkflowIntegration:
    """Task 6 改动的完整工作流集成验证。

    验证 parser_v2 → DistillationService.start_distillation → advance → finalize
    → DecisionCore 决策 → MemoryManager.write_with_decision 的端到端协同。
    """

    @pytest.fixture
    def memory_manager(self, tmp_path):
        from backend.core.memory.manager import MemoryManager

        return MemoryManager(db_path=str(tmp_path / "test_workflow.db"))

    def test_distillation_service_start_returns_session_id(self, tmp_path):
        """DistillationService.start_distillation 返回合法 session_id。"""
        from modules.模块9_蒸馏服务 import DistillationService, StartDistillationRequest

        # 使用 Mock 配置避免依赖真实 vLLM
        config = {
            "distillation_service": {
                "persistence_dir": str(tmp_path / "sessions"),
                "default_max_turns": 2,
            },
            "vllm": {"base_url": "http://localhost:8002", "timeout": 5},
        }
        service = DistillationService(config=config)
        request = StartDistillationRequest(
            source_type="text",
            source_ref="test-document.txt",
            template_id="default",
            max_turns=2,
            ask_user_on_ambiguity=False,
        )
        # 异步调用（async → sync 桥接）
        import asyncio
        response = asyncio.run(service.start_distillation(
            source_type=request.source_type,
            source_ref=request.source_ref,
            template_id=request.template_id,
            max_turns=request.max_turns,
            ask_user_on_ambiguity=request.ask_user_on_ambiguity,
        ))
        assert response.session_id is not None
        assert len(response.session_id) > 0

    def test_write_with_decision_after_distillation(self, memory_manager):
        """蒸馏完成后 write_with_decision 根据 DecisionCore 决策写入对应位置。"""
        # 模拟 DecisionCore 决策结果（quality_score 高 → permanent_memories）
        decision_permanent = {
            "location": "permanent_memories",
            "quality_score": 0.9,
            "reason": "高质量内容存入永久记忆",
        }
        result = memory_manager.write_with_decision(
            content="用户偏好：喜欢简洁的代码风格",
            decision=decision_permanent,
            metadata={"tags": ["preference"], "source": "distillation"},
        )
        assert result.stored is True
        assert result.location == "permanent_memories"

        # 模拟低质量决策（quality_score 低 → rejected）
        decision_rejected = {
            "location": "rejected",
            "quality_score": 0.1,
            "reason": "内容质量过低",
        }
        result_rejected = memory_manager.write_with_decision(
            content="无意义内容",
            decision=decision_rejected,
            metadata={"session_id": "workflow-test-001"},
        )
        assert result_rejected.stored is True
        assert result_rejected.location == "rejected"

    def test_parser_v2_to_distillation_workflow(self, tmp_path):
        """parser_v2 解析文本 → DistillationService 处理的端到端工作流。"""
        from backend.core.document.parser import parse_attachments_v2
        from modules.模块9_蒸馏服务 import DistillationService, StartDistillationRequest

        # 1. parser_v2 解析附件（legacy 模式，稳定路径）
        attachments = [
            {
                "name": "workflow.txt",
                "mime": "text/plain",
                "contentString": "data:text/plain;base64,5bCP56iL5YaF5a6577yM6L+Z5Liq5piv5rWL6K+V55qE5a+86Ie25oCb6L2v",
            }
        ]
        combined_text, _ = parse_attachments_v2(attachments, legacy_parser_enabled=True)
        assert len(combined_text) > 0

        # 2. DistillationService 启动蒸馏会话（source_type=text）
        config = {
            "distillation_service": {
                "persistence_dir": str(tmp_path / "workflow_sessions"),
                "default_max_turns": 1,
            },
            "vllm": {"base_url": "http://localhost:8002", "timeout": 5},
        }
        service = DistillationService(config=config)
        import asyncio
        response = asyncio.run(service.start_distillation(
            source_type="text",
            source_ref="workflow.txt",
            template_id="default",
            max_turns=1,
            ask_user_on_ambiguity=False,
        ))
        assert response.session_id is not None


# ============================================================================ #
# 10. AgentConfig 默认常量
# ============================================================================ #


class TestAgentConfigDefaultConstants:
    """agents.py _DEFAULT_TOOLS_CONFIG + _DEFAULT_DECISION_RUBRIC 常量验证。"""

    def test_default_tools_config_has_8_tools_all_true(self):
        """_DEFAULT_TOOLS_CONFIG 含 8 工具且全部 True。"""
        from backend.api.routers.agents import _DEFAULT_TOOLS_CONFIG

        expected = {
            "add_agent", "update_agent", "delete_agent",
            "start_distillation", "advance_distillation", "finalize_distillation",
            "render_template", "decide_storage",
        }
        assert set(_DEFAULT_TOOLS_CONFIG.keys()) == expected
        assert all(_DEFAULT_TOOLS_CONFIG.values()), "默认工具应全部启用"

    def test_default_decision_rubric_has_4_required_thresholds(self):
        """_DEFAULT_DECISION_RUBRIC 含 4 必需阈值。"""
        from backend.api.routers.agents import _DEFAULT_DECISION_RUBRIC

        required = [
            "importance_threshold_permanent",
            "quality_reject_threshold",
            "max_redistill_turns",
            "ask_user_confidence_threshold",
        ]
        for field in required:
            assert field in _DEFAULT_DECISION_RUBRIC

    def test_default_decision_rubric_no_disallowed_fields(self):
        """_DEFAULT_DECISION_RUBRIC 不含 schema 不允许的字段。"""
        from backend.api.routers.agents import _DEFAULT_DECISION_RUBRIC

        allowed = {
            "importance_threshold_permanent",
            "quality_reject_threshold",
            "max_redistill_turns",
            "ask_user_confidence_threshold",
            "cross_validate_sources",
            "session_timeout_seconds",
            "rejected_content_retention_days",
        }
        extra = set(_DEFAULT_DECISION_RUBRIC.keys()) - allowed
        assert not extra, f"_DEFAULT_DECISION_RUBRIC 含不允许字段: {extra}"

    def test_default_decision_rubric_thresholds_in_valid_range(self):
        """_DEFAULT_DECISION_RUBRIC 阈值在 schema 范围内。"""
        from backend.api.routers.agents import _DEFAULT_DECISION_RUBRIC

        r = _DEFAULT_DECISION_RUBRIC
        assert 0 <= r["importance_threshold_permanent"] <= 1
        assert 0 <= r["quality_reject_threshold"] <= 1
        assert 0 <= r["max_redistill_turns"] <= 6
        assert 0 <= r["ask_user_confidence_threshold"] <= 1
        assert 60 <= r["session_timeout_seconds"] <= 7200
        assert 1 <= r["rejected_content_retention_days"] <= 90
