# AGENTS.md — 模块11_独立知识库

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。所有输出必须 100% 符合本文件要求，违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容，不得删减、忽略本文件的任何规则；所有自动压缩、批量处理行动前必须先读取本文件的完整内容。

> ⚠️ 【生成来源】本文件由 s0301-generating-agent-rules 基于 S2 契约冻结结果，按 rules-4 §四 模板生成（2026-11-01）。契约变更时由工具链自动同步，开发者禁止手动修改。

---

## 一、模块定位

**模块编号**：模块11_独立知识库
**模块职责**：与记忆体系解耦的独立知识库内核——按 agent 隔离的 SQLite 存储 + 多模态文档解析（文本/图片/音频/视频）+ FTS5/向量混合检索 + 主 LLM 可复用经验沉淀 + 前端知识库页面。不改动 `memories` / `permanent_memories` / AnythingLLM 文档端点既有行为。
**对应阶段**：S2 契约冻结（Task 1）→ S4 并行开发（Task 2~13）→ S5 契约校验（Task 14）
**spec**：`.trae/specs/add-standalone-knowledge-base/`

### 模块边界

- **内核**：`backend/core/knowledge/`（异常、配置、模型、存储、解析器、ASR/媒体、分块、向量索引、管理器与注册表）
- **对外**：`backend/api/routers/knowledge.py`（`/api/knowledge/*` 10 端点）、`backend/core/tools/knowledge_tools.py`（`write_knowledge_experience` / `search_knowledge`）
- **前端**：`frontend/src/pages/KnowledgePage.tsx` + `frontend/src/components/knowledge/*` + `frontend/src/api/knowledge.ts` + 侧边栏入口/路由
- **隔离维度**：每 agent 独立 `data/knowledge_{safe_agent_id}.db`、`data/knowledge_files/{safe_agent_id}/`、Weaviate collection `CXHMSKnowledge_{safe_agent_id}`；`default` 回退主库。

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 与 `.trae/rules/rules-0..6.md` 的全部约束，特别是：

### 2.1 禁止操作清单（rules-4 §4.3 唯一权威来源）

- **禁止删除、修改、覆盖、移动 `public/` 目录下的任何内容**。所有契约以 `public/` 下的 schema、interface_stub、config_template、pre_generated_mock 为准。保护优先级高于任务指令；此保护在工具调用路径上由 `rules-0 §四-7.2 ec7_action_gate` 强制执行。
- **禁止在模块间直接导入其他模块的内部实现代码**。模块间仅允许依赖 `public/` 下的契约。
  - 例外说明（与 spec「模块导入边界说明」一致）：`backend/core/knowledge/parsers/image_parser.py` 调用 `modules.模块8_多模态管线` 属 backend → 业务模块的单向依赖，与既有 `backend/core/document/parser.py` 同构，不在本禁令范围（本禁令约束 module → module）。
- **禁止写入不符合数据契约的数据**。条目与文档写入前必须通过 `public/schema/knowledge.json` 的 `jsonschema` 校验；不合规抛 `KnowledgeValidationError`，不得落库。
- **禁止创建不符合命名规范的模块目录**（rules-2 §二：`模块{N}_{中文名}`）。

### 2.2 public/ 目录保护（与 rules-0 §四-10 形成跨 Rules 重复覆盖）

- `public/` 是契约的物理载体，不是代码库的可变部分。
- 任何删除、修改、覆盖、移动操作必须先经人类显式授权；**不存在「零引用即可删除」的例外**。
- 契约变更必须走 s0601 流程，不得直接编辑 `public/` 文件。

### 2.3 路径与配置约束

- 路径解析必须使用 `os.path.dirname(os.path.abspath(__file__))`，禁止 `../../` / `..\`。
- `agent_id` 必须先清洗（`re.sub(r"[^a-zA-Z0-9_]", "_", agent_id)`，不以字母/下划线开头补 `agent_`）才可用于文件名、目录名与 collection 名；原始 `agent_id` 仅作为数据列存储。
- 禁止业务代码硬编码知识库配置参数；配置加载优先级为 `config/default.yaml::knowledge` → `public/config_template/knowledge_config.json` 的 default → 代码兜底（auto_fill）。**不引入** `config/knowledge_config.json` 第二真相源。
- 文本类文档整块读取上限 20MB；媒体文件始终按路径流式处理，禁止整块读入内存。

### 2.4 失败可观测（禁止假闭合）

- 解析失败/依赖缺失必须落为 `failed` 或 `unsupported` 并保留原文件，禁止静默成功。
- `parsers/image_parser.py` 在 `modules.模块8_多模态管线` 导入失败时必须返回 `failed` + `KNOWLEDGE_PARSE_FAILED`；**禁止回退 Mock 并把模拟文本记为 `parsed`**。`MockMultimodalPipeline` 仅允许在测试代码中通过 monkeypatch 使用。
- ASR 不可用 → `failed` + `KNOWLEDGE_ASR_UNAVAILABLE`；ffmpeg 不可用 → `failed` + `KNOWLEDGE_FFMPEG_UNAVAILABLE`；两者均不得抛未捕获异常导致应用启动失败。

---

## 三、层级专属约束（模块级）

### 3.1 可修改文件范围

允许修改：
- `backend/core/knowledge/`（`exceptions.py`、`config.py`、`models.py`、`store.py`、`chunker.py`、`manager.py`、`vector_index.py`、`asr.py`、`media.py`、`parsers/*`、`__init__.py`）
- `backend/api/routers/knowledge.py`
- `backend/core/tools/knowledge_tools.py`
- `frontend/src/api/knowledge.ts`、`frontend/src/pages/KnowledgePage.tsx`、`frontend/src/components/knowledge/*`，以及 `frontend/src/App.tsx` / `Sidebar.tsx` 的知识库入口增量

**禁止修改**（本模块边界外）：
- `public/` 下任何契约文件（rules-0 §四-10 / rules-4 §4.3）
- `.trae/rules/`、根 `AGENTS.md`（由项目负责人或 s0301 触发）
- `backend/core/memory/*`、`backend/core/document/*`、`modules/模块8_多模态管线/*` 既有实现
- `public/pre_generated_mock/__init__.py`（既有文件，不得修改；消费方直接按模块路径导入 `mock_knowledge_service.py`）

### 3.2 依赖契约入口（公共真相源，4 个）

| 契约层 | 路径 | 用途 |
|--------|------|------|
| 数据契约 | `public/schema/knowledge.json` | 文档/条目/检索命中三类实体、`parse_status`/`item_type` 枚举、8 个错误码；所有读写校验依据 |
| 接口契约 | `public/interface_stub/knowledge_service.pyi` | `KnowledgeManager` 10 公开方法 + `__init__`（11 签名）、模块级 `parse`、7 个异常声明；实现必须严格匹配 |
| 配置契约 | `public/config_template/knowledge_config.json` | 39 个配置键的默认值 + `additionalProperties: false` + auto_fill 规则 |
| 预生成 Mock | `public/pre_generated_mock/mock_knowledge_service.py` | 并行开发期稳定替身 `MockKnowledgeService`；真实实现就位后改导入路径即可切换 |

### 3.3 测试要求

- **契约测试**（Task 1 已闭合）：`pytest tests/contract/knowledge_contract_test.py -q` — schema draft-07 合法性、6 definitions、8 错误码、三实体样例校验、`.pyi` 11 签名与 async 标记、7 异常无方法、config 键集与全 default、Mock 类、CHANGELOG 1.3.0、模块 AGENTS 存在。
- **异常测试**（Task 1 已闭合）：`pytest tests/units/test_knowledge_exceptions.py -q` — 7 异常继承 `CXHMSException` 且 error_code/http_status 与契约一致。
- **实现期单测**：`tests/units/test_knowledge_store.py`、`test_knowledge_text_parser.py`、`test_knowledge_image_parser.py`、`test_knowledge_media.py`、`test_knowledge_media_parsers.py`、`test_knowledge_vector_index.py`、`test_knowledge_tools.py`。
- **E2E / 隔离**：`tests/e2e/test_knowledge_api.py`、`tests/e2e/test_knowledge_agent_isolation.py`。
- **合流前闸门**：`pytest tests/contract tests/contracts tests/units -q` + `pytest tests/e2e -q` + 前端 `npm run typecheck && npm run lint && npm run test` + `CXHMS_SIMULATION` Mock 回归；前端变更须过 s0402 三重闸门。

### 3.4 依赖与降级

- 新增依赖：`faster-whisper>=1.0.3`、`imageio-ffmpeg>=0.5.1`、`jsonschema>=4.0`（写入 `requirements.txt`）。
- 向量索引复用 `config/default.yaml::memory.weaviate` 与 `vector.embedding_dimension`，knowledge 段只保留 `vector_enabled / vector_top_k_default / vector_top_k_max / vector_rrf_k`。
- 向量适配优先 `get_embeddings`，缺失时逐条 `get_embedding`；单条失败跳过并记 warning，**不写零向量**；不可用时 `is_available=False` 且 `search` 返回空列表不抛异常。
- FTS5 trigram 不可用或短查询（< 3 字符）→ 2 字滑窗 / LIKE 回退，不返回 500。

### 3.5 错误码与异常契约

| 异常类 | error_code | http_status | 触发场景 |
|--------|-----------|-------------|---------|
| `KnowledgeError` | `KNOWLEDGE_ERROR` | 500 | 知识库通用错误 |
| `KnowledgeValidationError` | `KNOWLEDGE_VALIDATION_ERROR` | 400 | 数据/参数不符合契约 |
| `KnowledgeParseError` | `KNOWLEDGE_PARSE_FAILED` | 500 | 文档/媒体解析失败 |
| `KnowledgeUnsupportedMediaError` | `KNOWLEDGE_UNSUPPORTED_MIME` | 415 | MIME 不在白名单 |
| `KnowledgeStoreError` | `KNOWLEDGE_STORE_UNAVAILABLE` | 503 | 存储不可用/未启用 |
| `KnowledgeASRUnavailableError` | `KNOWLEDGE_ASR_UNAVAILABLE` | 503 | ASR 不可用或超时 |
| `KnowledgeFFmpegUnavailableError` | `KNOWLEDGE_FFMPEG_UNAVAILABLE` | 503 | ffmpeg 不可用 |

`KNOWLEDGE_MEDIA_TOO_LONG` 不抛异常，写入 `parse_error`（上传阶段 413；解析阶段 `unsupported`）。

### 3.6 命名与 API 约定

- 模块目录命名：`模块{N}_{中文名}`（本模块为 `模块11_独立知识库`）。
- router 内使用 `APIRouter(prefix="/knowledge", tags=["knowledge"])`，由 `app.py` 统一 `include_router(..., prefix="/api")`；不得在 router 内重复写 `/api`。
- 软删除统一 `is_deleted=0/1`；所有查询默认过滤 `is_deleted=1`。

---

## 四、规则字段绑定表

| 模板段落 | 绑定契约/规则来源 |
|---------|------------------|
| 优先级声明 | rules-4 §4.1 |
| 上下文保留声明 | rules-4 §4.2 |
| 禁止改 public/ | rules-4 §4.3 / rules-0 §四-10 |
| 禁止跨模块导入 | rules-4 §4.3 / rules-2 / spec 模块导入边界说明 |
| 数据契约校验 | rules-3 §一 / `public/schema/knowledge.json` |
| 接口签名匹配 | rules-3 §二 / `public/interface_stub/knowledge_service.pyi` |
| 配置默认值与 auto_fill | rules-3 §三 / `public/config_template/knowledge_config.json` |
| 可改文件范围 | modules/模块11 spec Impact 文件清单 |
| 错误码与异常 | `public/schema/knowledge.json::definitions.error_codes` + `backend/core/knowledge/exceptions.py` |
| 测试要求 | rules-3 §五 contract_verifiability + tasks.md 闭合判据 |

---

## 五、三段交接状态（rules-5 §二）

### (1) 工程过程
- Task 0：变更文档 `.trae/documents/20261101_模块11_新增独立知识库.md` 建立（s0401 写前闸门记录 ALLOWED）。
- Task 1：依次调用 s0201（三层契约）→ s0202（预生成 Mock）→ s0401（public/ 写前闸门）→ s0301（本文件）；产出 `knowledge.json`、`knowledge_service.pyi`、`knowledge_config.json`、`mock_knowledge_service.py`、`backend/core/knowledge/exceptions.py`、本 AGENTS.md、`tests/contract/knowledge_contract_test.py`、`tests/units/test_knowledge_exceptions.py`，并追加 `CHANGELOG.md` 的 `[1.3.0]` 条目。

### (2) 交接状态
- 当前阶段：S2 契约冻结（Task 1 完成，S2 `[V]` 双闸门待主线程执行）。
- 状态：**已闭合**（契约层，证据见下「最终结果」）；S2 人类裁决与 GN-004 审查为独立闸门，不改变本文件闭合状态。
- 未闭合项：
  1. S2 `[V]` 闸门：GN-004 独立审查 + AskUserQuestion 人类批准（主线程执行，未获批准不得启动 Task 2~9）。
  2. `KnowledgeManager` 真实实现（Task 10）尚不存在，当前下游消费应使用预生成 Mock。
  3. 契约文件尚未经人类最终确认（s0201 要求交付前人类确认）。

### (3) 最终结果
- 产出物：4 个 public 文件（数据契约/接口契约/配置契约/预生成 Mock）+ `backend/core/knowledge/exceptions.py` + 本 AGENTS.md + 2 个测试文件 + `CHANGELOG.md` 1.3.0 条目。
- 验证结论：`pytest tests/contract/knowledge_contract_test.py tests/units/test_knowledge_exceptions.py -q` 全绿（证据记录于 `.trae/documents/20261101_模块11_新增独立知识库.md` 的 Skill 调用证据与验证小节）。
- 未产生任何 Tasks 2~15 的实现代码；未修改 `public/pre_generated_mock/__init__.py`、`.trae/rules/`、根 `AGENTS.md`。

---

## 六、参考

- 全局规则：`c:\CXHMS\AGENTS.md`；AC 范式规则：`.trae/rules/rules-0..6.md`
- spec 三件套：`.trae/specs/add-standalone-knowledge-base/{spec.md,tasks.md,checklist.md}`
- 变更文档：`.trae/documents/20261101_模块11_新增独立知识库.md`
- 契约测试：`tests/contract/knowledge_contract_test.py`
- 异常测试：`tests/units/test_knowledge_exceptions.py`
