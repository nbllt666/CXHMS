"""DistillationService 主实现。

RADIX-Lite 蒸馏服务，独立 FastAPI 子服务（端口 8011）。
7 状态机多轮蒸馏工作流，与 MultimodalPipeline / TemplateEngine / DecisionCore 协同。

状态机:
    S_INIT -> S_PREREAD -> S_QUESTION -> S_REFLECT -> S_CROSSVALIDATE
           -> S_EXTRACT -> S_STORAGE_DECISION -> S_FINALIZE / S_REJECT

    回环: S_REFLECT -> S_QUESTION (D4_REDISTILL 决策驱动，受 max_redistill_turns 限制)
    主动追问: ask_user_on_ambiguity=True 且 S_QUESTION 时 agent_action=ask_user
    拒绝路径: S_REJECT (confidence 极低 / max_turns 超限 / quality_score 低于阈值)

对应契约:
    - 接口契约: public/interface_stub/distillation_service.pyi
    - 数据契约: public/schema/distillation_session.schema.json
    - 数据契约: public/schema/distillation_log.schema.json
    - 配置契约: public/config_template/radix_config.json

@version 1.0.0
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 路径锚点（rules-0 §三：os.path.dirname(os.path.abspath(__file__))）
# --------------------------------------------------------------------------- #
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_DEFAULT_SESSION_DIR = os.path.join(_DATA_DIR, "distillation_sessions")
_DEFAULT_LOG_DIR = os.path.join(_DATA_DIR, "distillation_logs")
_CONFIG_PATH = os.path.join(
    _PROJECT_ROOT, "public", "config_template", "radix_config.json"
)


def _iso_now() -> str:
    """返回 ISO 8601 带时区时间戳。

    Returns:
        str: UTC 时间 ISO 8601 字符串
    """
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    """生成 UUID v4 字符串。

    Returns:
        str: 36 字符 UUID v4
    """
    return str(uuid.uuid4())


def _ensure_dir(path: str) -> None:
    """确保目录存在（auto_init: data补全，rules-0 §三）。

    Args:
        path: 目录绝对路径
    """
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


# --------------------------------------------------------------------------- #
# Pydantic 响应/请求模型（严格匹配 distillation_service.pyi）
# --------------------------------------------------------------------------- #


class StartDistillationRequest(BaseModel):
    """启动蒸馏会话请求。"""

    source_type: str  # enum: text / character_card / image / conversation_log
    source_ref: Optional[str] = None
    template_id: str
    max_turns: int = 4  # 1-6
    ask_user_on_ambiguity: bool = True


class StartDistillationResponse(BaseModel):
    """启动蒸馏会话响应。"""

    session_id: str
    initial_state: str  # S_PREREAD
    preread_summary: Optional[str]


class AdvanceDistillationRequest(BaseModel):
    """推进蒸馏状态机请求。"""

    user_response: Optional[str] = None  # ask_user 时的用户响应


class AdvanceDistillationResponse(BaseModel):
    """推进蒸馏状态机响应。"""

    session_id: str
    current_state: str
    agent_action: str  # enum: ask_user / proceed / reflect / cross_validate / extract / decide / finalize / reject
    next_needed: bool  # 是否需要用户进一步输入


class FinalizeDistillationRequest(BaseModel):
    """终结蒸馏会话请求。"""

    override_decision: Optional[str] = None  # 人类覆盖决策


class FinalizeDistillationResponse(BaseModel):
    """终结蒸馏会话响应。"""

    stored: bool
    location: str  # enum: memories / permanent_memories / rejected
    memory_id: Optional[int]
    metadata: Dict[str, Any]
    reason: str


class SessionStatusResponse(BaseModel):
    """会话状态查询响应。字段与 distillation_session.schema.json 一致。"""

    session_id: str
    source_type: str
    state: str
    template_id: str
    max_turns: int
    ask_user_on_ambiguity: bool
    turns: List[Dict[str, Any]]
    preread_summary: Optional[str]
    ambiguity_questions: List[str]
    extracted_content: Optional[str]
    quality_score: Optional[float]
    created_at: str
    updated_at: Optional[str]
    finalized_at: Optional[str]
    is_finalized: bool
    error_message: Optional[str]


# --------------------------------------------------------------------------- #
# 状态机定义（与 distillation_session.schema.json enum 一致）
# --------------------------------------------------------------------------- #

_SOURCE_TYPES = {"text", "character_card", "image", "conversation_log"}

_STATES = (
    "S_INIT",
    "S_PREREAD",
    "S_QUESTION",
    "S_REFLECT",
    "S_CROSSVALIDATE",
    "S_EXTRACT",
    "S_STORAGE_DECISION",
    "S_FINALIZE",
    "S_REJECT",
)

_AGENT_ACTIONS = (
    "ask_user",
    "proceed",
    "reflect",
    "cross_validate",
    "extract",
    "decide",
    "finalize",
    "reject",
)

# 终态集合
_TERMINAL_STATES = {"S_FINALIZE", "S_REJECT"}

# 状态机转移表：(current_state, agent_action) -> next_state
# 与 distillation_session.schema.json 状态机描述一致
_TRANSITIONS: Dict[str, Dict[str, str]] = {
    "S_INIT": {"proceed": "S_PREREAD"},
    "S_PREREAD": {"ask_user": "S_QUESTION", "proceed": "S_QUESTION"},
    "S_QUESTION": {"proceed": "S_REFLECT", "ask_user": "S_QUESTION"},
    "S_REFLECT": {
        "proceed": "S_CROSSVALIDATE",
        "reflect": "S_QUESTION",
    },
    "S_CROSSVALIDATE": {
        "cross_validate": "S_EXTRACT",
        "proceed": "S_EXTRACT",
    },
    "S_EXTRACT": {"extract": "S_STORAGE_DECISION"},
    "S_STORAGE_DECISION": {
        "decide": "S_FINALIZE",
        "reject": "S_REJECT",
    },
    "S_FINALIZE": {"finalize": "S_FINALIZE"},
    "S_REJECT": {"reject": "S_REJECT"},
}


# --------------------------------------------------------------------------- #
# 配置加载（rules-3 §三 auto_fill，best-effort）
# --------------------------------------------------------------------------- #


def _load_distillation_config() -> Dict[str, Any]:
    """加载 radix_config.json 的 distillation_service 段配置。

    缺失字段用默认值补齐（rules-3 §三 auto_fill）。
    配置文件不存在或解析失败时使用全默认值（best-effort，不阻断启动）。

    Returns:
        Dict[str, Any]: distillation_service 配置段
    """
    defaults = {
        "host": "127.0.0.1",
        "port": 8011,
        "max_turns": 4,
        "session_timeout_seconds": 1800,
        "session_storage_dir": "data/distillation_sessions",
        "log_storage_dir": "data/distillation_logs",
        "main_backend_url": "http://127.0.0.1:8001",
    }
    try:
        if not os.path.exists(_CONFIG_PATH):
            return defaults
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            full = json.load(fh)
        seg = full.get("distillation_service", {})
        # auto_fill：缺失字段补默认值，范围外字段回退默认值
        for k, v in defaults.items():
            if k not in seg or seg[k] is None:
                seg[k] = v
        # 范围校验（best-effort，超范围回退默认值）
        if not (1 <= int(seg["max_turns"]) <= 6):
            seg["max_turns"] = defaults["max_turns"]
        if not (1024 <= int(seg["port"]) <= 65535):
            seg["port"] = defaults["port"]
        if not (60 <= int(seg["session_timeout_seconds"]) <= 7200):
            seg["session_timeout_seconds"] = defaults["session_timeout_seconds"]
        return seg
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return defaults


def _load_vllm_base_url() -> str:
    """加载 radix_config.json 的 vllm.base_url 配置。

    Returns:
        str: vLLM 主模型服务 URL（默认 http://127.0.0.1:8002）
    """
    default_url = "http://127.0.0.1:8002"
    try:
        if not os.path.exists(_CONFIG_PATH):
            return default_url
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            full = json.load(fh)
        vllm_seg = full.get("vllm", {})
        return vllm_seg.get("base_url", default_url)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return default_url


def _load_decision_core_config() -> Dict[str, Any]:
    """加载 radix_config.json 的 decision_core 段配置。

    Returns:
        Dict[str, Any]: decision_core 配置段（rubric 默认值）
    """
    defaults = {
        "importance_threshold_permanent": 0.7,
        "quality_reject_threshold": 0.3,
        "max_redistill_turns": 2,
        "ask_user_confidence_threshold": 0.4,
        "cross_validate_sources": [],
        "rejected_content_retention_days": 30,
        "system_prompt_fallback_enabled": True,
    }
    try:
        if not os.path.exists(_CONFIG_PATH):
            return defaults
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            full = json.load(fh)
        seg = full.get("decision_core", {})
        for k, v in defaults.items():
            if k not in seg or seg[k] is None:
                seg[k] = v
        return seg
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return defaults


# --------------------------------------------------------------------------- #
# 子系统导入（rules-0 §四-12 上下文保护：进程内调用 + Mock 替身）
# --------------------------------------------------------------------------- #


def _import_multimodal_pipeline():
    """导入 MultimodalPipeline（进程内调用）。

    优先使用真实实现 (modules.模块8_多模态管线)。
    若真实实现不可用（如循环依赖、未实现），回退到预生成 Mock。

    Returns:
        MultimodalPipeline 类
    """
    try:
        from modules.模块8_多模态管线 import MultimodalPipeline

        return MultimodalPipeline
    except Exception:
        from public.pre_generated_mock.mock_multimodal_pipeline import (
            MockMultimodalPipeline as MultimodalPipeline,
        )

        return MultimodalPipeline


def _import_template_engine():
    """导入 TemplateEngine（进程内调用）。

    优先使用真实实现 (modules.模块7_模板引擎)。
    若真实实现不可用，回退到预生成 Mock。

    Returns:
        TemplateEngine 类
    """
    try:
        from modules.模块7_模板引擎 import TemplateEngine

        return TemplateEngine
    except Exception:
        from public.pre_generated_mock.mock_template_engine import (
            MockTemplateEngine as TemplateEngine,
        )

        return TemplateEngine


def _import_decision_core():
    """导入 DecisionCore。

    Task 5 尚未实现，使用预生成 Mock。
    真实实现就位后，切换导入路径即可。

    Returns:
        DecisionCore 类（当前为 MockDecisionCore）
    """
    # Task 5 未实现，使用 Mock（rules-0 §四-12 Mock 替身）
    from public.pre_generated_mock.mock_decision_core import (
        DecisionInput,
        FinalDecision,
        MockDecisionCore as DecisionCore,
        RubricSnapshot,
        StorageDecision,
    )

    return DecisionCore, RubricSnapshot, DecisionInput, FinalDecision, StorageDecision


# --------------------------------------------------------------------------- #
# DistillationService 主类
# --------------------------------------------------------------------------- #


class DistillationService:
    """DistillationService 实现。

    独立 FastAPI 子服务（端口 8011），承载 7 状态机多轮蒸馏工作流。
    与主后端（8001）通过 HTTP REST API 通信。

    公开方法签名严格匹配 public/interface_stub/distillation_service.pyi。
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        multimodal_pipeline: Optional[Any] = None,
        template_engine: Optional[Any] = None,
        decision_core: Optional[Any] = None,
    ) -> None:
        """初始化 DistillationService。

        Args:
            config: 配置字典（None 时从 radix_config.json 加载）
            multimodal_pipeline: MultimodalPipeline 实例（None 时自动实例化）
            template_engine: TemplateEngine 实例（None 时自动实例化）
            decision_core: DecisionCore 实例（None 时使用 Mock）
        """
        # 配置加载
        self._config: Dict[str, Any] = (
            config if config is not None else _load_distillation_config()
        )
        # auto_init: data 补全
        self._session_dir = self._resolve_path(
            self._config.get("session_storage_dir", "data/distillation_sessions")
        )
        self._log_dir = self._resolve_path(
            self._config.get("log_storage_dir", "data/distillation_logs")
        )
        _ensure_dir(self._session_dir)
        _ensure_dir(self._log_dir)

        # 子系统实例化
        if multimodal_pipeline is not None:
            self._multimodal_pipeline = multimodal_pipeline
        else:
            mp_cls = _import_multimodal_pipeline()
            try:
                self._multimodal_pipeline = mp_cls()
            except Exception:
                # best-effort：实例化失败时设为 None，调用时再降级
                self._multimodal_pipeline = None

        if template_engine is not None:
            self._template_engine = template_engine
        else:
            te_cls = _import_template_engine()
            try:
                self._template_engine = te_cls()
            except Exception:
                self._template_engine = None

        if decision_core is not None:
            self._decision_core = decision_core
        else:
            dc_classes = _import_decision_core()
            dc_cls = dc_classes[0]
            self._decision_core = dc_cls()

        # 内置 rubric（从 decision_core 配置加载）
        self._decision_core_config = _load_decision_core_config()
        self._rubric = self._build_default_rubric()

        # 内存态 session 索引（持久化层的缓存，提升查询性能）
        self._sessions_cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # 公开 API（严格匹配 .pyi 签名）
    # ------------------------------------------------------------------ #

    async def start_distillation(
        self,
        source_type: str,
        source_ref: Optional[str],
        template_id: str,
        max_turns: int,
        ask_user_on_ambiguity: bool,
    ) -> StartDistillationResponse:
        """启动蒸馏会话。

        异步触发 MultimodalPipeline 预处理，session 进入 S_PREREAD 状态。

        Args:
            source_type: 数据源类型（text/character_card/image/conversation_log）
            source_ref: 数据源引用（文件路径/URL/文本 hash）
            template_id: 关联模板 ID
            max_turns: 最大轮次（1-6）
            ask_user_on_ambiguity: 是否主动追问

        Returns:
            StartDistillationResponse: session_id + initial_state + preread_summary

        Raises:
            ValueError: source_type 不在枚举中 / max_turns 超出范围（422）
            RuntimeError: MultimodalPipeline 预处理失败（422）
            ConnectionError: MultimodalPipeline 不可用（500）
        """
        # 参数校验（422）
        if source_type not in _SOURCE_TYPES:
            raise ValueError(
                f"source_type 不在枚举中（422）: {source_type}"
            )
        if not (1 <= max_turns <= 6):
            raise ValueError(
                f"max_turns 超出范围 1-6（422）: {max_turns}"
            )
        if not template_id:
            raise ValueError("template_id 不能为空（422）")

        session_id = _new_uuid()
        now = _iso_now()

        # 调用 MultimodalPipeline 预处理（S_PREREAD）
        preread_summary, ambiguity_questions = await self._run_preread(
            source_type, source_ref, template_id
        )

        # 构造 session（符合 distillation_session.schema.json）
        session: Dict[str, Any] = {
            "session_id": session_id,
            "source_type": source_type,
            "source_ref": source_ref,
            "state": "S_PREREAD",
            "template_id": template_id,
            "max_turns": max_turns,
            "ask_user_on_ambiguity": ask_user_on_ambiguity,
            "turns": [
                {
                    "turn_index": 0,
                    "state": "S_INIT",
                    "agent_action": "proceed",
                    "agent_output": "[DistillationService] 初始化会话",
                    "user_response": None,
                    "timestamp": now,
                },
                {
                    "turn_index": 1,
                    "state": "S_PREREAD",
                    "agent_action": "proceed",
                    "agent_output": preread_summary,
                    "user_response": None,
                    "timestamp": now,
                },
            ],
            "preread_summary": preread_summary,
            "ambiguity_questions": list(ambiguity_questions),
            "extracted_content": None,
            "quality_score": None,
            "created_at": now,
            "updated_at": now,
            "finalized_at": None,
            "is_finalized": False,
            "error_message": None,
        }

        # 持久化 + 缓存
        self._save_session(session)
        self._sessions_cache[session_id] = session

        return StartDistillationResponse(
            session_id=session_id,
            initial_state="S_PREREAD",
            preread_summary=preread_summary,
        )

    async def advance_distillation(
        self,
        session_id: str,
        user_response: Optional[str],
    ) -> AdvanceDistillationResponse:
        """推进蒸馏状态机一步。

        支持回环（S_REFLECT → S_QUESTION）和主动追问（ask_user_on_ambiguity=True）。

        Args:
            session_id: 会话 ID
            user_response: 用户对 ask_user 的响应（如无则为 None）

        Returns:
            AdvanceDistillationResponse: session_id + current_state + agent_action + next_needed

        Raises:
            KeyError: session_id 不存在（404）
            ValueError: 非法状态转移 / 会话已终结 / 超过最大轮次（409）
            RuntimeError: LLM 调用失败（500）
        """
        session = self._load_session(session_id)
        if session is None:
            raise KeyError(f"session_id 不存在（404）: {session_id}")
        if session["is_finalized"]:
            raise ValueError(
                f"会话已终结（409）: state={session['state']}"
            )

        current_state = session["state"]
        current_turn_index = len(session["turns"])

        # 推进策略（按当前状态决策下一步动作）
        if current_state == "S_PREREAD":
            # 疑点清单非空 + ask_user_on_ambiguity=True → 主动追问
            if (
                session["ambiguity_questions"]
                and session["ask_user_on_ambiguity"]
                and not user_response
            ):
                action = "ask_user"
                next_state = self._transition_state(current_state, action)
                next_needed = True
                agent_output = "[DistillationService] 疑点待澄清，请用户响应: " + "; ".join(
                    session["ambiguity_questions"]
                )
            else:
                action = "proceed"
                next_state = self._transition_state(current_state, action)
                next_needed = False
                agent_output = "[DistillationService] 进入 S_QUESTION 状态"

        elif current_state == "S_QUESTION":
            # ask_user_on_ambiguity=True 且用户未答复 → 继续追问
            if (
                session["ask_user_on_ambiguity"]
                and session["ambiguity_questions"]
                and not user_response
            ):
                action = "ask_user"
                next_state = self._transition_state(current_state, action)
                next_needed = True
                agent_output = "[DistillationService] 等待用户响应"
            else:
                action = "proceed"
                next_state = self._transition_state(current_state, action)
                next_needed = False
                agent_output = "[DistillationService] 进入 S_REFLECT 状态"

        elif current_state == "S_REFLECT":
            # D4_REDISTILL 决策：是否回环至 S_QUESTION
            # 受 max_redistill_turns 限制，且总轮次不得超过 max_turns
            redistill_count = self._count_redistill_turns(session)
            max_redistill = self._rubric.get("max_redistill_turns", 2)
            can_redistill = (
                redistill_count < max_redistill
                and current_turn_index < session["max_turns"]
            )
            if can_redistill:
                action = "reflect"
                next_state = self._transition_state(current_state, action)
                next_needed = True
                agent_output = (
                    f"[DistillationService] D4 决策回环至 S_QUESTION "
                    f"(redistill_count={redistill_count + 1}, "
                    f"max_redistill_turns={max_redistill})"
                )
            else:
                action = "proceed"
                next_state = self._transition_state(current_state, action)
                next_needed = False
                agent_output = (
                    f"[DistillationService] D4 决策不回环，进入 S_CROSSVALIDATE "
                    f"(redistill_count={redistill_count}, "
                    f"max_redistill_turns={max_redistill})"
                )

        elif current_state == "S_CROSSVALIDATE":
            # D5_CROSS_VALIDATE 决策：是否跨源验证
            # 此处简化：如果 rubric.cross_validate_sources 非空则触发
            cross_sources = self._rubric.get("cross_validate_sources", [])
            if cross_sources:
                action = "cross_validate"
                next_state = self._transition_state(current_state, action)
                agent_output = (
                    f"[DistillationService] D5 跨源验证 sources={cross_sources}"
                )
            else:
                action = "proceed"
                next_state = self._transition_state(current_state, action)
                agent_output = "[DistillationService] 跳过跨源验证"
            next_needed = False

        elif current_state == "S_EXTRACT":
            # 抽取结构化内容
            action = "extract"
            next_state = self._transition_state(current_state, action)
            next_needed = False
            extracted = self._extract_content(session)
            session["extracted_content"] = extracted
            agent_output = f"[DistillationService] 抽取结果: {extracted[:200]}..."

            # 改进3：S_EXTRACT 阶段检测 needs_more_context（仅批量蒸馏时）
            # 启发式预筛 + LLM 确认，避免单 chunk 蒸馏无意义的 LLM 调用
            boundary_ctx = session.get("chunk_boundary_context") or {}
            if boundary_ctx and (boundary_ctx.get("prev_tail") or boundary_ctx.get("next_head")):
                try:
                    needs_more = await self._check_needs_more_context(
                        source_ref=session.get("source_ref", ""),
                        extracted_content=extracted,
                        boundary_ctx=boundary_ctx,
                    )
                    session["needs_more_context"] = needs_more
                    if needs_more:
                        # 改进3：若需要更多上下文，立即从 chunk_boundary_context 构造 extra_context
                        prev_tail = boundary_ctx.get("prev_tail", "")
                        next_head = boundary_ctx.get("next_head", "")
                        parts = []
                        if prev_tail:
                            parts.append(f"[前一片段尾部上下文]\n{prev_tail}")
                        if next_head:
                            parts.append(f"[后一片段头部上下文]\n{next_head}")
                        session["extra_context"] = "\n\n".join(parts)
                        # 将 extra_context 合并到 extracted_content，供后续状态机使用
                        extracted = (
                            extracted
                            + "\n\n[改进3] 相邻片段边界上下文（已补充）：\n"
                            + session["extra_context"]
                        )
                        session["extracted_content"] = extracted
                        agent_output += (
                            f"\n[改进3] 检测到语义可能截断，已注入相邻片段边界上下文 "
                            f"(prev_tail={len(prev_tail)} chars, next_head={len(next_head)} chars)"
                        )
                        logger.info(
                            f"S_EXTRACT needs_more_context=True (session={session_id}): "
                            f"已注入边界上下文"
                        )
                except Exception as e:
                    logger.warning(f"needs_more_context 检测失败 (session={session_id}): {e}")
                    session["needs_more_context"] = False

        elif current_state == "S_STORAGE_DECISION":
            # D1_LOCATION / D6_REJECT 决策
            # 此处简化：根据 preread_summary 推断 quality_score
            quality_score = self._estimate_quality_score(session)
            session["quality_score"] = quality_score
            reject_threshold = self._rubric.get("quality_reject_threshold", 0.3)
            if quality_score < reject_threshold:
                action = "reject"
                next_state = self._transition_state(current_state, action)
                agent_output = (
                    f"[DistillationService] D6 拒绝存储 "
                    f"(quality_score={quality_score} < {reject_threshold})"
                )
            else:
                action = "decide"
                next_state = self._transition_state(current_state, action)
                agent_output = (
                    f"[DistillationService] D1 决策存储位置 "
                    f"(quality_score={quality_score})"
                )
            next_needed = False

        else:
            raise ValueError(
                f"非法状态转移（409）: current_state={current_state}"
            )

        # 记录新轮次
        now = _iso_now()
        session["state"] = next_state
        session["updated_at"] = now
        # 终态时设置 finalized_at + is_finalized
        # 仅 S_REJECT 在 advance 中设置 is_finalized（拒绝路径，无需记忆存储）
        # S_FINALIZE 不在此处设置 is_finalized，留给 finalize_distillation 执行记忆存储后设置
        if next_state == "S_REJECT":
            session["is_finalized"] = True
            session["finalized_at"] = now

        session["turns"].append(
            {
                "turn_index": len(session["turns"]),
                "state": next_state,
                "agent_action": action,
                "agent_output": agent_output,
                "user_response": user_response,
                "timestamp": now,
            }
        )

        # 持久化 + 缓存更新
        self._save_session(session)
        self._sessions_cache[session_id] = session

        return AdvanceDistillationResponse(
            session_id=session_id,
            current_state=next_state,
            agent_action=action,
            next_needed=next_needed,
        )

    async def finalize_distillation(
        self,
        session_id: str,
        override_decision: Optional[str],
    ) -> FinalizeDistillationResponse:
        """终结蒸馏会话，执行存储决策。

        调用 DecisionCore 执行 6 决策点，返回存储结果。

        Args:
            session_id: 会话 ID
            override_decision: 人类覆盖决策（非 None 时覆盖 agent 决策）

        Returns:
            FinalizeDistillationResponse: stored + location + memory_id + metadata + reason

        Raises:
            KeyError: session_id 不存在（404）
            ValueError: 会话已终结（409）
            RuntimeError: DecisionCore 决策失败 / 审计日志写入失败（500）
        """
        session = self._load_session(session_id)
        if session is None:
            raise KeyError(f"session_id 不存在（404）: {session_id}")
        if session["is_finalized"]:
            raise ValueError("会话已终结（409）")

        # 调用 DecisionCore 决策（best-effort，失败时降级到内置规则）
        quality_score = session.get("quality_score")
        if quality_score is None:
            quality_score = self._estimate_quality_score(session)
            session["quality_score"] = quality_score

        location, memory_id, metadata, reason = self._invoke_decision_core(
            session=session,
            quality_score=quality_score,
            override_decision=override_decision,
        )

        # 记忆蒸馏注入：当 session 指定 target_agent_id 且 location 非 rejected 时，
        # 调用后端 POST /api/memories 将 extracted_content 真实写入指定 agent 的记忆库
        target_agent_id = session.get("target_agent_id")
        if target_agent_id and location != "rejected":
            extracted_content = session.get("extracted_content") or ""
            inject_result = await self._inject_memory_to_agent(
                target_agent_id=target_agent_id,
                extracted_content=extracted_content,
                session_id=session_id,
                quality_score=quality_score,
            )
            metadata["target_agent_id"] = target_agent_id
            if inject_result["success"]:
                # 覆盖 MockDecisionCore 分配的 fake id 为真实 memory_id
                memory_id = inject_result["memory_id"]
                metadata["injected_to_agent"] = True
                metadata["real_memory_id"] = memory_id
                reason = (
                    f"{reason}；已注入 agent={target_agent_id} "
                    f"memory_id={memory_id}"
                )
            else:
                metadata["injected_to_agent"] = False
                metadata["inject_error"] = inject_result.get("error", "")
                logger.warning(
                    f"记忆注入 agent 失败 (session={session_id}): "
                    f"{inject_result.get('error')}"
                )

        # 更新 session 状态
        now = _iso_now()
        session["state"] = "S_REJECT" if location == "rejected" else "S_FINALIZE"
        session["is_finalized"] = True
        session["finalized_at"] = now
        session["updated_at"] = now
        session["turns"].append(
            {
                "turn_index": len(session["turns"]),
                "state": session["state"],
                "agent_action": "reject" if location == "rejected" else "finalize",
                "agent_output": reason,
                "user_response": override_decision,
                "timestamp": now,
            }
        )

        # 持久化
        self._save_session(session)
        self._sessions_cache[session_id] = session

        stored = location != "rejected"
        return FinalizeDistillationResponse(
            stored=stored,
            location=location,
            memory_id=memory_id,
            metadata=metadata,
            reason=reason,
        )

    async def get_session_status(self, session_id: str) -> SessionStatusResponse:
        """查询会话状态。

        Args:
            session_id: 会话 ID

        Returns:
            SessionStatusResponse: 完整会话状态

        Raises:
            KeyError: session_id 不存在（404）
        """
        session = self._load_session(session_id)
        if session is None:
            raise KeyError(f"session_id 不存在（404）: {session_id}")

        return SessionStatusResponse(
            session_id=session["session_id"],
            source_type=session["source_type"],
            state=session["state"],
            template_id=session["template_id"],
            max_turns=session["max_turns"],
            ask_user_on_ambiguity=session["ask_user_on_ambiguity"],
            turns=list(session["turns"]),
            preread_summary=session["preread_summary"],
            ambiguity_questions=list(session["ambiguity_questions"]),
            extracted_content=session["extracted_content"],
            quality_score=session["quality_score"],
            created_at=session["created_at"],
            updated_at=session["updated_at"],
            finalized_at=session["finalized_at"],
            is_finalized=session["is_finalized"],
            error_message=session["error_message"],
        )

    # ------------------------------------------------------------------ #
    # RADIX-Lite v1.3.0 扩展：批量切分 + agent 创建蒸馏
    # ------------------------------------------------------------------ #

    async def start_batch_distillation(
        self,
        source_type: str,
        source_ref: str,
        template_id: str,
        max_turns: int,
        ask_user_on_ambiguity: bool,
        chunk_size: int = 4000,
        distillation_goal: str = "memory",
        target_agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """批量切分启动蒸馏会话。

        将超长 source_ref 按 chunk_size 切分为多个片段，每个片段创建独立 session，
        归属同一 session_group_id。串行蒸馏（一个 chunk 完成后启动下一个）。

        Args:
            source_type: 数据源类型（text/character_card/image/conversation_log）
            source_ref: 超长文本内容
            template_id: 模板 ID
            max_turns: 最大轮次（1-6）
            ask_user_on_ambiguity: 是否主动追问
            chunk_size: 切分大小（token 估算，默认 4000）
            distillation_goal: 蒸馏目标（memory / agent / memory_and_agent）

        Returns:
            dict: session_group_id + sessions 数组 + total_chunks

        Raises:
            ValueError: 参数无效（422）
        """
        if source_type not in _SOURCE_TYPES:
            raise ValueError(f"source_type 不在枚举中（422）: {source_type}")
        if not (1 <= max_turns <= 6):
            raise ValueError(f"max_turns 超出范围 1-6（422）: {max_turns}")
        if not template_id:
            raise ValueError("template_id 不能为空（422）")
        if not source_ref:
            raise ValueError("source_ref 不能为空（422）")
        if chunk_size < 500:
            chunk_size = 500
        if distillation_goal not in ("memory", "agent", "memory_and_agent"):
            raise ValueError(
                f"distillation_goal 不在枚举中（422）: {distillation_goal}"
            )

        # 改进3：切分时应用重叠窗口（默认 200 字符），保证相邻 chunk 上下文连续
        overlap_size = 200
        # 先用 overlap_size=0 切分得到原始 chunks（用于构造 boundary_context）
        raw_chunks = self._split_text_into_chunks(source_ref, chunk_size, overlap_size=0)
        # 构造每个 chunk 的相邻边界上下文（用于 needs_more_context 时补充）
        boundary_contexts = self._build_chunk_boundary_context(raw_chunks)
        # 再用 overlap_size=200 切分得到带重叠窗口的 chunks（用于实际蒸馏）
        chunks = self._split_text_into_chunks(
            source_ref, chunk_size, overlap_size=overlap_size
        )
        session_group_id = _new_uuid()
        sessions = []

        for idx, chunk in enumerate(chunks):
            start_resp = await self.start_distillation(
                source_type=source_type,
                source_ref=chunk,
                template_id=template_id,
                max_turns=max_turns,
                ask_user_on_ambiguity=ask_user_on_ambiguity,
            )
            # 在 session 中注入 group 信息
            session = self._load_session(start_resp.session_id)
            if session is not None:
                session["session_group_id"] = session_group_id
                session["chunk_index"] = idx
                session["distillation_goal"] = distillation_goal
                session["target_agent_id"] = target_agent_id
                # 改进3：存入 chunk_boundary_context（相邻 chunk 边界文本，用于 needs_more_context 补充）
                session["chunk_boundary_context"] = (
                    boundary_contexts[idx] if idx < len(boundary_contexts) else {}
                )
                session["needs_more_context"] = False  # 初始化为 False，S_EXTRACT 阶段可能更新
                session["extra_context"] = ""  # 初始化为空，needs_more_context 时填充
                self._save_session(session)
                self._sessions_cache[start_resp.session_id] = session

            sessions.append(
                {
                    "session_id": start_resp.session_id,
                    "chunk_index": idx,
                    "initial_state": start_resp.initial_state,
                    "preread_summary": start_resp.preread_summary,
                }
            )

        return {
            "session_group_id": session_group_id,
            "sessions": sessions,
            "total_chunks": len(chunks),
            "distillation_goal": distillation_goal,
        }

    async def get_group_status(self, group_id: str) -> Dict[str, Any]:
        """查询批量切分组状态。

        Args:
            group_id: 会话组 ID

        Returns:
            dict: group_id + sessions 状态数组 + completed_count + total_count

        Raises:
            KeyError: group_id 不存在（404）
        """
        sessions_in_group = []
        for sid, session in self._sessions_cache.items():
            if session.get("session_group_id") == group_id:
                sessions_in_group.append(session)

        if not sessions_in_group:
            raise KeyError(f"session_group_id 不存在（404）: {group_id}")

        sessions_in_group.sort(key=lambda s: s.get("chunk_index", 0))
        completed = sum(1 for s in sessions_in_group if s.get("is_finalized"))

        return {
            "session_group_id": group_id,
            "total_count": len(sessions_in_group),
            "completed_count": completed,
            "sessions": [
                {
                    "session_id": s["session_id"],
                    "chunk_index": s.get("chunk_index", 0),
                    "state": s["state"],
                    "is_finalized": s.get("is_finalized", False),
                    "quality_score": s.get("quality_score"),
                    "extracted_content": s.get("extracted_content"),
                }
                for s in sessions_in_group
            ],
        }

    async def finalize_with_agent_creation(
        self,
        session_id: str,
        override_decision: Optional[str] = None,
    ) -> Dict[str, Any]:
        """终结蒸馏会话并创建 agent（可选同时注入记忆）。

        根据 session 的 distillation_goal：
        - memory_and_agent: 先创建 agent，然后将记忆注入到新创建的 agent（无需用户选择）
        - agent: 仅创建 agent，不注入记忆

        注意：memory_and_agent 时前端不传 target_agent_id，finalize_distillation
        不会注入记忆；记忆注入在 agent 创建后，用新 agent_id 自动注入。

        Args:
            session_id: 会话 ID
            override_decision: 人类覆盖决策

        Returns:
            dict: finalize 响应 + agent_creation_result

        Raises:
            KeyError: session_id 不存在（404）
            ValueError: 会话已终结（409）
            RuntimeError: agent 创建失败（500）
        """
        # 先从 session 加载 extracted_content + distillation_goal（finalize 后 session 会被更新，需提前取）
        session = self._load_session(session_id)
        if session is None:
            raise KeyError(f"session_id 不存在（404）: {session_id}")
        if session["is_finalized"]:
            raise ValueError("会话已终结（409）")
        extracted_content = session.get("extracted_content") or ""
        distillation_goal = session.get("distillation_goal", "agent")
        chunk_index = session.get("chunk_index")  # 用于时间推测（改进2）

        # 先执行常规 finalize（记忆存储路径）
        # memory_and_agent 时 session 无 target_agent_id，finalize_distillation 不会注入记忆
        # 记忆注入在 agent 创建后用新 agent_id 自动注入
        finalize_resp = await self.finalize_distillation(
            session_id=session_id,
            override_decision=override_decision,
        )

        # 创建 agent（LLM 生成 profile + 调用 createAgent API）
        # best-effort：失败不影响 finalize 响应，仅记录 agent_creation_result
        try:
            agent_creation_result = await self._create_agent_from_extraction(
                session_id=session_id,
                extracted_content=extracted_content,
            )
            logger.info(
                f"finalize_with_agent_creation: agent_creation_result success={agent_creation_result.get('success')}, "
                f"agent_id={agent_creation_result.get('agent_id')}, goal={distillation_goal}"
            )
        except Exception as e:
            logger.exception(f"_create_agent_from_extraction 未预期异常: {e}")
            agent_creation_result = {
                "success": False,
                "error": f"未预期异常: {e}",
                "agent_id": None,
            }

        # memory_and_agent: 将记忆注入到新创建的 agent
        # best-effort：注入失败不影响 finalize 响应
        if (
            distillation_goal == "memory_and_agent"
            and finalize_resp.location != "rejected"
            and agent_creation_result.get("success")
            and agent_creation_result.get("agent_id")
        ):
            try:
                # 从 finalize_resp.metadata 取 quality_score（用于估算 importance）
                quality_score = (
                    finalize_resp.metadata.get("quality_score", 0.5)
                    if isinstance(finalize_resp.metadata, dict)
                    else 0.5
                )
                new_agent_id = agent_creation_result["agent_id"]
                # 改进2：提取时间标记（正则 → LLM → chunk_index 推测）
                # best-effort：失败时使用 chunk_index 推测，不阻断注入
                try:
                    time_marker = await self._extract_time_marker(
                        extracted_content=extracted_content,
                        chunk_index=chunk_index,
                    )
                    logger.info(
                        f"时间标记提取 (session={session_id}): "
                        f"has_time={time_marker['has_time']}, "
                        f"inferred={time_marker['is_inferred']}"
                    )
                except Exception as e:
                    logger.warning(f"时间标记提取失败，使用 fallback: {e}")
                    time_marker = self._infer_timestamp_by_chunk(chunk_index)

                inject_result = await self._inject_memory_to_agent(
                    target_agent_id=new_agent_id,
                    extracted_content=extracted_content,
                    session_id=session_id,
                    quality_score=quality_score,
                    character_card=agent_creation_result.get("character_card"),
                    time_marker=time_marker,
                )
                agent_creation_result["memory_injection"] = inject_result
                if inject_result["success"]:
                    if isinstance(finalize_resp.metadata, dict):
                        finalize_resp.metadata["injected_to_new_agent"] = True
                        finalize_resp.metadata["new_agent_id"] = new_agent_id
                        finalize_resp.metadata["real_memory_id"] = inject_result["memory_id"]
                    finalize_resp.reason = (
                        f"{finalize_resp.reason}；已注入新创建的 agent={new_agent_id} "
                        f"memory_id={inject_result['memory_id']}"
                    )
                    logger.info(
                        f"记忆注入新创建的 agent 成功 (session={session_id}): "
                        f"agent={new_agent_id} memory_id={inject_result['memory_id']}"
                    )
                else:
                    if isinstance(finalize_resp.metadata, dict):
                        finalize_resp.metadata["injected_to_new_agent"] = False
                        finalize_resp.metadata["inject_error"] = inject_result.get("error", "")
                    logger.warning(
                        f"记忆注入新创建的 agent 失败 (session={session_id}): "
                        f"{inject_result.get('error')}"
                    )
            except Exception as e:
                logger.exception(f"记忆注入未预期异常: {e}")
                agent_creation_result["memory_injection"] = {
                    "success": False,
                    "error": f"未预期异常: {e}",
                    "memory_id": None,
                }

        return {
            "stored": finalize_resp.stored,
            "location": finalize_resp.location,
            "memory_id": finalize_resp.memory_id,
            "metadata": finalize_resp.metadata,
            "reason": finalize_resp.reason,
            "agent_creation_result": agent_creation_result,
        }

    async def _inject_memory_to_agent(
        self,
        target_agent_id: str,
        extracted_content: str,
        session_id: str,
        quality_score: float,
        character_card: Optional[Dict[str, str]] = None,
        time_marker: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """将蒸馏抽取的内容注入到指定 agent 的记忆库。

        通过调用后端 POST /api/memories API 写入真实记忆，agent_id 关联目标 agent。
        best-effort：失败时返回 success=False，不阻断 finalize 流程。

        若 character_card 非空，将 first_mes / mes_example 作为带标签的独立记忆
        单独存储，便于后续角色卡场景识别（SillyTavern 角色卡标准字段）。
        personality / scenario 不单独存储，因 system_prompt 已含相关信息。

        若 time_marker 非空，将时间信息写入 metadata：
            - has_time=True 且 is_inferred=False → metadata.original_timestamp
            - has_time=True 且 is_inferred=True  → metadata.original_timestamp + inferred=True
            - has_time=False → metadata.inferred_timestamp + inferred=True

        Args:
            target_agent_id: 目标 agent ID
            extracted_content: 蒸馏抽取的内容
            session_id: 蒸馏会话 ID（用于 metadata 追溯）
            quality_score: 质量评分（用于 importance 估算）
            character_card: 角色卡字段（first_mes/mes_example/personality/scenario）
            time_marker: 时间标记信息（has_time/timestamp/is_inferred）

        Returns:
            dict: success + memory_id（主记忆 ID）+ error + extra_memories（角色卡字段记忆列表）
        """
        if not extracted_content:
            return {
                "success": False,
                "error": "extracted_content 为空，跳过注入",
                "memory_id": None,
                "extra_memories": [],
            }

        try:
            import httpx

            backend_url = self._config.get("main_backend_url", "http://127.0.0.1:8001")
            # importance 由 quality_score 估算（0-1 → 1-5）
            importance = max(1, min(5, int(round(quality_score * 5))))

            # 构造时间相关 metadata（改进2：时间感知记忆存储）
            time_meta = self._build_time_metadata(time_marker)

            base_metadata = {
                "source": "distillation_service",
                "session_id": session_id,
                "quality_score": quality_score,
                "injected_by": "finalize_distillation",
            }
            base_metadata.update(time_meta)

            memory_payload = {
                "content": extracted_content,
                "type": "long_term",
                "importance": importance,
                "tags": ["distillation", "radix-lite"],
                "metadata": base_metadata,
                "permanent": False,
                "workspace_id": "default",
                "agent_id": target_agent_id,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{backend_url}/api/memories",
                    json=memory_payload,
                )
                resp.raise_for_status()
                data = resp.json()

            real_memory_id = data.get("memory_id")
            extra_memories: List[Dict[str, Any]] = []

            # 角色卡字段单独存储（first_mes / mes_example）
            # 用 tag 区分角色卡字段类型，便于后续检索
            if character_card:
                card_fields = [
                    ("first_mes", "character_card_first_mes", "角色卡首条开场白"),
                    ("mes_example", "character_card_mes_example", "角色卡对话示例"),
                ]
                for field_key, tag, label in card_fields:
                    field_value = (character_card.get(field_key) or "").strip()
                    if not field_value:
                        continue
                    card_metadata = {
                        "source": "distillation_service",
                        "session_id": session_id,
                        "field_key": field_key,
                        "label": label,
                        "injected_by": "finalize_distillation",
                    }
                    card_metadata.update(time_meta)
                    card_payload = {
                        "content": field_value,
                        "type": "long_term",
                        "importance": max(importance, 4),  # 角色卡字段重要性较高
                        "tags": ["distillation", "radix-lite", tag, "character_card"],
                        "metadata": card_metadata,
                        "permanent": False,
                        "workspace_id": "default",
                        "agent_id": target_agent_id,
                    }
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            card_resp = await client.post(
                                f"{backend_url}/api/memories",
                                json=card_payload,
                            )
                            card_resp.raise_for_status()
                            card_data = card_resp.json()
                        extra_memories.append({
                            "field": field_key,
                            "tag": tag,
                            "memory_id": card_data.get("memory_id"),
                            "success": True,
                        })
                    except Exception as e:
                        logger.warning(
                            f"角色卡字段 {field_key} 单独存储失败 (session={session_id}): {e}"
                        )
                        extra_memories.append({
                            "field": field_key,
                            "tag": tag,
                            "memory_id": None,
                            "success": False,
                            "error": str(e),
                        })

            return {
                "success": True,
                "memory_id": real_memory_id,
                "error": None,
                "extra_memories": extra_memories,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"调用 /api/memories 失败: {e}",
                "memory_id": None,
                "extra_memories": [],
            }

    @staticmethod
    def _build_time_metadata(time_marker: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """根据时间标记构造 metadata 字段（改进2）。

        规则：
            - has_time=True 且 is_inferred=False → {"original_timestamp": ts}
            - has_time=True 且 is_inferred=True  → {"original_timestamp": ts, "inferred": True}
            - has_time=False → {"inferred_timestamp": ts, "inferred": True}
            - time_marker=None → {} （不写入时间字段，向后兼容）

        Args:
            time_marker: 时间标记字典

        Returns:
            dict: 时间相关 metadata 字段
        """
        if not time_marker:
            return {}
        has_time = bool(time_marker.get("has_time"))
        ts = time_marker.get("timestamp", "")
        inferred = bool(time_marker.get("is_inferred"))
        if not ts:
            return {}
        if has_time and not inferred:
            return {"original_timestamp": ts}
        if has_time and inferred:
            return {"original_timestamp": ts, "inferred": True}
        # has_time=False
        return {"inferred_timestamp": ts, "inferred": True}

    async def _create_agent_from_extraction(
        self,
        session_id: str,
        extracted_content: str,
    ) -> Dict[str, Any]:
        """从蒸馏结果直接创建 agent（不经过角色卡中间步骤）。

        LLM 一次生成 name + description + system_prompt，确保内容干净、语义完整。
        source_type=character_card 场景走独立路径，不经过此方法。

        Args:
            session_id: 蒸馏会话 ID
            extracted_content: 蒸馏抽取的内容

        Returns:
            dict: success + agent_id + agent_name + error
        """
        if not extracted_content:
            return {
                "success": False,
                "error": "extracted_content 为空，无法创建 agent",
                "agent_id": None,
            }

        # LLM 生成 agent profile（含 SillyTavern 角色卡标准字段）
        # profile 字段：name/description/system_prompt/first_mes/mes_example/personality/scenario
        profile = await self._llm_generate_agent_profile(extracted_content)

        # 提取角色卡字段（用于后续作为带标签记忆单独存储）
        character_card = {
            "first_mes": profile.get("first_mes", ""),
            "mes_example": profile.get("mes_example", ""),
            "personality": profile.get("personality", ""),
            "scenario": profile.get("scenario", ""),
        }

        # 调用后端 createAgent API（HTTP 内部调用）
        # name 去重：若 400（名称已存在），追加随机后缀重试一次
        import httpx
        import random
        import string

        backend_url = self._config.get("main_backend_url", "http://127.0.0.1:8001")
        name_candidates = [profile["name"]]
        # 预生成 2 个带后缀的备选 name
        for _ in range(2):
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            name_candidates.append(f"{profile['name']}_{suffix}")

        last_error = ""
        for candidate_name in name_candidates:
            agent_payload = {
                "name": candidate_name,
                "description": profile["description"],
                "system_prompt": profile["system_prompt"],
                "model": "gemma4-e4b",
                "temperature": 0.7,
                "use_memory": True,
                "use_tools": True,
                "memory_scene": "default",
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{backend_url}/api/agents",
                        json=agent_payload,
                    )
                    if resp.status_code == 400:
                        # name 重复，尝试下一个候选
                        last_error = f"createAgent 400: {resp.text}"
                        logger.warning(f"createAgent name 重复，尝试下一个候选: {candidate_name}")
                        continue
                    resp.raise_for_status()
                    agent_data = resp.json()

                # POST /api/agents 返回 {"status": "success", "agent": {"id": ...}, ...}
                # agent_id 嵌套在 agent 子对象中，兼容扁平格式
                agent_obj = agent_data.get("agent") or agent_data
                agent_id = agent_obj.get("id") or agent_obj.get("agent_id")

                logger.info(f"createAgent 成功: name={candidate_name}, agent_id={agent_id}")
                return {
                    "success": True,
                    "agent_id": agent_id,
                    "agent_name": candidate_name,
                    "character_card": character_card,
                }
            except Exception as e:
                last_error = f"createAgent 调用失败: {e}"
                logger.warning(f"createAgent 调用失败 (name={candidate_name}): {e}")
                continue

        return {
            "success": False,
            "error": last_error,
            "agent_id": None,
            "character_card": character_card,
        }

    async def _extract_time_marker(
        self,
        extracted_content: str,
        chunk_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """从蒸馏内容中提取时间标记（改进2：时间感知记忆存储）。

        提取顺序：
        1. 正则匹配绝对时间（如 2024-01-15、2024年1月15日、2024/1/15 10:30）
        2. 若未命中，调用 LLM 提取相对时间（如"昨天"、"上周一"）并转换为绝对时间
        3. 若都未命中，按 chunk_index 推测顺序时间（基准时间 - chunk_index * 偏移）

        Args:
            extracted_content: 蒸馏抽取的内容
            chunk_index: 分块索引（用于无时间标记时推测顺序）

        Returns:
            dict: {has_time: bool, timestamp: str, is_inferred: bool}
                  - has_time: 是否提取到时间标记
                  - timestamp: ISO 8601 格式时间戳（UTC）
                  - is_inferred: 是否为推测时间（True 表示按 chunk_index 推测或 LLM 推断）
        """
        if not extracted_content:
            return self._infer_timestamp_by_chunk(chunk_index)

        # 步骤1：正则匹配绝对时间
        absolute_ts = self._regex_extract_absolute_time(extracted_content)
        if absolute_ts:
            return {
                "has_time": True,
                "timestamp": absolute_ts,
                "is_inferred": False,
            }

        # 步骤2：LLM 提取相对时间（best-effort，失败则进入步骤3）
        try:
            llm_ts = await self._llm_extract_time_marker(extracted_content)
            if llm_ts:
                return {
                    "has_time": True,
                    "timestamp": llm_ts,
                    "is_inferred": True,  # LLM 提取的相对时间标记为推断
                }
        except Exception as e:
            logger.warning(f"LLM 提取时间标记失败，将按 chunk_index 推测: {e}")

        # 步骤3：按 chunk_index 推测
        return self._infer_timestamp_by_chunk(chunk_index)

    @staticmethod
    def _regex_extract_absolute_time(text: str) -> Optional[str]:
        """用正则提取绝对时间标记。

        支持格式：
            - 2024-01-15 / 2024-1-15
            - 2024-01-15 10:30 / 2024-01-15T10:30:00
            - 2024/01/15 / 2024/1/15 10:30
            - 2024年1月15日 / 2024年1月15日 10时30分

        Args:
            text: 待提取的文本

        Returns:
            str: ISO 8601 格式时间戳，未命中返回 None
        """
        patterns = [
            # 2024-01-15 10:30:00 / 2024-01-15T10:30 / 2024-01-15 10:30
            (
                r"(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?",
                "ymd_hms",
            ),
            # 2024/01/15 10:30 / 2024/1/15 10:30:00
            (
                r"(\d{4})/(\d{1,2})/(\d{1,2})[T ](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?",
                "ymd_hms",
            ),
            # 2024年1月15日 10时30分 / 2024年1月15日 10:30
            (
                r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(?:(\d{1,2})[时:](\d{1,2})分?(?::(\d{1,2}))?)?",
                "ymd_hms",
            ),
            # 2024-01-15（仅日期）
            (r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"),
            # 2024/01/15（仅日期）
            (r"(\d{4})/(\d{1,2})/(\d{1,2})", "ymd"),
            # 2024年1月15日（仅日期）
            (r"(\d{4})年(\d{1,2})月(\d{1,2})日", "ymd"),
        ]

        for pattern, ptype in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                if ptype == "ymd_hms" and len(match.groups()) >= 6:
                    hour = int(match.group(4) or 0)
                    minute = int(match.group(5) or 0)
                    second = int(match.group(6) or 0)
                    dt = datetime(
                        year, month, day, hour, minute, second, tzinfo=timezone.utc
                    )
                else:
                    dt = datetime(year, month, day, tzinfo=timezone.utc)
                return dt.isoformat()
            except (ValueError, OverflowError):
                continue

        return None

    @staticmethod
    def _infer_timestamp_by_chunk(chunk_index: Optional[int]) -> Dict[str, Any]:
        """按 chunk_index 推测时间戳（无时间标记时的 fallback）。

        推测规则：基准时间为当前 UTC，按 chunk_index 倒序推测
        （chunk_index=0 为最新，越大越早），每个 chunk 间隔 1 小时。
        单 chunk 蒸馏（chunk_index=None 或 0）使用当前时间。

        Args:
            chunk_index: 分块索引

        Returns:
            dict: {has_time: False, timestamp: str, is_inferred: True}
        """
        now = datetime.now(timezone.utc)
        if chunk_index and chunk_index > 0:
            # 每个 chunk 间隔 1 小时倒序推测
            inferred = now - timedelta(hours=chunk_index)
        else:
            inferred = now
        return {
            "has_time": False,
            "timestamp": inferred.isoformat(),
            "is_inferred": True,
        }

    async def _llm_extract_time_marker(self, extracted_content: str) -> Optional[str]:
        """通过 LLM 提取时间标记（相对时间转绝对时间）。

        best-effort：LLM 调用失败或解析失败返回 None。

        Args:
            extracted_content: 蒸馏抽取的内容

        Returns:
            str: ISO 8601 格式时间戳，未提取到返回 None
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prompt = (
            "请从以下蒸馏内容中提取时间标记。\n"
            "- 如果内容中包含明确的时间（如'2024-01-15'、'昨天'、'上周一'、'3小时前'），"
            f"请将其转换为绝对日期时间（ISO 8601 格式，UTC，参考当前日期：{now_str}）。\n"
            "- 转换示例：'昨天' → 当前日期-1天；'上周一' → 上周一 00:00:00 UTC；"
            "'3小时前' → 当前时间-3小时。\n"
            "- 如果内容中无任何时间标记，请输出空字符串。\n"
            "输出严格的 JSON 格式（不要 markdown 代码块标记）：\n"
            '{"timestamp": "YYYY-MM-DDTHH:MM:SS+00:00"}\n\n'
            f"蒸馏内容：\n{extracted_content[:1000]}"
        )
        try:
            import httpx

            vllm_url = _load_vllm_base_url()
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{vllm_url}/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": 100,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                raw = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
                parsed = json.loads(raw)
                ts = str(parsed.get("timestamp", "")).strip()
                if not ts:
                    return None
                # 校验 ISO 格式
                datetime.fromisoformat(ts)
                return ts
        except Exception as e:
            logger.warning(f"LLM 提取时间标记解析失败: {e}")
            return None

    async def _llm_generate_agent_profile(self, extracted_content: str) -> Dict[str, Any]:
        """通过 LLM 从蒸馏内容生成 agent profile，兼容 SillyTavern 角色卡标准字段。

        输出字段：
            - name: 角色或主题名称（必填）
            - description: 一句话描述（必填）
            - system_prompt: 系统提示词（必填）
            - first_mes: 角色卡首条消息（可选，若内容含则提取）
            - mes_example: 角色卡对话示例（可选，若内容含则提取）
            - personality: 角色性格描述（可选）
            - scenario: 场景描述（可选）

        Args:
            extracted_content: 蒸馏抽取的内容

        Returns:
            dict: {name, description, system_prompt, first_mes, mes_example,
                   personality, scenario}（失败时用默认值，可选字段为空串）
        """
        default_name = f"蒸馏Agent_{datetime.now(timezone.utc).strftime('%H%M%S')}"
        prompt = (
            "请从以下蒸馏内容中提取信息，生成一个 AI Agent 的配置。\n"
            "输出严格的 JSON 格式（不要 markdown 代码块标记），包含以下字段：\n"
            '- "name": 简短的角色或主题名称（不超过10个字，不要引号标点）\n'
            '- "description": 一句话描述这个 Agent 的功能或角色（不超过50个字）\n'
            '- "system_prompt": 完整的系统提示词，定义 Agent 的行为、语气和能力（200-500字）\n'
            '- "first_mes": 角色卡首条开场白（可选；若蒸馏内容包含 first_mes、'
            '"开场白"、"第一条消息"等字段或标记，请直接提取原文；否则填空字符串）\n'
            '- "mes_example": 角色卡对话示例（可选；若蒸馏内容包含 mes_example、'
            '"对话示例"、"对话样本"等字段或标记，请直接提取原文；否则填空字符串）\n'
            '- "personality": 角色性格描述（可选；若蒸馏内容包含 personality、"性格"等字段，'
            '请提取；否则填空字符串）\n'
            '- "scenario": 场景描述（可选；若蒸馏内容包含 scenario、"场景"等字段，'
            '请提取；否则填空字符串）\n\n'
            "规则：\n"
            "1. 若蒸馏内容中明确含有 SillyTavern 角色卡标准字段名（first_mes、mes_example、"
            "personality、scenario），请直接提取对应原文，不要改写。\n"
            "2. 若内容不含上述字段名，但能从内容推断出对应信息（如开场白、对话样本），"
            "可适当填写，否则填空字符串。\n"
            "3. 必填字段（name/description/system_prompt）不可为空。\n\n"
            f"蒸馏内容：\n{extracted_content[:1500]}"
        )
        defaults = {
            "name": default_name,
            "description": "由蒸馏内容生成的 Agent",
            "system_prompt": extracted_content[:500],
            "first_mes": "",
            "mes_example": "",
            "personality": "",
            "scenario": "",
        }
        try:
            import httpx

            vllm_url = _load_vllm_base_url()
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{vllm_url}/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 1200,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                raw = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                # 清理 markdown 代码块标记
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
                parsed = json.loads(raw)
                # 字段校验（必填字段 + 可选角色卡字段）
                name = str(parsed.get("name", "")).strip()[:20]
                description = str(parsed.get("description", "")).strip()[:100]
                system_prompt = str(parsed.get("system_prompt", "")).strip()
                # 角色卡可选字段（空值兜底为空串，保持类型一致）
                first_mes = str(parsed.get("first_mes", "") or "").strip()
                mes_example = str(parsed.get("mes_example", "") or "").strip()
                personality = str(parsed.get("personality", "") or "").strip()
                scenario = str(parsed.get("scenario", "") or "").strip()
                return {
                    "name": name if name else defaults["name"],
                    "description": description if description else defaults["description"],
                    "system_prompt": system_prompt if system_prompt else defaults["system_prompt"],
                    "first_mes": first_mes,
                    "mes_example": mes_example,
                    "personality": personality,
                    "scenario": scenario,
                }
        except Exception as e:
            logger.warning(f"LLM 生成 agent profile 失败，使用默认值: {e}")
            return defaults

    async def _llm_extract_character_card(
        self, extracted_content: str
    ) -> Dict[str, Any]:
        """通过 LLM 从蒸馏内容提取角色卡 6 字段。

        使用后端 LLM 客户端调用主模型，提示词引导 LLM 输出 JSON 格式角色卡字段。
        best-effort：LLM 调用失败或 JSON 解析失败时返回默认空字段。

        Args:
            extracted_content: 蒸馏抽取的内容

        Returns:
            dict: 角色卡 6 字段（name/description/personality/scenario/first_mes/mes_example）
        """
        default_card = {
            "name": "",
            "description": "",
            "personality": "",
            "scenario": "",
            "first_mes": "",
            "mes_example": "",
        }

        prompt = f"""请从以下蒸馏内容中提取角色卡字段，返回 JSON 格式（仅含字段，无其他内容）：

{{
  "name": "角色名称",
  "description": "角色描述",
  "personality": "性格特征",
  "scenario": "场景设定",
  "first_mes": "开场白",
  "mes_example": "对话示例"
}}

蒸馏内容：
{extracted_content[:3000]}
"""
        try:
            import httpx

            vllm_url = _load_vllm_base_url()
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{vllm_url}/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2000,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

            # 从 LLM 响应中提取 JSON
            import re as _re

            json_match = _re.search(r"\{[^{}]*\}", content, _re.DOTALL)
            if json_match:
                card = json.loads(json_match.group(0))
                # 标准化字段（补默认值）
                for k, v in default_card.items():
                    if k not in card or not card[k]:
                        card[k] = v
                return card

            return default_card
        except Exception as e:
            logger.warning(f"LLM 提取角色卡失败: {e}")
            return default_card

    @staticmethod
    def _build_system_prompt_from_card(card: Dict[str, Any]) -> str:
        """从角色卡字段构建 agent system_prompt。

        Args:
            card: 角色卡 6 字段

        Returns:
            str: system_prompt 文本
        """
        parts = []
        if card.get("name"):
            parts.append(f"你是 {card['name']}。")
        if card.get("description"):
            parts.append(f"角色描述：{card['description']}")
        if card.get("personality"):
            parts.append(f"性格特征：{card['personality']}")
        if card.get("scenario"):
            parts.append(f"场景设定：{card['scenario']}")
        if card.get("first_mes"):
            parts.append(f"开场白：{card['first_mes']}")
        if card.get("mes_example"):
            parts.append(f"对话示例：{card['mes_example']}")
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _split_text_into_chunks(
        text: str, chunk_size: int, overlap_size: int = 0
    ) -> List[str]:
        """将超长文本按 chunk_size 切分为多个片段（改进3：支持重叠窗口）。

        切分策略：
        1. 估算 token 数（中文 2 字符/token，英文 4 字符/token，取加权平均）
        2. 按 chunk_size 估算的字符数切分
        3. 优先在段落边界（\\n\\n）切分，其次 \\n，再次句号
        4. 若 overlap_size > 0，相邻 chunk 共享重叠窗口文本：
           chunk[i] 头部包含 chunk[i-1] 尾部 overlap_size 字符，
           保证 LLM 在处理 chunk[i] 时能看到前一 chunk 的边界上下文。

        Args:
            text: 原始文本
            chunk_size: 每个片段的 token 上限
            overlap_size: 相邻 chunk 重叠字符数（默认 0，向后兼容）

        Returns:
            List[str]: 切分后的片段列表（若 overlap_size > 0，除 chunk[0] 外
                       每个 chunk 头部含前一 chunk 尾部重叠文本）
        """
        if not text:
            return []

        # 估算字符/token 比例（混合中英文，取 3 字符/token）
        chars_per_token = 3
        target_chars = chunk_size * chars_per_token

        if len(text) <= target_chars:
            return [text]

        # overlap_size 不能超过 target_chars 的一半
        if overlap_size > target_chars // 2:
            overlap_size = target_chars // 2
        if overlap_size < 0:
            overlap_size = 0

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= target_chars:
                chunks.append(remaining)
                break

            # 在 target_chars 附近寻找最佳切分点
            search_window = remaining[: target_chars + 200]
            split_pos = -1

            # 优先段落边界
            for sep in ["\n\n", "\n", "。", ".", "!", "?", "；", ";"]:
                pos = search_window.rfind(sep)
                if pos > target_chars * 0.5:
                    split_pos = pos + len(sep)
                    break

            if split_pos < 0:
                split_pos = target_chars

            chunks.append(remaining[:split_pos])
            remaining = remaining[split_pos:]

        # 改进3：应用重叠窗口（除 chunk[0] 外，每个 chunk 头部插入前一 chunk 尾部 overlap_size 字符）
        if overlap_size > 0 and len(chunks) > 1:
            overlapped_chunks = [chunks[0]]
            for i in range(1, len(chunks)):
                prev_tail = chunks[i - 1][-overlap_size:]
                # 用分隔标记标识重叠区域，便于 LLM 识别
                overlapped_content = (
                    f"[上下文重叠区开始]\n{prev_tail}\n[上下文重叠区结束]\n"
                    + chunks[i]
                )
                overlapped_chunks.append(overlapped_content)
            return overlapped_chunks

        return chunks

    @staticmethod
    def _build_chunk_boundary_context(
        chunks: List[str], boundary_size: int = 500
    ) -> List[Dict[str, str]]:
        """为每个 chunk 构造相邻 chunk 的边界上下文（改进3）。

        用于 needs_more_context=true 时注入 session.extra_context，
        让 LLM 获取更完整的跨块上下文。

        Args:
            chunks: 切分后的 chunk 列表（未应用 overlap 的原始 chunks）
            boundary_size: 边界文本最大字符数（默认 500）

        Returns:
            List[Dict]: 每个 chunk 对应的边界上下文
                        [{prev_tail, next_head}, ...]
                        chunk[0].prev_tail="" , chunk[-1].next_head=""
        """
        if not chunks:
            return []
        if boundary_size < 0:
            boundary_size = 0

        contexts = []
        for i, _ in enumerate(chunks):
            prev_tail = ""
            next_head = ""
            if i > 0:
                prev_tail = chunks[i - 1][-boundary_size:]
            if i < len(chunks) - 1:
                next_head = chunks[i + 1][:boundary_size]
            contexts.append({"prev_tail": prev_tail, "next_head": next_head})
        return contexts

    # ------------------------------------------------------------------ #
    # 内部方法（严格匹配 .pyi 签名）
    # ------------------------------------------------------------------ #

    def _transition_state(self, current_state: str, agent_action: str) -> str:
        """内部方法：状态机转移。

        Args:
            current_state: 当前状态
            agent_action: agent 动作

        Returns:
            下一个状态

        Raises:
            ValueError: 非法状态转移
        """
        if current_state not in _STATES:
            raise ValueError(f"非法状态（422）: {current_state}")
        if agent_action not in _AGENT_ACTIONS:
            raise ValueError(f"非法 agent_action（422）: {agent_action}")

        transitions = _TRANSITIONS.get(current_state, {})
        next_state = transitions.get(agent_action)
        if next_state is None:
            raise ValueError(
                f"非法状态转移（409）: {current_state} + {agent_action}"
            )
        return next_state

    # ------------------------------------------------------------------ #
    # 私有辅助方法（非 .pyi 范围，内部使用）
    # ------------------------------------------------------------------ #

    def _resolve_path(self, configured: str) -> str:
        """将配置中的相对路径解析为绝对路径。

        Args:
            configured: 配置中的路径（相对或绝对）

        Returns:
            绝对路径
        """
        if os.path.isabs(configured):
            return configured
        return os.path.join(_PROJECT_ROOT, configured.replace("/", os.sep))

    def _build_default_rubric(self) -> Dict[str, Any]:
        """构建默认 rubric 字典。

        Returns:
            Dict[str, Any]: rubric 字典
        """
        cfg = self._decision_core_config
        return {
            "importance_threshold_permanent": cfg.get(
                "importance_threshold_permanent", 0.7
            ),
            "quality_reject_threshold": cfg.get("quality_reject_threshold", 0.3),
            "max_redistill_turns": cfg.get("max_redistill_turns", 2),
            "ask_user_confidence_threshold": cfg.get(
                "ask_user_confidence_threshold", 0.4
            ),
            "cross_validate_sources": cfg.get("cross_validate_sources", []),
        }

    async def _run_preread(
        self,
        source_type: str,
        source_ref: Optional[str],
        template_id: str,
    ) -> tuple:
        """执行 S_PREREAD 阶段：调用 MultimodalPipeline 预处理 + 模板渲染。

        Args:
            source_type: 数据源类型
            source_ref: 数据源引用
            template_id: 关联模板 ID

        Returns:
            (preread_summary, ambiguity_questions) 元组

        Raises:
            RuntimeError: MultimodalPipeline 预处理失败
            ConnectionError: MultimodalPipeline 不可用
        """
        # 调用 MultimodalPipeline 预处理
        artifact_summary = ""
        try:
            if self._multimodal_pipeline is not None:
                # conversation_log 类型映射到 text 模态
                mp_source_type = (
                    "text" if source_type == "conversation_log" else source_type
                )
                ref = source_ref if source_ref else ""
                try:
                    artifact = self._multimodal_pipeline.preprocess(
                        source_type=mp_source_type,
                        source_ref=ref,
                    )
                    # 提取摘要（前 500 字符）
                    text_content = getattr(artifact, "text_content", "")
                    artifact_type = getattr(artifact, "type", mp_source_type)
                    artifact_summary = (
                        f"[MultimodalArtifact type={artifact_type}] "
                        f"{text_content[:500]}"
                    )
                except (ValueError, FileNotFoundError, RuntimeError, ConnectionError):
                    # best-effort：预处理失败时降级到占位摘要
                    artifact_summary = (
                        f"[DistillationService] MultimodalPipeline 预处理降级: "
                        f"source_type={source_type}, source_ref={source_ref}"
                    )
            else:
                artifact_summary = (
                    f"[DistillationService] MultimodalPipeline 不可用，"
                    f"使用占位摘要: source_type={source_type}"
                )
        except Exception as exc:
            raise RuntimeError(
                f"MultimodalPipeline 预处理失败（500）: {exc}"
            ) from exc

        # 调用 TemplateEngine 渲染预读提示词（best-effort）
        try:
            if self._template_engine is not None:
                # 仅检查 template_id 是否存在，触发 frontmatter 解析
                # 真实实现可能用 template 渲染 preread prompt，此处简化
                pass
        except Exception:
            pass

        # 生成预读摘要（结合 artifact 摘要）
        preread_summary = (
            f"[S_PREREAD] 数据源类型={source_type}, 模板={template_id}。\n"
            f"预读摘要: {artifact_summary}"
        )

        # 疑点清单（简化：根据 source_type 推断）
        ambiguity_questions: List[str] = []
        if source_type == "text":
            ambiguity_questions = [
                "1. 文本中的关键实体是否需要归一化？",
                "2. 时间戳是否需要转换为 UTC？",
            ]
        elif source_type == "character_card":
            ambiguity_questions = [
                "1. 角色卡字段映射是否完整？",
                "2. 角色描述是否需要分块存储？",
            ]
        elif source_type == "image":
            ambiguity_questions = [
                "1. OCR 文本块的置信度阈值是多少？",
                "2. 视觉描述是否需要单独存储？",
            ]
        elif source_type == "conversation_log":
            ambiguity_questions = [
                "1. 对话角色如何区分？",
                "2. 是否需要提取情感倾向？",
            ]

        return preread_summary, ambiguity_questions

    def _count_redistill_turns(self, session: Dict[str, Any]) -> int:
        """统计已发生的回环次数（S_REFLECT → S_QUESTION）。

        Args:
            session: 会话状态字典

        Returns:
            回环次数
        """
        count = 0
        for turn in session.get("turns", []):
            if (
                turn.get("state") == "S_QUESTION"
                and turn.get("agent_action") == "reflect"
            ):
                count += 1
        return count

    def _extract_content(self, session: Dict[str, Any]) -> str:
        """抽取结构化内容（S_EXTRACT 阶段）。

        Args:
            session: 会话状态字典

        Returns:
            抽取的结构化内容字符串
        """
        preread = session.get("preread_summary") or ""
        # 简化抽取：从 preread_summary 中提取关键信息
        extracted = (
            "[S_EXTRACT] 结构化抽取结果:\n"
            f"- source_type: {session['source_type']}\n"
            f"- template_id: {session['template_id']}\n"
            f"- preread_summary: {preread[:300]}\n"
            f"- turns_count: {len(session.get('turns', []))}\n"
        )
        return extracted

    @staticmethod
    def _heuristic_check_truncated(source_ref: str) -> bool:
        """启发式检测 source_ref 是否可能在边界处截断（改进3）。

        判断规则：
            - 末尾不以句号/换行/问号/感叹号/分号/引号结尾 → 可能尾部截断
            - 开头为非句首字符（小写字母、标点）→ 可能头部截断

        Args:
            source_ref: 原始输入文本

        Returns:
            bool: True 表示可能截断，需进一步 LLM 确认
        """
        if not source_ref:
            return False
        # 末尾判断：基于原始文本末尾字符（保留换行符）
        tail_char = source_ref[-1]
        end_chars = ("。", ".", "!", "?", "！", "？", "；", ";", "\n", "\r", "”", '"', ")", "）", " ", "\t")
        tail_truncated = tail_char not in end_chars
        # 开头判断：基于 strip 后的文本（去除首部空白）
        text = source_ref.lstrip()
        if not text:
            return False
        start_punct = (",", "，", "、", "。", ".", "!", "?", "；", ";")
        head_truncated = (
            text[0].islower()
            or text[0] in start_punct
            or (text.startswith("[上下文重叠区开始]") and len(text) > 20 and text[19:20].islower())
        )
        return tail_truncated or head_truncated

    async def _check_needs_more_context(
        self,
        source_ref: str,
        extracted_content: str,
        boundary_ctx: Dict[str, str],
    ) -> bool:
        """检测蒸馏内容是否需要更多上下文（改进3）。

        检测流程：
        1. 启发式预筛：source_ref 是否在边界处截断
        2. 若启发式命中，调用 LLM 确认（best-effort，失败则返回 False）

        Args:
            source_ref: 原始输入文本
            extracted_content: 蒸馏抽取的内容
            boundary_ctx: 相邻 chunk 边界上下文 {prev_tail, next_head}

        Returns:
            bool: True 表示需要更多上下文
        """
        # 步骤1：启发式预筛
        if not self._heuristic_check_truncated(source_ref):
            return False

        # 步骤2：LLM 确认
        try:
            return await self._llm_check_needs_more_context(
                source_ref=source_ref,
                extracted_content=extracted_content,
                boundary_ctx=boundary_ctx,
            )
        except Exception as e:
            logger.warning(f"LLM 确认 needs_more_context 失败，返回 False: {e}")
            return False

    async def _llm_check_needs_more_context(
        self,
        source_ref: str,
        extracted_content: str,
        boundary_ctx: Dict[str, str],
    ) -> bool:
        """通过 LLM 判断是否需要更多上下文（改进3）。

        best-effort：LLM 调用失败或解析失败返回 False。

        Args:
            source_ref: 原始输入文本
            extracted_content: 蒸馏抽取的内容
            boundary_ctx: 相邻 chunk 边界上下文

        Returns:
            bool: True 表示需要更多上下文
        """
        prev_tail = boundary_ctx.get("prev_tail", "")[:300]
        next_head = boundary_ctx.get("next_head", "")[:300]
        prompt = (
            "请判断以下蒸馏片段是否因切分边界导致语义不完整，需要更多上下文才能正确理解。\n\n"
            f"当前片段（source_ref，末尾 300 字符）：\n{source_ref[-300:]}\n\n"
            f"蒸馏抽取结果（前 300 字符）：\n{extracted_content[:300]}\n\n"
            f"前一相邻片段尾部（300 字符）：\n{prev_tail}\n\n"
            f"后一相邻片段头部（300 字符）：\n{next_head}\n\n"
            "判断标准：\n"
            "1. 当前片段末尾是否在句子中间截断（如对话未完成、角色卡字段未闭合）\n"
            "2. 抽取结果是否包含不完整语义（如'用户：'后无内容、'first_mes:'后无值）\n"
            "3. 相邻片段是否包含当前片段所需的上下文\n\n"
            "输出严格的 JSON 格式（不要 markdown 代码块标记）：\n"
            '{"needs_more_context": true 或 false}\n'
        )
        try:
            import httpx

            vllm_url = _load_vllm_base_url()
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{vllm_url}/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": 50,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                raw = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
                parsed = json.loads(raw)
                return bool(parsed.get("needs_more_context", False))
        except Exception as e:
            logger.warning(f"LLM 判断 needs_more_context 解析失败: {e}")
            return False

    def _estimate_quality_score(self, session: Dict[str, Any]) -> float:
        """估算质量评分（S_STORAGE_DECISION 阶段）。

        Args:
            session: 会话状态字典

        Returns:
            质量评分（0-1）
        """
        # 简化：基于 turns 数量 + preread_summary 长度估算
        turns_count = len(session.get("turns", []))
        preread_len = len(session.get("preread_summary") or "")
        # 基础分 0.6，turns 多则加分，preread 长则加分
        score = 0.6 + min(turns_count * 0.05, 0.2) + min(preread_len / 1000, 0.2)
        return float(min(max(score, 0.0), 1.0))

    def _invoke_decision_core(
        self,
        session: Dict[str, Any],
        quality_score: float,
        override_decision: Optional[str],
    ) -> tuple:
        """调用 DecisionCore 执行决策。

        best-effort：DecisionCore 调用失败时降级到内置规则决策。

        Args:
            session: 会话状态字典
            quality_score: 质量评分
            override_decision: 人类覆盖决策

        Returns:
            (location, memory_id, metadata, reason) 元组
        """
        # 人类覆盖决策优先
        if override_decision == "permanent":
            location = "permanent_memories"
            memory_id = self._alloc_memory_id()
            metadata = self._build_metadata(session, "permanent")
            reason = "[DistillationService] 人类 override=permanent，存入永久记忆"
            # 写入审计日志（best-effort，记录人类覆盖决策）
            self._write_decision_log(
                session_id=session["session_id"],
                decision_point="D1_LOCATION",
                decision_input=None,
                rubric=None,
                final_action="store",
                final_location=location,
                final_details={
                    "memory_id": memory_id,
                    "quality_score": quality_score,
                    "override_decision": override_decision,
                },
            )
            return location, memory_id, metadata, reason
        if override_decision == "reject":
            location = "rejected"
            metadata = {"retention_days": 30, "quality_score": quality_score}
            reason = "[DistillationService] 人类 override=reject，拒绝存储"
            # 写入审计日志（best-effort，记录人类覆盖决策）
            self._write_decision_log(
                session_id=session["session_id"],
                decision_point="D6_REJECT",
                decision_input=None,
                rubric=None,
                final_action="reject",
                final_location=location,
                final_details={
                    "quality_score": quality_score,
                    "override_decision": override_decision,
                },
            )
            return location, None, metadata, reason

        # 调用 DecisionCore（best-effort）
        try:
            from public.pre_generated_mock.mock_decision_core import (
                DecisionInput,
                RubricSnapshot,
            )

            rubric = RubricSnapshot(
                importance_threshold_permanent=self._rubric[
                    "importance_threshold_permanent"
                ],
                quality_reject_threshold=self._rubric["quality_reject_threshold"],
                max_redistill_turns=self._rubric["max_redistill_turns"],
                ask_user_confidence_threshold=self._rubric[
                    "ask_user_confidence_threshold"
                ],
                cross_validate_sources=self._rubric["cross_validate_sources"],
            )
            decision_input = DecisionInput(
                artifact_summary=session.get("preread_summary"),
                session_state=session["state"],
                turn_history_summary=str(
                    [t.get("agent_action") for t in session.get("turns", [])]
                ),
                extracted_content=session.get("extracted_content"),
                quality_score=quality_score,
            )

            # D6 拒绝优先判定
            if quality_score < self._rubric["quality_reject_threshold"]:
                decision = self._decision_core.decide_reject(
                    session_id=session["session_id"],
                    quality_score=quality_score,
                    rubric=rubric,
                )
                location = "rejected"
                memory_id = None
                metadata = dict(decision.metadata)
                metadata["retention_days"] = 30
                reason = decision.reason
            else:
                # D1 位置决策
                decision = self._decision_core.decide_location(
                    session_id=session["session_id"],
                    decision_input=decision_input,
                    rubric=rubric,
                )
                location = decision.location
                memory_id = decision.memory_id
                metadata = dict(decision.metadata)
                reason = decision.reason

            # 写入决策审计日志（best-effort，不阻断主流程）
            self._write_decision_log(
                session_id=session["session_id"],
                decision_point="D1_LOCATION" if location != "rejected" else "D6_REJECT",
                decision_input=decision_input,
                rubric=rubric,
                final_action="reject" if location == "rejected" else "store",
                final_location=location,
                final_details={
                    "memory_id": memory_id,
                    "quality_score": quality_score,
                    "override_decision": override_decision,
                },
            )

            return location, memory_id, metadata, reason

        except Exception as exc:
            # 降级到内置规则决策
            return self._fallback_decision(
                session, quality_score, override_decision, str(exc)
            )

    def _fallback_decision(
        self,
        session: Dict[str, Any],
        quality_score: float,
        override_decision: Optional[str],
        error_msg: str,
    ) -> tuple:
        """DecisionCore 不可用时的降级决策。

        Args:
            session: 会话状态字典
            quality_score: 质量评分
            override_decision: 人类覆盖决策
            error_msg: 错误信息

        Returns:
            (location, memory_id, metadata, reason) 元组
        """
        if quality_score < self._rubric["quality_reject_threshold"]:
            return (
                "rejected",
                None,
                {
                    "retention_days": 30,
                    "quality_score": quality_score,
                    "fallback_reason": error_msg,
                },
                f"[DistillationService] 降级决策-拒绝: quality_score={quality_score} < "
                f"threshold={self._rubric['quality_reject_threshold']}",
            )
        # 简化：importance 固定 0.75，与 rubric 阈值比较
        importance = 0.75
        if importance >= self._rubric["importance_threshold_permanent"]:
            location = "permanent_memories"
            reason = (
                f"[DistillationService] 降级决策-永久记忆: importance={importance} >= "
                f"threshold={self._rubric['importance_threshold_permanent']}"
            )
        else:
            location = "memories"
            reason = (
                f"[DistillationService] 降级决策-临时记忆: importance={importance} < "
                f"threshold={self._rubric['importance_threshold_permanent']}"
            )
        return (
            location,
            self._alloc_memory_id(),
            self._build_metadata(session, location),
            reason,
        )

    def _alloc_memory_id(self) -> int:
        """分配 memory_id（简化：基于时间戳的递增序列）。

        Returns:
            memory_id
        """
        # 简化：使用当前毫秒数模 1000000
        return int(datetime.now(timezone.utc).timestamp() * 1000) % 1000000 + 1

    def _build_metadata(
        self, session: Dict[str, Any], location: str
    ) -> Dict[str, Any]:
        """构建记忆元数据。

        Args:
            session: 会话状态字典
            location: 存储位置

        Returns:
            元数据字典
        """
        return {
            "time": _iso_now(),
            "importance": 0.75,
            "source": session["source_type"],
            "tags": ["radix", "distillation", session["template_id"], location],
            "session_id": session["session_id"],
            "quality_score": session.get("quality_score"),
        }

    def _write_decision_log(
        self,
        session_id: str,
        decision_point: str,
        decision_input: Any,
        rubric: Any,
        final_action: str,
        final_location: Optional[str],
        final_details: Dict[str, Any],
    ) -> None:
        """写入决策审计日志到 data/distillation_logs/{session_id}.json。

        best-effort：写入失败不阻断主流程（rules-3 §1.2 异常契约 IOError best-effort）。
        日志结构符合 distillation_log.schema.json。

        Args:
            session_id: 会话 ID
            decision_point: 决策点（D1-D6）
            decision_input: 决策输入
            rubric: rubric 快照
            final_action: 最终决策动作
            final_location: 存储位置
            final_details: 决策详情
        """
        try:
            log_path = os.path.join(self._log_dir, f"{session_id}.json")
            # 读取已有日志（追加模式）
            existing: List[Dict[str, Any]] = []
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8") as fh:
                        existing = json.load(fh)
                        if not isinstance(existing, list):
                            existing = []
                except (json.JSONDecodeError, OSError):
                    existing = []

            # 构造日志条目（符合 distillation_log.schema.json）
            log_entry = {
                "log_id": _new_uuid(),
                "session_id": session_id,
                "decision_point": decision_point,
                "input": (
                    decision_input.model_dump()
                    if hasattr(decision_input, "model_dump")
                    else {}
                ),
                "rubric_snapshot": (
                    rubric.model_dump()
                    if hasattr(rubric, "model_dump")
                    else dict(rubric) if isinstance(rubric, dict) else {}
                ),
                "llm_reasoning": None,
                "llm_confidence": None,
                "final_decision": {
                    "action": final_action,
                    "location": final_location,
                    "details": final_details,
                },
                "timestamp": _iso_now(),
            }
            existing.append(log_entry)

            # 原子写入（先写临时文件再重命名，避免半写损坏）
            tmp_path = log_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, log_path)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            # best-effort：写入失败不阻断主流程
            pass

    def _save_session(self, session: Dict[str, Any]) -> None:
        """持久化 session 到 data/distillation_sessions/{session_id}.json。

        原子写入：先写临时文件再重命名，避免半写损坏。

        Args:
            session: 会话状态字典

        Raises:
            RuntimeError: 持久化失败（500）
        """
        try:
            session_path = os.path.join(
                self._session_dir, f"{session['session_id']}.json"
            )
            tmp_path = session_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(session, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, session_path)
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError(
                f"session 持久化失败（500）: {exc}"
            ) from exc

    def _load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从持久化层加载 session。

        优先从内存缓存读取，缓存未命中时从磁盘加载。

        Args:
            session_id: 会话 ID

        Returns:
            会话状态字典，不存在时返回 None
        """
        # 优先缓存
        if session_id in self._sessions_cache:
            return self._sessions_cache[session_id]

        # 从磁盘加载
        session_path = os.path.join(self._session_dir, f"{session_id}.json")
        if not os.path.exists(session_path):
            return None
        try:
            with open(session_path, "r", encoding="utf-8") as fh:
                session = json.load(fh)
            self._sessions_cache[session_id] = session
            return session
        except (json.JSONDecodeError, OSError):
            return None
