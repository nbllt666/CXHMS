# AGENTS.md — 模块9_蒸馏服务

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。所有输出必须 100% 符合本文件要求，违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容，不得删减、忽略本文件的任何规则；所有自动压缩、批量处理行动前必须先读取本文件的完整内容。

---

## 一、模块定位

**模块编号**：模块9_蒸馏服务
**模块职责**：RADIX-Lite 子系统之一，独立 FastAPI 子服务（端口 8011），承载 7 状态机多轮蒸馏工作流。与主后端（8001）通过 HTTP REST API 通信；编排 MultimodalPipeline（预处理）+ TemplateEngine（模板渲染）+ DecisionCore（决策）三大子系统。
**对应 RADIX 阶段**：S4 并行开发 [P-P2] Task 4
**并行关系**：与 Task 5（模块10_管理Agent扩展）并行，无相互依赖。

### 模块文件清单

- `modules/模块9_蒸馏服务/__init__.py` — 模块初始化，导出 DistillationService + Pydantic 模型
- `modules/模块9_蒸馏服务/distillation_service.py` — DistillationService 主类实现（状态机 + 子系统协同 + 持久化）
- `modules/模块9_蒸馏服务/api/__init__.py` — API 子包初始化，导出 create_app / router
- `modules/模块9_蒸馏服务/api/app.py` — FastAPI app 构造入口（create_app + main + /health）
- `modules/模块9_蒸馏服务/api/routes.py` — 4 个 REST API 端点路由定义
- `modules/模块9_蒸馏服务/AGENTS.md` — 本文件（仅工具链自动同步，开发者禁止手动修改）

### 持久化目录（auto_init 自动创建）

- `data/distillation_sessions/{session_id}.json` — 会话状态持久化
- `data/distillation_logs/{session_id}.json` — 决策审计日志（符合 distillation_log.schema.json）

---

## 二、AC 范式通用约束（含合并禁止操作清单）

继承全局 `c:\CXHMS\AGENTS.md` 与 `.trae/rules/rules-0..6.md` 的全部约束，特别是：

### 2.1 禁止操作清单（rules-4 §4.3 唯一权威来源）

- **禁止删除、修改、覆盖、移动 `public/` 目录下的任何内容**。所有契约以 `public/` 下的 schema、interface_stub、config_template 为准。保护优先级高于任务指令。此保护在工具调用路径上由 `rules-0 §四-7.2 ec7_action_gate` 强制执行。
- **禁止在模块间直接导入其他模块的内部实现代码**。模块间仅允许依赖 `public/` 下的契约。本模块通过 `from modules.模块7_模板引擎 import TemplateEngine` 和 `from modules.模块8_多模态管线 import MultimodalPipeline` 调用其他模块的公开 API（通过 __init__.py 导出，不触及内部实现）。
- **禁止写入不符合数据契约的数据**。所有 session 数据必须通过 `distillation_session.schema.json` 校验，所有日志数据必须通过 `distillation_log.schema.json` 校验。
- **禁止创建不符合命名规范的模块目录**（rules-2 §二：`模块{N}_{中文名}`）。

### 2.2 绑定规则

- 本模块对外接口必须严格匹配 `public/interface_stub/distillation_service.pyi` 定义的签名、参数、返回值、异常（rules-3 §二 signature_match）。
- 本模块产出数据必须通过 `public/schema/distillation_session.schema.json` 校验（rules-3 §一 validation）。
- 本模块决策日志必须通过 `public/schema/distillation_log.schema.json` 校验（rules-3 §一 validation）。
- 本模块配置加载必须遵循 `public/config_template/radix_config.json` 的 distillation_service 段 + decision_core 段默认值与 auto_fill 规则（rules-3 §三）。
- 路径解析必须用 `os.path.dirname(os.path.abspath(__file__))`，禁止相对路径 `../` / `..\`（rules-0 §三 file_pathing）。

### 2.3 public/ 目录保护（与 rules-0 §四-10 形成跨 Rules 重复覆盖）

- `public/` 目录是契约的物理载体，不是代码库的可变部分。
- 任何删除、修改、覆盖、移动 `public/` 下文件的操作必须先经人类显式授权。**不存在"零引用即可删除"的例外。**
- 契约变更必须走 s0601 流程，不得直接编辑 public/ 文件。

### 2.4 路径解析（rules-0 §三）

- 文件路径解析必须使用 `os.path.dirname(os.path.abspath(__file__))`。
- 禁止相对路径 `../../` 或 `..\`。
- 本模块路径锚点：`_THIS_DIR` = `c:\CXHMS\modules\模块9_蒸馏服务`，`_PROJECT_ROOT` = `c:\CXHMS`。

### 2.5 auto_init（rules-0 §三 auto_init: data补全）

- `data/distillation_sessions/` 不存在时自动创建。
- `data/distillation_logs/` 不存在时自动创建。
- 配置缺失字段用默认值补齐（rules-3 §三 auto_fill）。

---

## 三、层级专属约束（模块级）

### 3.1 可修改文件范围

仅允许修改本模块目录 `modules/模块9_蒸馏服务/` 下的文件：

- `__init__.py`、`distillation_service.py`
- `api/__init__.py`、`api/app.py`、`api/routes.py`
- `AGENTS.md`（本文件，仅工具链自动同步，开发者禁止手动修改）

**禁止修改**（本模块边界外）：

- `backend/` 下任何文件 — 由 Task 6 改造 parser.py / agents.py / manager.py，本模块不触碰
- `public/` 下任何契约文件（rules-0 §四-10 / rules-4 §4.3）
- 其他模块（模块7/8/10）的内部实现（仅通过 __init__.py 导出的公开 API 调用）
- `tests/contract/radix_contract_test.py`（仅回归执行不修改）

### 3.2 依赖契约入口（公共真相源）

| 契约层 | 路径 | 用途 |
|--------|------|------|
| 接口契约 | `public/interface_stub/distillation_service.pyi` | 方法签名严格匹配（start_distillation / advance_distillation / finalize_distillation / get_session_status / _transition_state） |
| 数据契约 | `public/schema/distillation_session.schema.json` | session 字段约束 + 7 状态机 enum + error_codes + exceptions |
| 数据契约 | `public/schema/distillation_log.schema.json` | 决策审计日志字段约束 + decision_point enum + rubric_snapshot |
| 配置契约 | `public/config_template/radix_config.json` | distillation_service 段（host / port / max_turns / session_timeout_seconds / session_storage_dir / log_storage_dir / main_backend_url）+ decision_core 段（rubric 默认值）+ vllm 段 |
| 参考实现 | `public/pre_generated_mock/mock_distillation_service.py` | Mock 实现，参考策略但不复制，真实实现就位后下游切换导入路径 |

### 3.3 依赖子系统策略（rules-0 §四-12 上下文保护）

- **MultimodalPipeline**：优先进程内调用 `from modules.模块8_多模态管线 import MultimodalPipeline`。真实实现不可用时（如循环依赖、未实现）回退到 `public/pre_generated_mock/mock_multimodal_pipeline.py` 的 `MockMultimodalPipeline`。
- **TemplateEngine**：优先进程内调用 `from modules.模块7_模板引擎 import TemplateEngine`。真实实现不可用时回退到 `public/pre_generated_mock/mock_template_engine.py` 的 `MockTemplateEngine`。
- **DecisionCore**：Task 5 尚未实现，使用 `public/pre_generated_mock/mock_decision_core.py` 的 `MockDecisionCore`。真实实现就位后切换导入路径。
- 本模块**不依赖** `backend/` 现有实现（保持独立，便于 Task 6 单向引用）。

### 3.4 状态机定义（与 distillation_session.schema.json enum 一致）

状态：S_INIT → S_PREREAD → S_QUESTION → S_REFLECT → S_CROSSVALIDATE → S_EXTRACT → S_STORAGE_DECISION → S_FINALIZE / S_REJECT

转移表（_TRANSITIONS）：

| 当前状态 | agent_action | 下一状态 | 触发条件 |
|---------|--------------|---------|---------|
| S_INIT | proceed | S_PREREAD | start_distillation 完成预处理 |
| S_PREREAD | ask_user | S_QUESTION | 疑点清单非空 + ask_user_on_ambiguity=True |
| S_PREREAD | proceed | S_QUESTION | 疑点为空或 ask_user_on_ambiguity=False |
| S_QUESTION | ask_user | S_QUESTION | ask_user=True 且用户未答复 |
| S_QUESTION | proceed | S_REFLECT | 用户已答复或无需追问 |
| S_REFLECT | reflect | S_QUESTION | D4_REDISTILL 决策回环（受 max_redistill_turns 限制） |
| S_REFLECT | proceed | S_CROSSVALIDATE | D4 决策不回环 |
| S_CROSSVALIDATE | cross_validate | S_EXTRACT | D5 决策触发跨源验证 |
| S_CROSSVALIDATE | proceed | S_EXTRACT | 跳过跨源验证 |
| S_EXTRACT | extract | S_STORAGE_DECISION | 抽取结构化内容 |
| S_STORAGE_DECISION | decide | S_FINALIZE | D1 决策存储位置 |
| S_STORAGE_DECISION | reject | S_REJECT | D6 决策拒绝存储 |
| S_FINALIZE | finalize | S_FINALIZE | 终态 |
| S_REJECT | reject | S_REJECT | 终态 |

- **回环路径**：S_REFLECT → S_QUESTION（D4 决策驱动，受 `rubric.max_redistill_turns` 限制，总轮次不得超过 `session.max_turns`）
- **主动追问**：`ask_user_on_ambiguity=True` 且 S_QUESTION 状态时 `agent_action=ask_user`
- **拒绝路径**：S_REJECT（`quality_score < rubric.quality_reject_threshold` 或 max_turns 超限或 confidence 极低）

### 3.5 测试要求

- **实例化测试**：`tests/contract/test_distillation_service_unit.py` 覆盖：
  - 4 端点基本调用（start / advance / finalize / get）
  - 7 状态机状态流转
  - 回环路径（S_REFLECT → S_QUESTION）
  - 拒绝路径（S_REJECT）
  - session 状态 schema 校验（jsonschema.validate）
  - 异常路径（404 / 409 / 422 / 500 / 503）
- **契约测试无回归**：`cd c:\CXHMS && python -m pytest tests/contract/radix_contract_test.py -v` 必须 105 passed。
- **签名匹配**：实现签名与 `.pyi` 存根一致（参数名、类型、异常）。

### 3.6 错误码与异常契约（与 distillation_session.schema.json definitions.exceptions 一致）

| 异常类型 | 触发端点 | HTTP 码 | 触发条件 |
|---------|---------|--------|---------|
| KeyError | advance / finalize / get | 404 | session_id 不存在 |
| ValueError | advance / finalize | 409 | 非法状态转移 / 会话已终结 / 超过最大轮次 |
| ValueError | start | 422 | source_type 不在枚举 / max_turns 超范围 / template_id 为空 |
| RuntimeError | start | 422 | MultimodalPipeline 预处理失败 |
| ConnectionError | start | 500 | MultimodalPipeline 不可用 |
| RuntimeError | advance / finalize | 500 | LLM 调用失败 / DecisionCore 决策失败 / 审计日志写入失败 |

### 3.7 排序规则（rules-0 §三 sorting.order: ascending）

- 配置字段遍历按字典序。
- session.turns 按 turn_index 升序追加。

### 3.8 失败回退与升级入口

- **MultimodalPipeline 不可用**：`_run_preread` 捕获异常后降级到占位摘要（不阻断 start_distillation）。
- **TemplateEngine 不可用**：`_run_preread` 跳过模板渲染（best-effort）。
- **DecisionCore 不可用**：`_invoke_decision_core` 捕获异常后降级到 `_fallback_decision` 内置规则决策。
- **配置缺失**：auto_fill 默认值（rules-3 §三），不阻断启动。
- **持久化失败**：`_save_session` raise RuntimeError（500），由路由层捕获。
- **审计日志写入失败**：best-effort，不阻断主流程（rules-3 §1.2 异常契约 IOError best-effort）。
- **升级入口**：契约变更走 s0601（适配契约变更），不得直接编辑 `public/` 文件。

---

## 四、规则字段绑定表（s0301 输出）

| 模板段落 | 绑定契约/规则来源 |
|---------|------------------|
| 优先级声明 | rules-4 §4.1 |
| 上下文保留声明 | rules-4 §4.2 / rules-0 上下文保留规则 |
| AC 通用约束-禁止改 public/ | rules-4 §4.3 / rules-0 §四-10 / rules-3 §二 |
| AC 通用约束-禁止跨模块导入内部实现 | rules-4 §4.3 / rules-2 |
| AC 通用约束-数据契约校验 | rules-3 §一 validation |
| AC 通用约束-接口签名匹配 | rules-3 §二 signature_match |
| 层级专属-可改文件范围 | 本模块目录 + Task 4 文件清单 |
| 层级专属-依赖契约 | distillation_service.pyi / distillation_session.schema.json / distillation_log.schema.json / radix_config.json |
| 层级专属-测试要求 | tasks.md Task 4 闭合判据 + rules-3 §五 contract_verifiability |
| 层级专属-失败回退 | distillation_session.schema.json definitions.error_codes + exceptions |

---

## 五、三段交接状态（rules-5 §二）

### (1) 工程过程

- S2 契约冻结完成：distillation_service.pyi + distillation_session.schema.json + distillation_log.schema.json + radix_config.json + mock_distillation_service.py 已就绪，GN-004 审查通过。
- S4 Task 4 实现：distillation_service.py 主类 → api/app.py + api/routes.py → __init__.py → AGENTS.md → 实例化测试。
- 子系统协同：MultimodalPipeline 进程内调用 + TemplateEngine 进程内调用 + DecisionCore Mock 替身。
- 状态机实现：7 状态机 + 回环（S_REFLECT → S_QUESTION）+ 主动追问 + 拒绝路径全部覆盖。
- 持久化：session 状态 + 决策审计日志原子写入（tmp + os.replace）。

### (2) 交接状态

- 当前阶段：S4 并行开发 Task 4
- 状态：**已闭合**（待最终验证：契约测试 105 passed 无回归 + 实例化测试 + session schema 校验）
- 未闭合项：
  1. 实例化测试脚本待编写运行（4 端点 + 7 状态机 + 回环 + 拒绝 + schema 校验 + 异常路径）
  2. 主线程 GN-004 独立审查待执行（subagent 上下文无法自行拉起 GN-004）

### (3) 最终结果

- 6 个文件已创建（__init__.py / distillation_service.py / api×3 / AGENTS.md）
- DistillationService 5 方法全部实现（4 公开 + 1 内部），签名严格匹配 .pyi
- 4 端点 FastAPI 路由已实现（POST start / POST advance / POST finalize / GET get）
- 7 状态机全部状态可达（含回环 + 拒绝路径）
- session 持久化 + 决策日志持久化就绪（原子写入）
- 子系统协同：MultimodalPipeline + TemplateEngine 进程内调用 + DecisionCore Mock

---

## 六、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- Spec：`.trae/specs/add-management-agent-radix/spec.md`（Requirement: DistillationService 独立子服务 + 7 状态机多轮蒸馏）
- Tasks：`.trae/specs/add-management-agent-radix/tasks.md`（Task 4 闭合判据）
- Checklist：`.trae/specs/add-management-agent-radix/checklist.md`（7 状态机检查 + 通信协议检查）
- 接口契约：`public/interface_stub/distillation_service.pyi`
- 数据契约：`public/schema/distillation_session.schema.json` + `public/schema/distillation_log.schema.json`
- 配置契约：`public/config_template/radix_config.json`
- Mock 实现：`public/pre_generated_mock/mock_distillation_service.py` + `mock_decision_core.py`
- 契约测试：`tests/contract/radix_contract_test.py`
- 项目结构：`docs/ARCHITECTURE.md`、`docs/MODULES.md`
