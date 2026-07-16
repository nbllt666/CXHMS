# CXHMS (晨曦人格化记忆系统)

> **文档版本**: v3.1.0 | **最后更新**: 2026-07-17

CXHMS (CX-O History & Memory Service) 是一个智能记忆管理平台，提供长期记忆存储、语义搜索、自动归档、多模型对话、ACP 协议通信、图数据库、CXFC 插件协议、工具调用以及 RADIX-Lite 管理 Agent 扩展（模板引擎 / 多模态管线 / 蒸馏服务 / 决策核心）功能。

## 核心特性

- **智能记忆系统**: 多向量存储后端（Milvus Lite/Chroma/Qdrant/Weaviate/Weaviate Embedded）、双阶段指数衰减+艾宾浩斯遗忘曲线、三维评分、混合搜索、情感分析、去重检测、副模型路由、write_with_decision 决策化写入（含 rejected_content 30 天保留）、**per-agent collection 隔离**（每个 agent 独立 Weaviate collection + SQLite 图数据库，懒创建+生命周期清理）
- **RADIX-Lite 管理 Agent 扩展**（v1.2.0 新增）:
  - **模块7 模板引擎**: Jinja2 DSL 模板渲染 + frontmatter 解析 + CRUD
  - **模块8 多模态管线**: 3 worker（OCR / 视觉 / 文本）+ 模态融合 + 降级开关
  - **模块9 蒸馏服务**: 7 状态机多轮蒸馏（draft→collecting→distilling→refining→reviewing→finalizing→finalized）+ 4 API 端点
  - **模块10 管理Agent扩展**: 6 决策点自主决策（distill_start / distill_collect / distill_advance / distill_finalize / storage_decision / content_merge）+ 8 工具方法 + rubric 驱动
- **图数据库**: 知识图谱、语义搜索、路径分析、社区检测、PageRank、GraphML/DOT 导出、**per-agent 懒加载**（每个 agent 独立 `data/graph_{agent_id}.db`，首次使用图功能时创建，agent 删除时清理）
- **ACP 协议**: 局域网自动发现、点对点通信、群组协同
- **CXFC 插件协议**: 插件发现、技能注册、心跳管理、事件推送
- **工具生态**: MCP 协议支持、内置工具（calculator/datetime/random/json_format）、主模型工具（write_long_term_memory/search_all_memories/call_assistant/set_alarm/mono/write_permanent_memory/ACP工具）、摘要工具、记忆管理工具（16个）、图工具
- **对话系统**: 流式响应、RAG 检索增强、多 Agent 支持、多模态视觉、WebSocket 实时通信
- **双通信模式**: WebSocket + SSE fallback，自动降级保障连接可靠性
- **连接检测与动态配置**: ConnectionCheck 组件实时检测后端连接状态，支持动态配置切换
- **视觉/多模态支持**: 图片上传与识别，支持视觉模型多模态对话
- **提醒系统**: 定时提醒、闹钟管理
- **备份恢复**: 选择性备份、导入导出
- **控制服务**: 独立端口 8765，管理后端启停
- **配置系统**: YAML 配置 + 环境变量 + 自动修复 + 验证
- **国际化**: i18next 多语言支持（zh-CN/en-US）
- **LLM E2E 测试**: 自动化质量评判框架

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- vLLM（默认主模型 / Embedding 服务）或 Ollama（副模型，可选）

### 安装启动

```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 准备模型服务（默认使用 vLLM）
#    主模型 gemma4-e4b 由 vLLM 提供：http://localhost:8002
#    Embedding 模型 Qwen3-Embedding-0.6B 由 vLLM 提供：http://localhost:8101
#    摘要/记忆副模型（可选）使用 Ollama: ollama pull qwen3-vl:8b

# 3. 启动后端
python main.py

# 4. 安装并启动前端
cd frontend && npm install && npm run dev
```

**Windows 启动脚本**（位于项目根目录）：

| 脚本 | 用途 |
|------|------|
| `2-1.重建环境.bat` | 重建 Conda 环境 |
| `2-2.安装依赖.bat` | 安装后端/前端依赖 |
| `2.启动后端(Conda环境).bat` | 在 Conda 环境中启动后端 |
| `3.启动后端(系统环境).bat` | 在系统 Python 环境中启动后端 |
| `7.激活conda环境.bat` | 激活 Conda 环境 |

### 服务地址

| 服务 | 地址 |
|------|------|
| API 服务 | http://localhost:8001 |
| API 文档 (Swagger) | http://localhost:8001/docs |
| API 文档 (ReDoc) | http://localhost:8001/redoc |
| 前端界面 | http://localhost:3000 |
| 控制服务 | http://localhost:8765 |
| vLLM 主模型 | http://localhost:8002 |
| vLLM Embedding | http://localhost:8101 |
| Weaviate 向量库 | http://localhost:8090 |
| RADIX-Lite 蒸馏服务 | http://localhost:8011 |

> **注意**: API 默认端口为 8001、前端开发服务器为 3000、控制服务为 8765、vLLM 主模型为 8002、RADIX-Lite 蒸馏服务为 8011（见 `config/default.yaml` 与 `public/config_template/radix_config.json`）。前端开发服务器通过代理转发请求至 8001 端口，Swagger/ReDoc 文档可通过前端代理访问。

## 主要 API

| 端点 | 描述 |
|------|------|
| `POST /api/chat/stream` | 流式聊天 |
| `POST /api/chat` | 同步聊天 |
| `POST /api/memory-agent/chat/stream` | 记忆管理 Agent 对话 |
| `GET/POST /api/memories` | 记忆管理 |
| `POST /api/memories/search` | 记忆搜索 |
| `POST /api/memories/semantic-search` | 语义搜索 |
| `POST /api/memories/rag` | RAG 检索 |
| `POST /api/memories/3d` | 3D 评分搜索 |
| `POST /api/memories/batch/*` | 批量操作（write/update/delete/tags/archive/restore/tag-by-query/delete-by-query/archive-by-query） |
| `POST /api/memories/write-with-decision` | 决策化写入（含 rejected_content 保留，v1.2.0 新增） |
| `GET /api/memories/rejected-content` | 获取拒绝写入内容（30 天保留） |
| `DELETE /api/memories/rejected-content/cleanup-expired` | 清理过期拒绝内容 |
| `GET/POST /api/agents` | Agent 管理（含 tools_config / decision_rubric / distillation_enabled 字段） |
| `GET/POST /api/tools` | 工具管理 |
| `POST /api/acp/discover` | Agent 发现 |
| `GET/POST /api/nodes` | 图节点管理 |
| `GET/POST /api/edges` | 图边管理 |
| `POST /api/traverse/bfs\|dfs` | 图遍历 |
| `GET/POST /api/vector/*` | 向量数据库管理 |
| `GET/POST /api/cxfc/*` | CXFC 插件管理 |
| `GET/PUT /api/config` | 配置管理 |
| `GET /api/stats` | 统计信息 |
| `POST /api/archive/*` | 归档管理 |
| `GET/POST /api/backups` | 备份恢复 |
| `POST /api/radix/distillation/*` | RADIX-Lite 蒸馏服务（start/advance/finalize/get，端口 8011） |
| `WS /ws/{agent_id}` | WebSocket |
| `GET /api/service/*` | 服务管理 |
| `GET /api/admin/*` | 管理员 |

完整 API 文档: http://localhost:8001/docs

## 项目结构

```
CXHMS/
├── backend/                # Python 后端 (FastAPI)
│   ├── api/routers/        # API 路由 (17 个路由模块：acp/admin/agents/archive/backup/chat/config/context/cxfc/graph/memory/memory_chat/service/stats/tools/vector/websocket)
│   ├── core/               # 核心模块 (13 个子模块：acp/alarm/backup/context/cxfc/document/graph/llm/memory/plugins/session/tools/websocket)
│   ├── models/             # 数据模型 (acp.py, context.py, memory.py)
│   ├── cache.py            # 缓存
│   ├── exceptions.py       # 异常定义
│   ├── logging_config.py   # 日志配置
│   ├── model_router.py     # 模型路由
│   ├── utils.py            # 工具函数
│   └── control_service.py  # 控制服务 (端口 8765)
├── frontend/               # React 前端
│   └── src/
│       ├── pages/          # 页面组件 (9 个页面)
│       ├── components/     # UI 组件库 + 布局组件 + 功能组件
│       ├── store/          # 状态管理 (chatStore + themeStore)
│       ├── hooks/          # 自定义 Hooks (useWebSocket + useHotkey)
│       ├── i18n/           # 国际化 (zh-CN + en-US)
│       ├── api/            # API 客户端
│       └── styles/         # 样式文件
├── config/                 # 配置文件
│   ├── default.yaml        # 默认配置（真相源）
│   ├── env.py              # 环境变量
│   ├── validation.py       # 配置验证
│   ├── repair.py           # 配置修复
│   └── settings.py         # 设置加载
├── modules/                # 业务模块区（AC 范式：11 个模块）
│   ├── 模块0_全局调度面板/    # 全局调度与进度监控
│   ├── 模块1_记忆服务/        # 记忆存储与搜索
│   ├── 模块2_对话服务/        # 对话与上下文
│   ├── 模块3_工具与ACP/       # 工具系统与 ACP 协议
│   ├── 模块4_图数据库/        # 知识图谱
│   ├── 模块5_前端展示/        # React 前端
│   ├── 模块6_辅助服务/        # 提醒 / 备份 / 插件 / WebSocket / 会话
│   ├── 模块7_模板引擎/        # Jinja2 DSL 模板引擎（RADIX-Lite）
│   ├── 模块8_多模态管线/      # 3 worker 多模态预处理（RADIX-Lite）
│   ├── 模块9_蒸馏服务/        # 7 状态机多轮蒸馏（RADIX-Lite）
│   └── 模块10_管理Agent扩展/  # 6 决策点 + 8 工具方法（RADIX-Lite）
├── interfaces/             # 入口层（app.py / main.py / start.bat）
├── workspace/              # 用户数据区
├── public/                 # 全局公共资源区（只读契约载体，AC 范式真相源）
│   ├── schema/             # 数据契约 (13 份 JSON Schema，v1.2.0)
│   ├── interface_stub/      # 接口契约 (13 份 .pyi 存根，v1.2.0)
│   ├── config_template/    # 配置契约模板 (5 份，含 radix_config.json)
│   ├── pre_generated_mock/ # 预生成 Mock（12 份，并行开发支点）
│   ├── global_mock/        # 全局可自定义 Mock
│   ├── test_cases/         # 通用测试用例
│   └── dependencies/      # 依赖锁定
├── scripts/                # 脚本目录
├── data/                   # 运行时数据 (SQLite/向量库等)
│   ├── agents.json         # Agent 配置（含 RADIX-Lite tools_config / decision_rubric / distillation_enabled）
│   ├── graph_{agent_id}.db # per-agent 图数据库（懒创建，agent 删除时清理）
│   └── graph.db            # default agent 图数据库（向后兼容）
├── logs/                   # 运行日志
└── docs/                   # 文档
    ├── API.md              # API 文档
    ├── ARCHITECTURE.md     # 架构文档
    ├── DEPLOYMENT.md       # 部署指南
    ├── TECHNICAL.md        # 技术文档
    ├── PROJECT_OVERVIEW.md # 项目概述
    └── MODULES.md          # 模块详解
```

## 配置

主配置文件: `config/default.yaml`（端口、模型等以该文件为真相源）

```yaml
server:
  host: 0.0.0.0
  port: 8001          # API 服务端口

models:
  main:               # 默认主模型
    provider: vllm
    host: http://localhost:8002
    model: gemma4-e4b
    enabled: true
    temperature: 0.7
  embedding:          # 默认 Embedding 模型
    provider: vllm
    host: http://localhost:8101
    model: /models/Qwen3-Embedding-0.6B
    enabled: true
  summary:            # 摘要副模型（默认禁用，回退到 main）
    provider: ollama
    model: qwen3-vl:8b
    enabled: false
  memory:             # 记忆副模型（默认禁用，回退到 main）
    provider: ollama
    model: qwen3-vl:8b
    enabled: false

model_defaults:
  summary: main
  memory: main

memory:
  vector_backend: weaviate
  decay_model: exponential
  decay_rate: 0.1
  decay_interval_days: 7
  reactivation_boost: 0.2
  emotion_enabled: true
  hybrid_search_enabled: false   # 默认关闭
  archive_enabled: true
  dedup_threshold: 0.85

context:
  max_summaries_in_context: 10    # 上下文摘要保留数量

cxfc:
  enabled: true                  # CXFC 插件协议启用

graph:
  enabled: true                  # 图数据库启用
  weaviate:
    grpc_port: 50061             # gRPC 端口

llm:
  max_tool_rounds: 10            # 流式与非流式统一
  temperature: 1.5
```

> RADIX-Lite 子系统配置见 `public/config_template/radix_config.json`（5 段：distillation_service / multimodal_pipeline / template_engine / decision_core / vllm）。

## Per-Agent 资源隔离（v3.1.0 新增）

系统为每个 agent 提供独立的资源隔离层，确保 agent 间数据完全隔离：

**Weaviate per-agent collection**：
- 每个 agent 动态创建独立 collection：`CXHMSMemory_{agent_id}`（agent_id 中非字母数字字符替换为下划线）
- **懒创建**：首次写入记忆时才创建 collection，不预建
- **向后兼容**：`agent_id="default"` 时回退到 `CXHMSMemory` collection（与改造前行为一致）
- **生命周期清理**：删除 agent 时自动清理对应的 Weaviate collection

**图数据库 per-agent 懒加载**：
- 每个 agent 独立 SQLite 图数据库文件：`data/graph_{agent_id}.db`
- **懒创建**：agent 首次使用图功能时才创建 db 文件
- **生命周期清理**：删除 agent 时自动清理图数据库实例 + db 文件

**端到端验证**（2026-07-16）：真实 Weaviate 环境下 6 步骤验证全部通过（创建 agent → 写入记忆 → 检查 collection → 验证隔离 → 删除验证清理 → 无残留）。

详见变更文档 [`.trae/documents/20260717_模块0_图数据库agent自建图.md`](.trae/documents/20260717_模块0_图数据库agent自建图.md)。

## 技术栈

**后端**: FastAPI, Pydantic v2, SQLite, Milvus Lite/Chroma/Qdrant/Weaviate, Ollama/vLLM/OpenAI/Anthropic/DeepSeek, httpx, psutil, Jinja2（RADIX-Lite 模板引擎）
**前端**: React 18.3.1, TypeScript 5.7.2, Vite 6.0.6, Tailwind CSS 3.4.17, Zustand 5.0.2, React Query 5.62.11, i18next 25.8.4, Framer Motion 11.15.0, Recharts 2.15.0, Lucide React 0.469.0, Axios 1.7.9, React Markdown 9.0.1, date-fns 4.1.0

## 开发

### 后端开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行后端单元测试
python -m pytest tests/ -v

# 运行 RADIX-Lite 单元测试
python -m pytest tests/contract/ -v

# 运行契约测试
python -m pytest public/test_cases/ -v

# 运行 E2E 测试（依赖真实 vLLM）
python -m pytest tests/e2e/ -v

# 运行测试覆盖率
python -m pytest --cov=backend --cov-report=term-missing

# LLM E2E 测试
cd backend/tests/llm_e2e && python main.py

# 代码格式化
black backend/
isort backend/
```

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build

# 类型检查
npm run typecheck

# 代码格式化
npm run format

# 运行测试
npm run test

# 测试覆盖率
npm run test:coverage
```

## 测试统计

| 套件 | 数量 | 位置 |
|------|------|------|
| 后端单元测试 | 753 passed | `tests/units/` + `tests/simulation/` |
| RADIX-Lite 单元测试 | 262 passed | `tests/contract/` |
| 接口契约测试 | 437 passed | `tests/contracts/` |
| E2E 测试 | 37 passed | `tests/e2e/` |
| 前端单元测试 | 19 文件 / 299 项 | `frontend/src/` |
| Playwright E2E | 2 文件 | `frontend/e2e/` |
| **合计** | **1489 passed** | — |

详见 [TESTING.md](./TESTING.md)。

## 文档

- [项目概述](docs/PROJECT_OVERVIEW.md)
- [架构文档](docs/ARCHITECTURE.md)
- [模块详解](docs/MODULES.md)
- [API 文档](docs/API.md)
- [部署指南](docs/DEPLOYMENT.md)
- [技术文档](docs/TECHNICAL.md)
- [测试文档](TESTING.md)
- [项目报告索引](PROJECT_REPORT.md)
- [AI 协同规则](AGENTS.md)
- [契约变更日志](public/schema/CHANGELOG.md)

## 契约版本

当前三层契约版本：**v1.2.0**（2026-07-16）

- v1.0.0（2026-07-02）：初始 5 schema + 5 .pyi + 3 config
- v1.0.1（2026-07-04）：接口契约补全 + graph schema 新增
- v1.0.2（2026-07-04）：jsonschema 严格化
- v1.1.0（2026-07-14）：AnythingLLM 兼容层
- v1.2.0（2026-07-16）：RADIX-Lite 4 新模块契约（6 schema + 6 .pyi + 1 config + 6 Mock）

详见 [public/schema/CHANGELOG.md](public/schema/CHANGELOG.md)。

## 许可证

MIT License
