# 契约变更日志 (CHANGELOG)

> 遵循 AC 范式 v6 rules-3 §六 契约版本化规则。所有契约变更必须记录版本号、变更内容、变更原因、影响范围。

## [1.2.0] - 2026-07-16

### 变更内容
- **数据契约新增（MINOR）**：新增 6 份 JSON Schema (draft-07+)
  - `distillation_session.schema.json`：蒸馏会话状态机契约（7 状态 + turns 数组 + final_decision）
  - `multimodal_artifact.schema.json`：多模态预处理产出契约（3 模态 type 枚举 + confidence + vision_degraded）
  - `template_registry.schema.json`：模板仓库契约（frontmatter + body + CRUD 元数据）
  - `storage_decision.schema.json`：存储决策契约（3 location 枚举 + rubric_snapshot + quality_score）
  - `distillation_log.schema.json`：决策审计日志契约（6 决策点 + llm_reasoning + final_decision）
  - `agent_config_v2.schema.json`：管理 Agent 配置契约（tools_config 8 工具 + decision_rubric 4 阈值 + distillation_enabled）
- **接口契约新增（MINOR）**：新增 6 份 .pyi 存根
  - `distillation_service.pyi`：4 API 端点 + 1 内部方法（start/advance/finalize/get + _transition_state）
  - `template_engine.pyi`：7 方法（render_template + CRUD + _parse_frontmatter）
  - `multimodal_pipeline.pyi`：7 方法（preprocess + 3 worker + _merge_ocr_vision）
  - `decision_core.pyi`：9 方法（6 决策点 + _load_rubric + _llm_decide + _write_audit_log）
  - `memory_manager_v2.pyi`：3 方法（write_with_decision + get_rejected_content + cleanup_expired_rejected_content）
  - `agent_tools_v2.pyi`：8 工具方法
- **配置契约新增（MINOR）**：新增 `radix_config.json`（5 段：distillation_service / multimodal_pipeline / template_engine / decision_core / vllm）
- **预生成 Mock 新增**：6 份对应接口的 Mock 实现
- **测试套件新增**：
  - `tests/contract/radix_contract_test.py`（105 用例）
  - `tests/contract/test_distillation_service_unit.py`（50 用例）
  - `tests/contract/test_decision_core_unit.py`（55 用例）
  - `tests/contract/test_multimodal_pipeline_unit.py`（28 用例）
  - `tests/units/test_template_engine_smoke.py`（24 用例）
  - `tests/e2e/test_radix_task6_integration.py`（37 用例）
  - `tests/contracts/test_interface_stub.py` 扩展（+156 用例，RADIX-Lite 6 类 locator）

### 变更原因
- spec `add-management-agent-radix` 实施：RADIX-Lite 融合方案（方案 C 去除音视频模态，保留 3 独立子系统 + 7 状态机多轮蒸馏 + Jinja2 DSL 模板 + 6 决策点自主决策）
- spec 三件套已通过 GN-004 交付前独立审查（6 维度全 PASS，0 阻断 0 警示 3 观察项非阻断）
- [V] 双重闸门已闭合：GN-004 通过 + 人类批准交付（2026-07-16）
- public/ 文件已获人类显式授权（rules-0 §四-10 + rules-4 §4.3）

### 影响范围
- MINOR 变更（新增可选接口）：通知依赖模块，不阻断。新增的 6 schema + 6 .pyi + 1 config 独立于现有 11 schema 和 11 .pyi，不影响现有模块
- 下游影响：
  - `backend/core/document/parser.py` 新增 `parse_attachments_v2` 双模式入口（legacy_parser_enabled 开关，默认 True 向后兼容）
  - `backend/core/memory/manager.py` 新增 `write_with_decision` + `rejected_content` 表（保留 30 天）
  - 模块间通过 try-except fallback 到 Mock（rules-0 §三），不硬依赖真实实现

### 闭合判据
- [x] 6 份数据契约存在且通过 jsonschema 自校验
- [x] 6 份接口存根存在且仅含签名（零实现）
- [x] 1 份配置契约存在且含默认值（5 段）
- [x] 6 份预生成 Mock 存在且签名匹配 .pyi
- [x] 测试套件可自主执行：262 RADIX-Lite + 437 interface_stub + 37 E2E = 736 PASS
- [x] GN-004 交付前审查通过（6 维度全 PASS）
- [x] [V] 双重闸门闭合（GN-004 通过 + 人类批准交付）

## [1.1.0] - 2026-07-14

### 变更内容
- **数据契约新增（MINOR）**：新增 `anythingllm_workspace.json`（AnythingLLM 兼容 workspace 数据契约）和 `openai_chat_completion.json`（OpenAI ChatCompletion 响应契约），共 2 份 JSON Schema (draft-07+)。
- **接口契约新增（MINOR）**：新增 `anythingllm_service.pyi`，包含 11 个端点方法签名 + 1 个 verify_api_key 认证依赖，对应 AnythingLLM Developer API Phase 1 兼容层。
- **测试套件新增**：新增 `test_anythingllm_contract.py`，校验 workspace/chat_completion schema + 接口存根 11 签名完整性。

### 变更原因
- 用户需求：加入 AnythingLLM 兼容 API，使支持 AnythingLLM API 的工具/客户端可直接对接 CXHMS。
- spec 三件套已通过 GN-004 第五次独立审查（14/14 检查点 PASS），人类已显式授权创建 public/ 下契约文件（rules-0 §四-10）。

### 影响范围
- MINOR 变更（新增可选接口）：通知依赖模块，不阻断。新增的契约独立于现有 5 份 schema 和 5 份 .pyi，不影响现有模块。
- 下游影响：AnythingLLM 兼容路由模块（`backend/api/routers/anythingllm.py`）的实现必须严格匹配本批契约。

### 闭合判据
- [x] `anythingllm_workspace.json` 存在且通过 jsonschema 自校验
- [x] `openai_chat_completion.json` 存在且通过 jsonschema 自校验
- [x] `anythingllm_service.pyi` 存在且包含 11 个端点方法签名 + verify_api_key
- [x] `test_anythingllm_contract.py` 全部 PASS

## [1.0.2] - 2026-07-04

### 变更内容
- **接口契约修正（PATCH）**：`memory_service.pyi` 的 `batch_delete_memories.soft_delete` 默认值由 `False` 改为 `True`，与真实实现对齐（保留软删除语义）。
- **实现类型严格化（PATCH）**：`backend/core/memory/manager.py` 的 `semantic_search.memory_type` 类型注解由 `str = None` 改为 `Optional[str] = None`，与契约一致（PEP 484 严格）。
- **测试严格化（PATCH）**：`test_data_schema.py`、`test_config_template.py` 删除 `if jsonschema is None: return` 静默降级分支，改为 `pytestmark = pytest.mark.skipif(jsonschema is None, ...)` 显式 skip；新建 `public/dependencies/requirements.txt` 声明 `jsonschema>=4.0.0` 硬依赖。
- **rubric 同步（PATCH）**：`rubric.md` 测试数量 27/27 → 34/34；`hybrid_search`/`semantic_search`/`batch_update_memories`/`batch_delete_memories` 签名描述对齐 .pyi 实际参数。

### 变更原因
- GN-004 第二次复审阻断项（jsonschema 未安装导致 3 测试静默跳过断言）+ 4 观察项（rubric 数字/描述、soft_delete 默认值、type annotation 严格化）的修复。

### 影响范围
- PATCH 变更：记录即可。`soft_delete=True` 是真实实现已有行为，契约对齐无回归。type annotation 修改仅静态检查影响。测试严格化使契约约束真正被验证。

### 闭合判据
- [x] jsonschema 实际安装并验证 9 次实际调用 `jsonschema.validate`（GN-004 第三次复审独立证实）
- [x] 测试 34/34 真正通过（非降级）
- [x] 后端 smoke test 端到端通过（write_memory/batch_write_memories/batch_delete_memories/semantic_search）

## [1.0.1] - 2026-07-04

### 变更内容
- **接口契约补全（MINOR）**：
  - `memory_service.pyi`：`get_memory` 补 `include_deleted: bool = False`；`hybrid_search` 补 `memory_type`/`tags` 参数，`workspace_id` 改 `Optional[str]`；`semantic_search` 补 `memory_type: Optional[str] = None`；`batch_update_memories` 补 `raise_on_error: bool = False`。
  - `graph_service.pyi`：`delete_node` 补 `cascade: bool = True`；`shortest_path` 补 `agent_id: str = "default"`。
- **数据契约新增（MINOR）**：新增 `graph_node.json`、`graph_edge.json` 共 2 份 JSON Schema，补全 GraphNode/GraphEdge 数据契约缺口。
- **配置契约清理（PATCH）**：`llm_config.json` 删除 `models.additionalProperties` 内联冗余 modelSlot 定义，统一改为 `$ref: "#/$defs/modelSlot"` 引用，消除双重定义。
- **实现签名对齐（PATCH）**：`backend/core/memory/manager.py` 的 `update_memory` 参数顺序对齐契约（`new_importance` 前移到 `new_tags` 前）；`hybrid_search` 的 `limit` 默认值从 10 改为 5。
- **Mock 同步**：`memory_mock.py`、`graph_mock.py` 同步上述接口契约变更。
- **类型修正（PATCH）**：`chat_service.pyi`、`agent_service.pyi`、`chat_mock.py` 补全缺失的 `Any` import。
- **测试基础设施**：新建 `public/test_cases/rubric.md`；`test_interface_stub.py` 增加存根 vs 真实实现签名对比分支；`test_data_schema.py` 增加 `test_message_valid_instance`、`test_graph_valid_instance`；`conftest.py` 重写为 pytest fixture 模式；`pytest.ini` testpaths 从 `tests` 调整为 `public/test_cases`（移除 tests，因 sim_actor fixture 未实现 G2 阶段且用户已指示抛弃旧测试）。

### 变更原因
- GN-004 第一次审查 D6 三层契约结论为「阻断」（4 项硬性阻断 + 5 项警示项）。用户已显式授权修复 `public/` 下文件（ec7_action_gate 已通过），并选定混合策略：纯顺序/默认值不一致改实现对齐契约；功能性参数缺失改契约补全（保留功能）。

### 影响范围
- MINOR 变更（新增可选字段、新增 schema）：通知依赖模块，不阻断。新增的可选字段均对齐真实实现已有参数，下游模块无需强制适配。
- PATCH 变更（默认值调整、类型修正、描述清理）：记录即可。`hybrid_search` 的 limit 默认值从 10 改为 5，调用方依赖默认值的需关注。
- 新增 `graph_node.json`/`graph_edge.json`：下游涉及图节点/边读写的模块可参考此契约校验数据结构。

### 闭合判据
- [x] 4 项硬性阻断全部修复（测试可自主执行 / rubric 存在 / 签名匹配 / 测试覆盖真实实现）
- [x] 5 项警示项全部修复（Any import / valid_instance 用例 / llm_config 冗余清理 / 变更记录收尾 / CHANGELOG 更新）
- [x] 全量核验其他 4 个存根（chat/agent/tool/graph）vs 真实实现，修复 2 处功能性参数缺失
- [x] 测试两种调用方式通过（`python -m pytest public/test_cases/ -v` 与 `python -m pytest -v`）

## [1.0.0] - 2026-07-02

### 变更内容
- 初始化三层契约（首次建立）。
- 数据契约：新增 `memory.json`、`agent.json`、`message.json`、`tool.json`、`error.json` 共 5 份 JSON Schema (draft-07+)。
- 接口契约：新增 `memory_service.pyi`、`chat_service.pyi`、`agent_service.pyi`、`tool_service.pyi`、`graph_service.pyi` 共 5 份 .pyi 存根。
- 配置契约：新增 `llm_config.json`、`vector_config.json`、`system_config.json` 共 3 份 JSON Schema（含默认值）。
- 预生成 Mock：新增 5 份对应接口的默认 Mock 实现。
- 测试套件：新增 `test_data_schema.py`、`test_interface_stub.py`、`test_config_template.py`。

### 变更原因
- D6 [V] 价值判断节点任务要求：在并行开发全面展开前钉住唯一真相源（rules-3 §五 契约可验证性要求）。
- 此前 backend 使用 dataclass + Pydantic 散点定义，缺乏跨模块公共契约约束，需统一为 public/ 下的可核对边界。

### 影响范围
- MAJOR 初始版本，下游所有模块（memory/chat/agent/tool/graph）以此契约为准。
- backend 现有实现已对齐契约字段；如未来 backend 字段变更须走 s0601 契约适配流程，MAJOR 变更将触发依赖模块 TODO 清单。

### 闭合判据
- [x] 5 份数据契约存在且符合 draft-07+
- [x] 5 份接口存根存在且仅含签名
- [x] 3 份配置契约存在且含默认值
- [x] 测试套件可自主执行（jsonschema 校验 + 签名匹配 + 默认值填充）
