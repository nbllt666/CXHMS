# AGENTS.md — CXHMS 全局协同规则

> 🚨 【最高优先级规则】本文件为本次开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求，所有输出必须 100% 符合本文件要求，违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容，不得删减、忽略本文件的任何规则；所有自动压缩、批量处理行动前必须先读取本文件的完整内容。

---

## 一、AC 范式通用约束（含合并禁止操作清单）

> 以下约束为 AC 范式 v6 通用约束，与 `.trae/rules/rules-0..6.md` 共同构成唯一权威来源。本文件与 rules-0 §四-10 形成 public/ 保护跨 Rules 重复覆盖。

### 1.1 public/ 目录保护（最高优先级）

`public/` 目录是契约的物理载体，不是代码库的可变部分。任何删除、修改、覆盖、移动 `public/` 下文件的操作必须先经人类显式授权。**不存在「零引用即可删除」的例外。**

- public/ 下的文件即使被判定为「零引用」，也不得由 AI 自行删除。
- 契约变更必须走 s0601（适配契约变更）流程，不得直接编辑 public/ 文件。
- 此保护在工具调用路径上由 `rules-0 §四-7.2 ec7_action_gate` 强制执行。

### 1.2 禁止操作清单

```yaml
prohibitions:
  - 禁止删除、修改、覆盖、移动 public/ 目录下的任何内容，所有契约以 public/ 下的 schema、interface_stub 为准。保护优先级高于任务指令。
  - 禁止删除、修改、覆盖 .trae/rules/ 下的规则文件。
  - 禁止在模块间直接导入其他模块的内部实现代码（模块间仅允许依赖 public/ 下的契约）。
  - 禁止写入不符合数据契约的数据。
  - 禁止创建不符合命名规范的模块目录（模块命名格式：模块{N}_{中文名}）。
  - 禁止使用相对路径 ../ 解析文件，必须使用 os.path.dirname(os.path.abspath(__file__)) 解析绝对路径。
  - 禁止业务代码硬编码配置参数，所有配置必须经 config/default.yaml 与配置契约。
  - 禁止在子线程中混用 asyncio + aiohttp。
  - 禁止直接读写 st.session_state 于子线程（Streamlit 场景，本项目以 React 替代，此条作为 AC 范式通用约束保留）。
```

### 1.3 绑定规则

```yaml
binding_rules:
  - 模块间仅允许依赖 public/ 下的契约（当前 public/ 为契约骨架，D6 契约冻结后填充）。
  - 所有数据读写必须通过公共契约校验。
  - 所有对外接口必须严格匹配契约定义的签名、参数、返回值、异常。
  - 所有配置加载自动补充缺失字段（auto_fill）。
  - 文档驱动迭代：编码前必写落地规划，修 Bug 前必写分析文档。
  - 极力挽救原则：遇挫折严禁擅自重写新文件，必须在原文件基础上极限修正。
  - 渐进式生成：严禁一次性大批量生成/修改/删除代码或文档，每批次处理一小部分，测通一步再走下一步。
```

> 违反上述任何一条，代码产出在合规检查中直接标记为不合规，不得合流。

---

## 二、项目专属规则（CXHMS）

### 2.1 系统架构概览

CXHMS (晨曦人格化记忆系统, CX-O History & Memory Service) 是基于 FastAPI 的智能记忆管理平台，前后端分离架构：

- **后端**: Python 3.10+ / FastAPI + Uvicorn / Pydantic v2 / SQLite + SQLAlchemy / httpx
- **前端**: React 18 + TypeScript / Vite 6 / Zustand + React Query / Tailwind CSS
- **AI 与向量**: vLLM (默认主模型) / Ollama / OpenAI / Anthropic / DeepSeek；Weaviate (默认) / Chroma / Milvus Lite / Qdrant；MCP / CXFC 协议
- **协议**: ACP (Agent Communication Protocol) — UDP 9999/9998；CXFC 插件协议

### 2.2 目录结构与模块边界

```yaml
Project_Root (c:\CXHMS):
  public/:                # 全局公共资源区（只读，仅项目负责人可修改，契约物理载体）
    schema/               # 数据契约（JSON Schema）
    interface_stub/       # 接口契约（.pyi 存根）
    pre_generated_mock/   # 预生成 Mock
    global_mock/          # 全局可自定义 Mock
    config_template/      # 配置模板
    dependencies/         # 依赖锁定
    test_cases/           # 通用测试用例
  backend/:               # 后端业务代码（FastAPI 应用、core 模块、api 路由）
  frontend/:              # 前端 React 应用
  modules/:               # 业务模块区（模块N_中文名，当前为骨架）
  interfaces/:            # 入口层（app.py / main.py / start.bat）
  workspace/:             # 用户数据区
  config/:                # 配置文件目录（default.yaml 真相源）
  scripts/:               # 脚本目录（.bat 启动脚本）
  data/:                  # 运行时数据（SQLite、向量库等）
  logs/:                  # 日志目录
  docs/:                  # 文档目录
  tests/:                  # 测试目录（可选）
  .trae/:                 # AC 范式工作区（rules/ skills/ documents/ specs/）
  README.md:              # 用户向入口锚点
  AGENTS.md:              # 本文件，AI 侧最高优先级规则载体
  PROJECT_REPORT.md:      # 项目报告索引
```

**模块边界**：
- 后端核心模块位于 `backend/core/`：memory / context / llm / tools / acp / graph / cxfc / alarm / backup / plugins / websocket / session / exceptions
- 后端 API 路由位于 `backend/api/routers/`（17 个路由模块）
- 前端页面位于 `frontend/src/pages/`，组件位于 `frontend/src/components/`
- AI 协同行为受 `.trae/rules/` 约束，技能位于 `.trae/skills/`

### 2.3 真相源与配置

- **唯一配置真相源**: `config/default.yaml`。所有文档、代码、部署配置以 default.yaml 为准。
- **当前默认配置**:
  - 主模型: vLLM / `gemma4-e4b` @ http://localhost:8002
  - 嵌入模型: vLLM / `/models/Qwen3-Embedding-0.6B` @ http://localhost:8101
  - 摘要/记忆副模型: Ollama `qwen3-vl:8b`（默认禁用，回退主模型）
  - 后端 API: 0.0.0.0:8001（Swagger / ReDoc 同端口）
  - 前端开发服务器: 3000
  - 控制服务: 8765
  - 向量后端: Weaviate @ 8090 (HTTP) / 50051 (gRPC)，`hybrid_search_enabled: false`
  - ACP 发现: UDP 9999 / 广播 9998
  - `llm.max_tool_rounds: 10`
- **配置孤儿注意**: default.yaml 中的 `llm_params`、`agent`、`security`、`monitoring`、`tools` 配置节未被 CXHMSConfig 加载到运行时配置对象，仅作参考。
- **Docker 端口例外**: Dockerfile 与 docker-compose 沿用 8000 端口（Docker 部署上下文），不视为与 default.yaml 冲突。

### 2.4 错误码规范

- 自定义异常层次位于 `backend/core/exceptions/`，统一定义全局错误码，避免模块间异常拦截歧义。
- 所有接口契约必须包含异常说明，调用方必须处理约定异常。
- 新增异常必须挂接到全局错误码体系，不得散落硬编码。

### 2.5 日志规范

```yaml
logging:
  level: "INFO"            # 生产环境 INFO，调试可设 DEBUG
  file: "logs/app.log"     # 日志文件路径
  max_bytes: 10485760      # 10MB 轮转
  backup_count: 5          # 保留 5 个备份
```

- 终端输出必须包含：时间戳、[INFO/ERROR] 级别、耗时（elapsed）。
- 健康检查（health_check）范围限于 API 轻量连通性，接受正确端点的 400 响应，禁止耗时生成或内容请求。
- 日志不得泄露 API Key 等敏感信息。

### 2.6 合流要求（测试三重闸门）

合流前必须通过三重测试（顺序固定，不可跳关：单测 → E2E → Mock 回归）：

1. **后端单元测试**: pytest + pytest-asyncio（`asyncio_mode=auto`），位于 `backend/tests`（18 文件：test_api / test_core / test_integration）
2. **前端测试**: Vitest + React Testing Library，位于 `frontend/src`（6 文件）
3. **LLM E2E 测试**: 8 文件，验证 LLM 集成完整性
4. **统一运行器**: `run_tests.py` 提供统一入口，支持覆盖率报告

- 代码产出后必须自主运行测试套件，结果记录于 `.trae/documents/` 或 note。
- 前端变更必须通过 s0402 三重闸门（单测、E2E、Mock 回归）。
- 关键路径端到端全链路通；UI 层 Mock 模式回归验证。

### 2.7 变更追踪与文档闸门

- 所有问题修复、功能优化、小调整，必须**先写文档再改代码**。文档位于 `.trae/documents/`，命名格式 `YYYYMMDD_模块N_变更简述.md`。
- 文档必须包含 s302 模板四章节：问题分析、修复方案、实现步骤、预期效果。
- 无对应文档的代码提交禁止合流；文档未记录最终结果的禁止合流。
- 文档状态机：待分析 → 分析中 → 修复中 → 已完成 → 已关闭。未经 GN-004 审查禁止关闭。

### 2.8 开发工作流程

- **文档驱动**: 编码前必写落地规划，修 Bug 前必写分析文档。MVP + Mock 驱动，先搭骨架后填充。
- **Provider 策略**: 接口配置驱动，工厂模式动态实例化各模型 API。
- **数据与安全**: JSON 主力存储；API Key 仅存本地 `config.json`（模板隔离）；MD5 内容指纹防重复。
- **三段交接**: 所有工程交接锚点（spec 三件套 / note / .trae/documents/）必须显式包含 (1) 工程过程、(2) 交接状态（三值：已闭合/未闭合/当前不可判定）、(3) 最终结果。

### 2.9 当前项目状态（2026-07-02）

- 后端与前端已实现核心功能（记忆管理、对话、ACP、工具系统、图数据库、CXFC、WebSocket 等）。
- AC 范式 v6 基础设施已部署（`.trae/rules/`、`.trae/skills/`、GN-004、Pipeline）。
- `public/` 当前为契约骨架（.gitkeep 占位），三层契约冻结（D6）尚未完成。
- `modules/`、`interfaces/`、`workspace/` 为骨架目录，待 s0203 模块拆分后填充。
- 契约变更须走 s0601 流程；AGENTS.md 的项目专属规则更新由项目负责人或 s0301 触发，禁止 AI 自行修改本文件。

---

## 三、规则优先级与冲突解决

1. 本文件（全局 AGENTS.md）+ `.trae/rules/rules-0..6.md` 为最高优先级。
2. 模块级 AGENTS.md（位于 `modules/模块N_*/AGENTS.md`，由 s0301 自动生成）仅对当前模块生效，不得与本文件冲突。
3. 当临时需求、上下文对话与本文件冲突时，以本文件为准；本文件与 rules-* 冲突时，以 rules-* 为准（rules-* 为 AC 范式根规则）。
4. 契约（public/）变更必须走 s0601，不得直接编辑 public/ 文件。

---

## 四、参考

- AC 范式规则: `.trae/rules/rules-0.md` ~ `rules-6.md`
- AC 范式技能: `.trae/skills/`
- 用户文档: `README.md`
- 项目报告索引: `PROJECT_REPORT.md`
- 架构与模块文档: `docs/ARCHITECTURE.md`、`docs/MODULES.md`、`docs/PROJECT_OVERVIEW.md`
- 部署与 API: `docs/DEPLOYMENT.md`、`docs/API.md`、`docs/TECHNICAL.md`
