"""DecisionCore + AgentToolsV2 单元测试。

覆盖 Task 5 闭合判据：
    - 6 决策点基本调用（D1-D6）
    - rubric 驱动（阈值触发）
    - 决策审计日志 schema 校验（jsonschema.validate 通过 distillation_log.schema.json）
    - confidence 极低时回退 system_prompt 规则（llm_available=False）
    - 8 工具基本调用
    - 异常路径（404 KeyError / 409 FileExistsError / 403 PermissionError / 422 ValueError / 500 IOError / 503 ConnectionError）

运行方式：
    $env:PYTHONPATH = "."; python -m pytest tests/contract/test_decision_core_unit.py -v

@version 1.0.0
@see .trae/specs/add-management-agent-radix/tasks.md Task 5
"""

import json
import os
import sys
import uuid

import jsonschema
import pytest

# --------------------------------------------------------------------------- #
# 路径锚点（rules-0 §三）
# --------------------------------------------------------------------------- #
_THIS_FILE = os.path.abspath(__file__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SCHEMA_DIR = os.path.join(_PROJECT_ROOT, "public", "schema")
_DISTILLATION_LOG_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "distillation_log.schema.json")
_STORAGE_DECISION_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "storage_decision.schema.json")
_AGENT_CONFIG_V2_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "agent_config_v2.schema.json")


def _load_schema(path: str) -> dict:
    """加载 JSON Schema 文件。"""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


_DISTILLATION_LOG_SCHEMA = _load_schema(_DISTILLATION_LOG_SCHEMA_PATH)
_STORAGE_DECISION_SCHEMA = _load_schema(_STORAGE_DECISION_SCHEMA_PATH)
_AGENT_CONFIG_V2_SCHEMA = _load_schema(_AGENT_CONFIG_V2_SCHEMA_PATH)


def _valid_uuid() -> str:
    """生成合法 UUID v4（符合 schema pattern）。"""
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def rubric():
    """默认 rubric 快照。"""
    from modules.模块10_管理Agent扩展.decision_core import RubricSnapshot
    return RubricSnapshot(
        importance_threshold_permanent=0.7,
        quality_reject_threshold=0.3,
        max_redistill_turns=2,
        ask_user_confidence_threshold=0.4,
        cross_validate_sources=["text", "conversation_log"],
    )


@pytest.fixture
def rubric_no_cross_validate():
    """无跨源验证的 rubric。"""
    from modules.模块10_管理Agent扩展.decision_core import RubricSnapshot
    return RubricSnapshot(
        importance_threshold_permanent=0.7,
        quality_reject_threshold=0.3,
        max_redistill_turns=2,
        ask_user_confidence_threshold=0.4,
        cross_validate_sources=[],
    )


@pytest.fixture
def decision_input():
    """默认决策输入。"""
    from modules.模块10_管理Agent扩展.decision_core import DecisionInput
    return DecisionInput(
        artifact_summary="测试内容摘要",
        session_state="S_STORAGE_DECISION",
        turn_history_summary="turn1:proceed;turn2:ask_user",
        extracted_content="抽取的结构化内容",
        quality_score=0.82,
    )


@pytest.fixture
def core(tmp_path):
    """DecisionCore 实例（隔离 log_dir，LLM 默认不可用触发回退）。

    llm_available=False 确保测试不依赖真实 vLLM 服务，直接走 system_prompt 回退。
    """
    from modules.模块10_管理Agent扩展.decision_core import DecisionCore
    log_dir = str(tmp_path / "distillation_logs")
    agents_file = str(tmp_path / "agents.json")
    # 预置 agents.json 含 memory-agent rubric
    _seed_agents_file(agents_file)
    return DecisionCore(
        agents_file=agents_file,
        log_dir=log_dir,
        llm_available=False,
    )


@pytest.fixture
def core_llm(tmp_path):
    """DecisionCore 实例（LLM 可用，但实际调用会失败触发回退）。"""
    from modules.模块10_管理Agent扩展.decision_core import DecisionCore
    log_dir = str(tmp_path / "distillation_logs")
    agents_file = str(tmp_path / "agents.json")
    _seed_agents_file(agents_file)
    return DecisionCore(
        agents_file=agents_file,
        log_dir=log_dir,
        llm_available=True,
    )


def _seed_agents_file(agents_file: str) -> None:
    """预置 agents.json 含 memory-agent rubric。"""
    os.makedirs(os.path.dirname(agents_file), exist_ok=True)
    data = {
        "agents": [
            {
                "agent_id": "default",
                "name": "默认 Agent",
                "tools_config": {
                    "add_agent": True, "update_agent": True, "delete_agent": True,
                    "start_distillation": True, "advance_distillation": True,
                    "finalize_distillation": True, "render_template": True,
                    "decide_storage": True,
                },
                "decision_rubric": {
                    "importance_threshold_permanent": 0.7,
                    "quality_reject_threshold": 0.3,
                    "max_redistill_turns": 2,
                    "ask_user_confidence_threshold": 0.4,
                    "cross_validate_sources": [],
                },
                "distillation_enabled": False,
                "legacy_parser_enabled": True,
            },
            {
                "agent_id": "memory-agent",
                "name": "记忆管理 Agent",
                "tools_config": {
                    "add_agent": True, "update_agent": True, "delete_agent": True,
                    "start_distillation": True, "advance_distillation": True,
                    "finalize_distillation": True, "render_template": True,
                    "decide_storage": True,
                },
                "decision_rubric": {
                    "importance_threshold_permanent": 0.7,
                    "quality_reject_threshold": 0.3,
                    "max_redistill_turns": 2,
                    "ask_user_confidence_threshold": 0.4,
                    "cross_validate_sources": ["text", "conversation_log"],
                },
                "distillation_enabled": True,
                "legacy_parser_enabled": False,
            },
        ]
    }
    with open(agents_file, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


@pytest.fixture
def tools(tmp_path):
    """AgentToolsV2 实例（隔离 agents.json + decision_core）。"""
    from modules.模块10_管理Agent扩展.agent_tools import AgentToolsV2
    from modules.模块10_管理Agent扩展.decision_core import DecisionCore
    agents_file = str(tmp_path / "agents.json")
    _seed_agents_file(agents_file)
    log_dir = str(tmp_path / "distillation_logs")
    core = DecisionCore(
        agents_file=agents_file,
        log_dir=log_dir,
        llm_available=False,
    )
    return AgentToolsV2(
        caller_agent_id="memory-agent",
        agents_file=agents_file,
        decision_core=core,
    )


# --------------------------------------------------------------------------- #
# D1: decide_location
# --------------------------------------------------------------------------- #


class TestDecideLocation:
    """D1 存入位置决策测试。"""

    def test_d1_permanent_memories(self, core, decision_input, rubric):
        """importance >= 阈值 → permanent_memories。"""
        session_id = _valid_uuid()
        decision = core.decide_location(session_id, decision_input, rubric)

        assert decision.session_id == session_id
        assert decision.decision_point == "D1_LOCATION"
        assert decision.location == "permanent_memories"
        assert decision.memory_id is not None
        assert decision.quality_score == 0.82
        assert decision.rubric_snapshot.importance_threshold_permanent == 0.7
        # LLM 不可用 → llm_confidence=None（system_prompt 回退）
        assert decision.llm_confidence is None

    def test_d1_memories_low_importance(self, core, decision_input):
        """importance < 阈值 → memories（用高阈值 rubric）。"""
        from modules.模块10_管理Agent扩展.decision_core import RubricSnapshot
        rubric_high = RubricSnapshot(
            importance_threshold_permanent=0.9,
            quality_reject_threshold=0.3,
            max_redistill_turns=2,
            ask_user_confidence_threshold=0.4,
            cross_validate_sources=[],
        )
        session_id = _valid_uuid()
        decision = core.decide_location(session_id, decision_input, rubric_high)

        assert decision.location == "memories"
        assert decision.memory_id is not None

    def test_d1_rejected_low_quality(self, core, rubric):
        """quality_score < quality_reject_threshold → rejected。"""
        from modules.模块10_管理Agent扩展.decision_core import DecisionInput
        decision_input = DecisionInput(
            session_state="S_STORAGE_DECISION",
            quality_score=0.2,  # < 0.3
        )
        session_id = _valid_uuid()
        decision = core.decide_location(session_id, decision_input, rubric)

        assert decision.location == "rejected"
        assert decision.memory_id is None

    def test_d1_key_error_empty_session(self, core, decision_input, rubric):
        """session_id 空 → KeyError（404）。"""
        with pytest.raises(KeyError):
            core.decide_location("", decision_input, rubric)

    def test_d1_value_error_invalid_quality(self, core, rubric):
        """quality_score 超范围 → ValueError（422）。"""
        from modules.模块10_管理Agent扩展.decision_core import DecisionInput
        decision_input = DecisionInput(
            session_state="S_STORAGE_DECISION",
            quality_score=1.5,  # > 1
        )
        with pytest.raises(ValueError):
            core.decide_location(_valid_uuid(), decision_input, rubric)

    def test_d1_storage_decision_schema_valid(self, core, decision_input, rubric):
        """StorageDecision 通过 storage_decision.schema.json 校验。"""
        decision = core.decide_location(_valid_uuid(), decision_input, rubric)
        decision_dict = decision.model_dump()
        # rubric_snapshot 是嵌套对象，schema 要求是 object，model_dump 已展开
        jsonschema.validate(instance=decision_dict, schema=_STORAGE_DECISION_SCHEMA)


# --------------------------------------------------------------------------- #
# D2: decide_metadata
# --------------------------------------------------------------------------- #


class TestDecideMetadata:
    """D2 元数据决策测试。"""

    def test_d2_returns_metadata_dict(self, core, decision_input):
        """D2 返回含 time/importance/source/tags 的字典。"""
        metadata = core.decide_metadata(_valid_uuid(), decision_input)

        assert isinstance(metadata, dict)
        assert "time" in metadata
        assert "importance" in metadata
        assert "source" in metadata
        assert "tags" in metadata
        assert 0 <= metadata["importance"] <= 1
        assert isinstance(metadata["tags"], list)

    def test_d2_key_error_empty_session(self, core, decision_input):
        """session_id 空 → KeyError（404）。"""
        with pytest.raises(KeyError):
            core.decide_metadata("", decision_input)


# --------------------------------------------------------------------------- #
# D3: decide_ask_user
# --------------------------------------------------------------------------- #


class TestDecideAskUser:
    """D3 追问决策测试。"""

    def test_d3_ask_user_low_confidence(self, core, rubric):
        """llm_confidence < 阈值 → True（追问）。"""
        result = core.decide_ask_user(_valid_uuid(), 0.2, rubric)
        assert result is True  # 0.2 < 0.4

    def test_d3_no_ask_high_confidence(self, core, rubric):
        """llm_confidence >= 阈值 → False（不追问）。"""
        result = core.decide_ask_user(_valid_uuid(), 0.8, rubric)
        assert result is False  # 0.8 >= 0.4

    def test_d3_key_error_empty_session(self, core, rubric):
        """session_id 空 → KeyError（404）。"""
        with pytest.raises(KeyError):
            core.decide_ask_user("", 0.5, rubric)

    def test_d3_value_error_invalid_confidence(self, core, rubric):
        """llm_confidence 超范围 → ValueError（422）。"""
        with pytest.raises(ValueError):
            core.decide_ask_user(_valid_uuid(), 1.5, rubric)


# --------------------------------------------------------------------------- #
# D4: decide_redistill
# --------------------------------------------------------------------------- #


class TestDecideRedistill:
    """D4 再次蒸馏决策测试。"""

    def test_d4_redistill_under_max(self, core, rubric):
        """current_turn < max_redistill_turns → True。"""
        result = core.decide_redistill(_valid_uuid(), 1, rubric)
        assert result is True  # 1 < 2

    def test_d4_no_redistill_at_max(self, core, rubric):
        """current_turn >= max_redistill_turns → False。"""
        result = core.decide_redistill(_valid_uuid(), 2, rubric)
        assert result is False  # 2 >= 2

    def test_d4_key_error_empty_session(self, core, rubric):
        """session_id 空 → KeyError（404）。"""
        with pytest.raises(KeyError):
            core.decide_redistill("", 1, rubric)


# --------------------------------------------------------------------------- #
# D5: decide_cross_validate
# --------------------------------------------------------------------------- #


class TestDecideCrossValidate:
    """D5 跨源验证决策测试。"""

    def test_d5_cross_validate_triggered(self, core, decision_input, rubric):
        """cross_validate_sources 非空且 extracted_content 非空 → True。"""
        result = core.decide_cross_validate(_valid_uuid(), decision_input, rubric)
        assert result is True

    def test_d5_no_cross_validate_empty_sources(self, core, decision_input, rubric_no_cross_validate):
        """cross_validate_sources 空 → False。"""
        result = core.decide_cross_validate(_valid_uuid(), decision_input, rubric_no_cross_validate)
        assert result is False

    def test_d5_no_cross_validate_empty_content(self, core, rubric):
        """extracted_content 空 → False。"""
        from modules.模块10_管理Agent扩展.decision_core import DecisionInput
        decision_input = DecisionInput(
            session_state="S_STORAGE_DECISION",
            extracted_content=None,
        )
        result = core.decide_cross_validate(_valid_uuid(), decision_input, rubric)
        assert result is False


# --------------------------------------------------------------------------- #
# D6: decide_reject
# --------------------------------------------------------------------------- #


class TestDecideReject:
    """D6 拒绝存储决策测试。"""

    def test_d6_reject_returns_decision(self, core, rubric):
        """D6 返回 location=rejected 的 StorageDecision。"""
        decision = core.decide_reject(_valid_uuid(), 0.2, rubric)

        assert decision.decision_point == "D6_REJECT"
        assert decision.location == "rejected"
        assert decision.memory_id is None
        assert decision.quality_score == 0.2

    def test_d6_key_error_empty_session(self, core, rubric):
        """session_id 空 → KeyError（404）。"""
        with pytest.raises(KeyError):
            core.decide_reject("", 0.2, rubric)

    def test_d6_value_error_invalid_quality(self, core, rubric):
        """quality_score 超范围 → ValueError（422）。"""
        with pytest.raises(ValueError):
            core.decide_reject(_valid_uuid(), -0.1, rubric)


# --------------------------------------------------------------------------- #
# rubric 驱动测试
# --------------------------------------------------------------------------- #


class TestRubricDriven:
    """rubric 驱动决策测试（阈值触发）。"""

    def test_rubric_quality_reject_threshold(self, core, decision_input):
        """quality_score < quality_reject_threshold 触发 rejected。"""
        from modules.模块10_管理Agent扩展.decision_core import RubricSnapshot
        rubric = RubricSnapshot(
            importance_threshold_permanent=0.7,
            quality_reject_threshold=0.5,  # 高拒绝阈值
            max_redistill_turns=2,
            ask_user_confidence_threshold=0.4,
            cross_validate_sources=[],
        )
        decision_input.quality_score = 0.4  # < 0.5
        decision = core.decide_location(_valid_uuid(), decision_input, rubric)
        assert decision.location == "rejected"

    def test_rubric_importance_threshold(self, core, decision_input):
        """importance >= importance_threshold_permanent 触发 permanent_memories。"""
        from modules.模块10_管理Agent扩展.decision_core import RubricSnapshot
        # 回退 importance=0.75，阈值 0.7 → permanent_memories
        rubric = RubricSnapshot(
            importance_threshold_permanent=0.7,
            quality_reject_threshold=0.3,
            max_redistill_turns=2,
            ask_user_confidence_threshold=0.4,
            cross_validate_sources=[],
        )
        decision_input.quality_score = 0.82
        decision = core.decide_location(_valid_uuid(), decision_input, rubric)
        assert decision.location == "permanent_memories"

    def test_rubric_max_redistill_turns(self, core):
        """max_redistill_turns 限制再次蒸馏。"""
        from modules.模块10_管理Agent扩展.decision_core import RubricSnapshot
        rubric = RubricSnapshot(
            importance_threshold_permanent=0.7,
            quality_reject_threshold=0.3,
            max_redistill_turns=3,
            ask_user_confidence_threshold=0.4,
            cross_validate_sources=[],
        )
        assert core.decide_redistill(_valid_uuid(), 2, rubric) is True  # 2 < 3
        assert core.decide_redistill(_valid_uuid(), 3, rubric) is False  # 3 >= 3


# --------------------------------------------------------------------------- #
# 审计日志 schema 校验
# --------------------------------------------------------------------------- #


class TestAuditLogSchema:
    """决策审计日志 schema 校验测试。"""

    def test_audit_log_passes_distillation_log_schema(self, core, decision_input, rubric):
        """审计日志通过 distillation_log.schema.json 校验。"""
        session_id = _valid_uuid()
        core.decide_location(session_id, decision_input, rubric)

        logs = core._read_audit_logs(session_id)
        assert len(logs) >= 1

        for log_entry in logs:
            # 严格 schema 校验（additionalProperties: false）
            jsonschema.validate(instance=log_entry, schema=_DISTILLATION_LOG_SCHEMA)

    def test_audit_log_d6_passes_schema(self, core, rubric):
        """D6 审计日志通过 schema 校验。"""
        session_id = _valid_uuid()
        core.decide_reject(session_id, 0.2, rubric)

        logs = core._read_audit_logs(session_id)
        assert len(logs) >= 1
        for log_entry in logs:
            jsonschema.validate(instance=log_entry, schema=_DISTILLATION_LOG_SCHEMA)

    def test_audit_log_structure(self, core, decision_input, rubric):
        """审计日志结构含 9 个必需/可选字段。"""
        session_id = _valid_uuid()
        core.decide_location(session_id, decision_input, rubric)

        logs = core._read_audit_logs(session_id)
        log_entry = logs[0]

        # required 字段
        assert "log_id" in log_entry
        assert "session_id" in log_entry
        assert "decision_point" in log_entry
        assert "input" in log_entry
        assert "rubric_snapshot" in log_entry
        assert "final_decision" in log_entry
        assert "timestamp" in log_entry
        # 可选字段
        assert "llm_reasoning" in log_entry
        assert "llm_confidence" in log_entry
        # final_decision 结构
        fd = log_entry["final_decision"]
        assert "action" in fd
        assert "details" in fd

    def test_audit_log_llm_none_on_fallback(self, core, decision_input, rubric):
        """LLM 不可用时审计日志 llm_confidence=None / llm_reasoning=None。"""
        session_id = _valid_uuid()
        core.decide_location(session_id, decision_input, rubric)

        logs = core._read_audit_logs(session_id)
        log_entry = logs[0]
        assert log_entry["llm_confidence"] is None
        assert log_entry["llm_reasoning"] is None


# --------------------------------------------------------------------------- #
# system_prompt 回退测试
# --------------------------------------------------------------------------- #


class TestSystemPromptFallback:
    """confidence 极低时回退 system_prompt 规则测试。"""

    def test_fallback_llm_confidence_none(self, core, decision_input, rubric):
        """LLM 不可用时 llm_confidence=None（回退 system_prompt 规则）。"""
        decision = core.decide_location(_valid_uuid(), decision_input, rubric)
        assert decision.llm_confidence is None

    def test_fallback_decision_still_valid(self, core, decision_input, rubric):
        """回退后决策仍有效（rubric 驱动）。"""
        decision = core.decide_location(_valid_uuid(), decision_input, rubric)
        # 回退后仍按 rubric 决策
        assert decision.location in ("memories", "permanent_memories", "rejected")
        assert decision.reason  # reason 非空

    def test_fallback_d2_metadata(self, core, decision_input):
        """D2 LLM 不可用时回退规则元数据。"""
        metadata = core.decide_metadata(_valid_uuid(), decision_input)
        assert "fallback" in metadata["tags"]

    def test_llm_decide_raises_connection_error(self, core, decision_input):
        """_llm_decide 直接调用 raise ConnectionError（503）。"""
        from modules.模块10_管理Agent扩展.decision_core import DecisionInput
        with pytest.raises(ConnectionError):
            core._llm_decide("test prompt", decision_input)


# --------------------------------------------------------------------------- #
# 8 工具基本调用测试
# --------------------------------------------------------------------------- #


class TestAgentToolsBasic:
    """8 工具基本调用测试。"""

    def test_tool_add_agent(self, tools):
        """工具 1: add_agent 创建新 agent。"""
        from modules.模块10_管理Agent扩展.agent_tools import AddAgentRequest
        request = AddAgentRequest(
            agent_id="test-agent-new",
            name="测试 Agent",
            config={
                "tools_config": {
                    "add_agent": True, "update_agent": True, "delete_agent": True,
                    "start_distillation": True, "advance_distillation": True,
                    "finalize_distillation": True, "render_template": True,
                    "decide_storage": True,
                },
                "decision_rubric": {
                    "importance_threshold_permanent": 0.7,
                    "quality_reject_threshold": 0.3,
                    "max_redistill_turns": 2,
                    "ask_user_confidence_threshold": 0.4,
                },
                "distillation_enabled": True,
            },
        )
        record = tools.add_agent(request)
        assert record.agent_id == "test-agent-new"
        assert record.name == "测试 Agent"
        assert record.distillation_enabled is True
        # schema 校验
        jsonschema.validate(instance=record.model_dump(), schema=_AGENT_CONFIG_V2_SCHEMA)

    def test_tool_update_agent(self, tools):
        """工具 2: update_agent 更新 agent。"""
        from modules.模块10_管理Agent扩展.agent_tools import UpdateAgentRequest
        record = tools.update_agent("default", UpdateAgentRequest(name="更新后的 Agent"))
        assert record.name == "更新后的 Agent"

    def test_tool_delete_agent(self, tools):
        """工具 3: delete_agent 删除 agent。"""
        result = tools.delete_agent("default")
        assert result is True
        # 删除后再查应不存在
        with pytest.raises(KeyError):
            tools.delete_agent("default")

    def test_tool_start_distillation(self, tools):
        """工具 4: start_distillation 启动蒸馏会话。"""
        from modules.模块10_管理Agent扩展.agent_tools import StartDistillationToolRequest
        request = StartDistillationToolRequest(
            source_type="text",
            source_ref="test.txt",
            template_id="default",
            max_turns=4,
            ask_user_on_ambiguity=True,
        )
        result = tools.start_distillation(request)
        assert "session_id" in result
        assert "initial_state" in result
        assert "preread_summary" in result
        assert result["initial_state"] == "S_PREREAD"

    def test_tool_advance_distillation(self, tools):
        """工具 5: advance_distillation 推进蒸馏状态机。"""
        from modules.模块10_管理Agent扩展.agent_tools import (
            AdvanceDistillationToolRequest,
            StartDistillationToolRequest,
        )
        # 先 start
        start_req = StartDistillationToolRequest(
            source_type="text",
            template_id="default",
        )
        start_resp = tools.start_distillation(start_req)
        session_id = start_resp["session_id"]

        # 再 advance
        request = AdvanceDistillationToolRequest(session_id=session_id)
        result = tools.advance_distillation(request)
        assert "session_id" in result
        assert "current_state" in result
        assert "agent_action" in result
        assert "next_needed" in result

    def test_tool_finalize_distillation(self, tools):
        """工具 6: finalize_distillation 终结蒸馏会话。"""
        from modules.模块10_管理Agent扩展.agent_tools import (
            FinalizeDistillationToolRequest,
            StartDistillationToolRequest,
        )
        start_req = StartDistillationToolRequest(
            source_type="text",
            template_id="default",
        )
        start_resp = tools.start_distillation(start_req)
        session_id = start_resp["session_id"]

        request = FinalizeDistillationToolRequest(session_id=session_id)
        result = tools.finalize_distillation(request)
        assert "stored" in result
        assert "location" in result
        assert "memory_id" in result
        assert "metadata" in result
        assert "reason" in result

    def test_tool_render_template(self, tools):
        """工具 7: render_template 渲染模板。"""
        from modules.模块10_管理Agent扩展.agent_tools import RenderTemplateToolRequest
        request = RenderTemplateToolRequest(
            template_id="default",
            variables={"content": "测试内容"},
        )
        result = tools.render_template(request)
        assert "rendered_prompt" in result
        assert "workflow_definition" in result
        assert "expected_turns" in result

    def test_tool_decide_storage(self, tools):
        """工具 8: decide_storage 智能存储决策。"""
        from modules.模块10_管理Agent扩展.agent_tools import DecideStorageToolRequest
        request = DecideStorageToolRequest(session_id=_valid_uuid())
        result = tools.decide_storage(request)
        assert "decision_id" in result
        assert "session_id" in result
        assert "decision_point" in result
        assert "location" in result
        assert "memory_id" in result
        assert "metadata" in result
        assert "reason" in result
        assert "quality_score" in result

    def test_tool_decide_storage_override_permanent(self, tools):
        """工具 8: decide_storage override=permanent 覆盖决策。"""
        from modules.模块10_管理Agent扩展.agent_tools import DecideStorageToolRequest
        request = DecideStorageToolRequest(
            session_id=_valid_uuid(),
            override_decision="permanent",
        )
        result = tools.decide_storage(request)
        assert result["location"] == "permanent_memories"

    def test_tool_decide_storage_override_reject(self, tools):
        """工具 8: decide_storage override=reject 覆盖决策。"""
        from modules.模块10_管理Agent扩展.agent_tools import DecideStorageToolRequest
        request = DecideStorageToolRequest(
            session_id=_valid_uuid(),
            override_decision="reject",
        )
        result = tools.decide_storage(request)
        assert result["location"] == "rejected"
        assert result["memory_id"] is None


# --------------------------------------------------------------------------- #
# 异常路径测试
# --------------------------------------------------------------------------- #


class TestExceptionPaths:
    """异常路径测试（404/409/403/422/500/503）。"""

    def test_404_key_error_agent_not_found(self, tools):
        """404: update_agent agent_id 不存在 → KeyError。"""
        from modules.模块10_管理Agent扩展.agent_tools import UpdateAgentRequest
        with pytest.raises(KeyError):
            tools.update_agent("nonexistent-agent", UpdateAgentRequest(name="x"))

    def test_404_key_error_delete_not_found(self, tools):
        """404: delete_agent agent_id 不存在 → KeyError。"""
        with pytest.raises(KeyError):
            tools.delete_agent("nonexistent-agent")

    def test_404_key_error_session_empty(self, tools):
        """404: decide_storage session_id 空 → KeyError。"""
        from modules.模块10_管理Agent扩展.agent_tools import DecideStorageToolRequest
        with pytest.raises(KeyError):
            tools.decide_storage(DecideStorageToolRequest(session_id=""))

    def test_409_file_exists_error(self, tools):
        """409: add_agent agent_id 已存在 → FileExistsError。"""
        from modules.模块10_管理Agent扩展.agent_tools import AddAgentRequest
        request = AddAgentRequest(
            agent_id="default",  # 已存在
            name="重复 Agent",
            config={
                "decision_rubric": {
                    "importance_threshold_permanent": 0.7,
                    "quality_reject_threshold": 0.3,
                    "max_redistill_turns": 2,
                    "ask_user_confidence_threshold": 0.4,
                },
            },
        )
        with pytest.raises(FileExistsError):
            tools.add_agent(request)

    def test_422_value_error_invalid_rubric(self, tools):
        """422: add_agent rubric 缺必需字段 → ValueError。"""
        from modules.模块10_管理Agent扩展.agent_tools import AddAgentRequest
        request = AddAgentRequest(
            agent_id="bad-agent",
            name="坏 Agent",
            config={
                "decision_rubric": {
                    # 缺 quality_reject_threshold / max_redistill_turns / ask_user_confidence_threshold
                    "importance_threshold_permanent": 0.7,
                },
            },
        )
        with pytest.raises(ValueError):
            tools.add_agent(request)

    def test_422_value_error_invalid_source_type(self, tools):
        """422: start_distillation source_type 无效 → ValueError。"""
        from modules.模块10_管理Agent扩展.agent_tools import StartDistillationToolRequest
        request = StartDistillationToolRequest(
            source_type="invalid_type",
            template_id="default",
        )
        with pytest.raises(ValueError):
            tools.start_distillation(request)

    def test_422_value_error_invalid_max_turns(self, tools):
        """422: start_distillation max_turns 超范围 → ValueError。"""
        from modules.模块10_管理Agent扩展.agent_tools import StartDistillationToolRequest
        request = StartDistillationToolRequest(
            source_type="text",
            template_id="default",
            max_turns=10,  # > 6
        )
        with pytest.raises(ValueError):
            tools.start_distillation(request)

    def test_403_permission_error_tool_disabled(self, tmp_path):
        """403: 工具未启用 → PermissionError。"""
        from modules.模块10_管理Agent扩展.agent_tools import AgentToolsV2
        from modules.模块10_管理Agent扩展.agent_tools import DecideStorageToolRequest
        from modules.模块10_管理Agent扩展.decision_core import DecisionCore

        agents_file = str(tmp_path / "agents.json")
        log_dir = str(tmp_path / "distillation_logs")
        # 预置 caller agent 禁用 decide_storage
        data = {
            "agents": [
                {
                    "agent_id": "memory-agent",
                    "name": "记忆管理 Agent",
                    "tools_config": {
                        "add_agent": True, "update_agent": True, "delete_agent": True,
                        "start_distillation": True, "advance_distillation": True,
                        "finalize_distillation": True, "render_template": True,
                        "decide_storage": False,  # 禁用
                    },
                    "decision_rubric": {
                        "importance_threshold_permanent": 0.7,
                        "quality_reject_threshold": 0.3,
                        "max_redistill_turns": 2,
                        "ask_user_confidence_threshold": 0.4,
                    },
                    "distillation_enabled": True,
                }
            ]
        }
        with open(agents_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)

        core = DecisionCore(agents_file=agents_file, log_dir=log_dir, llm_available=False)
        tools = AgentToolsV2(
            caller_agent_id="memory-agent",
            agents_file=agents_file,
            decision_core=core,
        )
        with pytest.raises(PermissionError):
            tools.decide_storage(DecideStorageToolRequest(session_id=_valid_uuid()))

    def test_403_permission_error_distillation_disabled(self, tmp_path):
        """403: distillation_enabled=false → PermissionError。"""
        from modules.模块10_管理Agent扩展.agent_tools import (
            AgentToolsV2,
            StartDistillationToolRequest,
        )

        agents_file = str(tmp_path / "agents.json")
        data = {
            "agents": [
                {
                    "agent_id": "memory-agent",
                    "name": "记忆管理 Agent",
                    "tools_config": {
                        "add_agent": True, "update_agent": True, "delete_agent": True,
                        "start_distillation": True, "advance_distillation": True,
                        "finalize_distillation": True, "render_template": True,
                        "decide_storage": True,
                    },
                    "decision_rubric": {
                        "importance_threshold_permanent": 0.7,
                        "quality_reject_threshold": 0.3,
                        "max_redistill_turns": 2,
                        "ask_user_confidence_threshold": 0.4,
                    },
                    "distillation_enabled": False,  # 禁用蒸馏
                }
            ]
        }
        with open(agents_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)

        tools = AgentToolsV2(caller_agent_id="memory-agent", agents_file=agents_file)
        request = StartDistillationToolRequest(
            source_type="text",
            template_id="default",
        )
        with pytest.raises(PermissionError):
            tools.start_distillation(request)

    def test_503_connection_error_llm_decide(self, core, decision_input):
        """503: _llm_decide LLM 不可用 → ConnectionError。"""
        with pytest.raises(ConnectionError):
            core._llm_decide("test prompt", decision_input)


# --------------------------------------------------------------------------- #
# agent 配置 schema 校验
# --------------------------------------------------------------------------- #


class TestAgentConfigSchema:
    """agent 配置通过 agent_config_v2.schema.json 校验。"""

    def test_default_agent_passes_schema(self, tools):
        """default agent 通过 agent_config_v2.schema 校验。"""
        from modules.模块10_管理Agent扩展.agent_tools import _make_default_agent
        record = _make_default_agent()
        jsonschema.validate(instance=record.model_dump(), schema=_AGENT_CONFIG_V2_SCHEMA)

    def test_memory_agent_passes_schema(self, tools):
        """memory-agent 通过 agent_config_v2.schema 校验。"""
        from modules.模块10_管理Agent扩展.agent_tools import _make_memory_agent
        record = _make_memory_agent()
        jsonschema.validate(instance=record.model_dump(), schema=_AGENT_CONFIG_V2_SCHEMA)

    def test_added_agent_passes_schema(self, tools):
        """add_agent 创建的 agent 通过 schema 校验。"""
        from modules.模块10_管理Agent扩展.agent_tools import AddAgentRequest
        request = AddAgentRequest(
            agent_id="schema-test-agent",
            name="Schema 测试 Agent",
            config={
                "tools_config": {
                    "add_agent": True, "update_agent": True, "delete_agent": True,
                    "start_distillation": True, "advance_distillation": True,
                    "finalize_distillation": True, "render_template": True,
                    "decide_storage": True,
                },
                "decision_rubric": {
                    "importance_threshold_permanent": 0.7,
                    "quality_reject_threshold": 0.3,
                    "max_redistill_turns": 2,
                    "ask_user_confidence_threshold": 0.4,
                    "cross_validate_sources": [],
                },
                "distillation_enabled": True,
                "legacy_parser_enabled": False,
            },
        )
        record = tools.add_agent(request)
        jsonschema.validate(instance=record.model_dump(), schema=_AGENT_CONFIG_V2_SCHEMA)
