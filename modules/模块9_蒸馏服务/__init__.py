"""模块9_蒸馏服务（DistillationService）。

RADIX-Lite 子系统之一：独立 FastAPI 子服务（端口 8011），承载 7 状态机多轮蒸馏工作流。

对应契约:
    - 接口契约: public/interface_stub/distillation_service.pyi
    - 数据契约: public/schema/distillation_session.schema.json
    - 数据契约: public/schema/distillation_log.schema.json
    - 配置契约: public/config_template/radix_config.json (distillation_service 段)

状态机:
    S_INIT -> S_PREREAD -> S_QUESTION -> S_REFLECT -> S_CROSSVALIDATE
           -> S_EXTRACT -> S_STORAGE_DECISION -> S_FINALIZE / S_REJECT

    回环: S_REFLECT -> S_QUESTION (D4_REDISTILL 决策驱动，受 max_redistill_turns 限制)
    主动追问: ask_user_on_ambiguity=True 且 S_QUESTION 时 agent_action=ask_user
    拒绝路径: S_REJECT (confidence 极低 / max_turns 超限 / quality_score 低于阈值)

子系统协同:
    - MultimodalPipeline (进程内调用 from modules.模块8_多模态管线 import MultimodalPipeline)
    - TemplateEngine     (进程内调用 from modules.模块7_模板引擎 import TemplateEngine)
    - DecisionCore       (Task 5 未实现，使用 Mock from public.pre_generated_mock.mock_decision_core import MockDecisionCore as DecisionCore)

公开导出:
    - DistillationService               — 蒸馏服务主类
    - StartDistillationRequest          — 启动会话请求
    - StartDistillationResponse         — 启动会话响应
    - AdvanceDistillationRequest        — 推进状态机请求
    - AdvanceDistillationResponse       — 推进状态机响应
    - FinalizeDistillationRequest       — 终结会话请求
    - FinalizeDistillationResponse      — 终结会话响应
    - SessionStatusResponse             — 会话状态查询响应

FastAPI app 构造入口: modules.模块9_蒸馏服务.api.create_app

@version 1.0.0
"""

from modules.模块9_蒸馏服务.distillation_service import (
    AdvanceDistillationRequest,
    AdvanceDistillationResponse,
    DistillationService,
    FinalizeDistillationRequest,
    FinalizeDistillationResponse,
    SessionStatusResponse,
    StartDistillationRequest,
    StartDistillationResponse,
)

__all__ = [
    "DistillationService",
    "StartDistillationRequest",
    "StartDistillationResponse",
    "AdvanceDistillationRequest",
    "AdvanceDistillationResponse",
    "FinalizeDistillationRequest",
    "FinalizeDistillationResponse",
    "SessionStatusResponse",
]

__version__ = "1.0.0"
