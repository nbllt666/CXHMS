# CXHMS 项目报告（索引）

> **文档版本**: v3.1.0 | **最后更新**: 2026-07-17
>
> 本文件原为 144KB 的完整功能与实现逻辑报告，已按主题拆分为三份独立文档以便维护与查阅。本文件保留为索引入口，下方提供项目概述与拆分文档导航。原始历史报告内容（v1.0.0, 2026-06-19）已分别迁移至下列三份文档，不再保留于本文件中。

## 项目概述

CXHMS (晨曦人格化记忆系统, CX-O History & Memory Service) 是一个基于 FastAPI 的智能记忆管理平台，提供完整的记忆存储、语义搜索、对话系统、ACP 协议通信、工具调用、图数据库、CXFC 插件协议，以及 **RADIX-Lite 管理 Agent 扩展**（模板引擎 / 多模态管线 / 蒸馏服务 / 决策核心）。系统采用前后端分离架构，后端使用 Python + FastAPI，前端使用 React + TypeScript，定位为面向人格化 Agent 的仿生记忆中间层服务。

### 技术栈概览

- **后端**: Python 3.10+ / FastAPI + Uvicorn / Pydantic v2 / SQLite + SQLAlchemy / httpx / Jinja2（RADIX-Lite 模板引擎）
- **前端**: React 18 + TypeScript / Vite 6 / Zustand + React Query / Tailwind CSS / Vitest
- **AI 与向量**: Ollama、OpenAI、Anthropic、DeepSeek、vLLM 兼容接口；Weaviate (默认)、Chroma、Milvus Lite、Qdrant；MCP / CXFC 协议；SQLite 知识图谱
- **RADIX-Lite v1.2.0 扩展**: Jinja2 DSL 模板引擎 + 3 worker 多模态管线（OCR / 视觉 / 文本）+ 7 状态机多轮蒸馏 + 6 决策点自主决策 + write_with_decision 决策化写入
- **Per-Agent 资源隔离**（v3.1.0 新增）: 每个 agent 独立 Weaviate collection（`CXHMSMemory_{agent_id}`，懒创建）+ 独立 SQLite 图数据库（`data/graph_{agent_id}.db`，懒加载），agent 删除时自动清理资源；`agent_id="default"` 时回退到共享 collection 与 `data/graph.db`（向后兼容）

### 当前默认配置（源自 `config/default.yaml`，唯一真相源）

| 项目 | 值 |
|------|-----|
| 主模型 | vLLM / `gemma4-e4b` @ http://localhost:8002，`temperature: 0.7` |
| 嵌入模型 | vLLM / `/models/Qwen3-Embedding-0.6B` @ http://localhost:8101 |
| 摘要/记忆副模型 | Ollama `qwen3-vl:8b`（默认禁用，`model_defaults` 回退主模型） |
| 后端 API | 0.0.0.0:8001（Swagger / ReDoc 同端口） |
| 前端开发服务器 | 3000 |
| 控制服务 | 8765 |
| RADIX-Lite 蒸馏服务 | 8011（`public/config_template/radix_config.json`） |
| 向量后端 | Weaviate @ 8090 (HTTP) / 50061 (gRPC)，`hybrid_search_enabled: false` |
| ACP 发现 | UDP 9999 / 广播 9998 |
| CXFC | `cxfc.enabled: true` |
| 图数据库 | `graph.enabled: true` |
| 上下文摘要保留 | `context.max_summaries_in_context: 10` |

### 三层契约版本

当前版本：**v1.2.0**（2026-07-16）

| 版本 | 日期 | 变更类型 | 内容摘要 |
|------|------|---------|---------|
| v1.0.0 | 2026-07-02 | MAJOR | 初始 5 schema + 5 .pyi + 3 config |
| v1.0.1 | 2026-07-04 | MINOR | 接口契约补全 + graph schema 新增 |
| v1.0.2 | 2026-07-04 | PATCH | jsonschema 严格化 |
| v1.1.0 | 2026-07-14 | MINOR | AnythingLLM 兼容层（2 schema + 1 .pyi） |
| v1.2.0 | 2026-07-16 | MINOR | RADIX-Lite 4 新模块契约（6 schema + 6 .pyi + 1 config + 6 Mock） |

详见 [public/schema/CHANGELOG.md](./public/schema/CHANGELOG.md)。

## 拆分文档导航

原报告的完整内容已按以下主题迁移：

| 新文档 | 路径 | 涵盖原报告章节 |
|--------|------|---------------|
| **项目总览** | [docs/PROJECT_OVERVIEW.md](./docs/PROJECT_OVERVIEW.md) | 项目概述、技术栈、核心功能列表、技术亮点、项目结构优势 |
| **架构文档** | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | 核心架构设计（启动流程、全局依赖注入）、核心业务流程图（消息处理/记忆检索评分/ACP 消息）、配置系统、部署架构、错误处理、性能优化、安全、扩展性、监控、版本兼容、开发规范 |
| **模块详解** | [docs/MODULES.md](./docs/MODULES.md) | API 路由系统、记忆管理、向量搜索、上下文管理、聊天对话、ACP 协议、LLM 客户端、工具系统、图数据库、CXFC、提醒/备份/插件/WebSocket/会话管理、异常处理、前端实现、测试体系 |

## RADIX-Lite 管理 Agent 扩展（v1.2.0 新增）

RADIX-Lite spec `add-management-agent-radix` 已于 2026-07-16 全生命周期闭合，产出 4 个新模块：

| 模块 | 核心文件 | 接口契约 | 测试 |
|------|---------|---------|------|
| 模块7_模板引擎 | `template_engine.py`（911 行） | `template_engine.pyi`（7 方法） | 24 passed |
| 模块8_多模态管线 | `multimodal_pipeline.py` + 3 workers（1242 行） | `multimodal_pipeline.pyi`（7 方法） | 28 passed |
| 模块9_蒸馏服务 | `distillation_service.py`（720 行） + 4 API 端点 | `distillation_service.pyi`（4 端点 + 1 内部方法） | 50 passed |
| 模块10_管理Agent扩展 | `decision_core.py`（580 行） + `agent_tools.py`（560 行） | `decision_core.pyi`（9 方法） + `agent_tools_v2.pyi`（8 工具方法） | 55 passed |

**核心能力**：
- **7 状态机多轮蒸馏**：draft → collecting → distilling → refining → reviewing → finalizing → finalized
- **6 决策点自主决策**：distill_start / distill_collect / distill_advance / distill_finalize / storage_decision / content_merge
- **write_with_decision 决策化写入**：`backend/core/memory/manager.py` 新增 3 方法 + `rejected_content` 表（保留 30 天）
- **Jinja2 DSL 模板引擎**：frontmatter 解析 + CRUD + 模板渲染
- **3 worker 多模态管线**：OCR / 视觉 / 文本 + 模态融合 + 降级开关

详见 [docs/MODULES.md](./docs/MODULES.md) 模块 7-10 章节。

## 其他相关文档

| 文档 | 路径 | 用途 |
|------|------|------|
| 部署指南 | [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | 环境要求、安装步骤、配置说明、Docker 部署、生产环境配置、故障排除 |
| API 文档 | [docs/API.md](./docs/API.md) | RESTful API 端点详细说明（聊天、记忆、上下文、ACP、工具、Agent、RADIX-Lite 等） |
| 技术文档 | [docs/TECHNICAL.md](./docs/TECHNICAL.md) | 核心模块技术细节（记忆系统、向量搜索、上下文、工具、ACP、图数据库、LLM 客户端、RADIX-Lite 子系统等） |
| 测试文档 | [TESTING.md](./TESTING.md) | 测试架构、运行方式、统计（1489 passed） |
| 用户入口 | [README.md](./README.md) | 快速上手、启动脚本、服务端口、项目结构 |
| AI 代理规则 | [AGENTS.md](./AGENTS.md) | AI 协同行为规则、模块边界、操作约束 |
| 契约变更日志 | [public/schema/CHANGELOG.md](./public/schema/CHANGELOG.md) | 三层契约版本演进历史 |

## 测试统计

| 套件 | 数量 | 位置 |
|------|------|------|
| 后端单元测试 | 753 passed | `tests/units/` + `tests/simulation/` |
| RADIX-Lite 单元测试 | 262 passed | `tests/contract/` |
| 接口契约测试 | 437 passed | `tests/contracts/` + `public/test_cases/` |
| E2E 测试 | 37 passed | `tests/e2e/`（含 `test_radix_task6_integration.py`） |
| 前端单元测试 | 19 文件 / 299 项 | `frontend/src/` |
| Playwright E2E | 2 文件 | `frontend/e2e/` |
| **合计** | **1489 passed** | — |

详见 [TESTING.md](./TESTING.md)。

## 历史版本信息

- **原始报告版本**: CXHMS v1.0.0
- **原始报告生成时间**: 2026-06-19
- **拆分时间**: 2026-07-02
- **本次重写时间**: 2026-07-17（v3.0.0）
- **本次增量更新时间**: 2026-07-17（v3.1.0）
- **拆分原因**: 原报告 144KB 单文件过大，不利于维护与查阅；按主题拆分后单文档均 < 50KB，并消除与 `config/default.yaml` 的配置不一致（端口、模型提供商、向量后端开关等）。
- **本次重写原因（v3.0.0）**: 反映 RADIX-Lite v1.2.0（2026-07-16 闭合）带来的所有变更，包括 4 个新模块、write_with_decision、契约版本升级、测试统计更新、配置项对齐 default.yaml 实际值。
- **本次增量更新原因（v3.1.0）**: 反映 Weaviate per-agent collection 改造（2026-07-17 闭合）带来的变更，包括 per-agent collection 隔离、懒创建机制、agent 生命周期集成、向后兼容设计、真实 Weaviate 端到端验证通过。详见 `.trae/documents/20260717_模块0_图数据库agent自建图.md`。

> 如需查阅拆分前的完整历史报告，可参考 git 历史中 2026-07-02 之前的 `PROJECT_REPORT.md` 版本。
