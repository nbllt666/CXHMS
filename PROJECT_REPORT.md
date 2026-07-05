# CXHMS 项目报告（索引）

> **文档版本**: v2.3.0 | **最后更新**: 2026-07-02
>
> 本文件原为 144KB 的完整功能与实现逻辑报告，已按主题拆分为三份独立文档以便维护与查阅。本文件保留为索引入口，下方提供项目概述与拆分文档导航。原始历史报告内容（v1.0.0, 2026-06-19）已分别迁移至下列三份文档，不再保留于本文件中。

## 项目概述

CXHMS (晨曦人格化记忆系统, CX-O History & Memory Service) 是一个基于 FastAPI 的智能记忆管理平台，提供完整的记忆存储、语义搜索、对话系统、ACP 协议通信和工具调用功能。系统采用前后端分离架构，后端使用 Python + FastAPI，前端使用 React + TypeScript，定位为面向人格化 Agent 的仿生记忆中间层服务。

### 技术栈概览

- **后端**: Python 3.10+ / FastAPI + Uvicorn / Pydantic v2 / SQLite + SQLAlchemy / httpx
- **前端**: React 18 + TypeScript / Vite 6 / Zustand + React Query / Tailwind CSS / Vitest
- **AI 与向量**: Ollama、OpenAI、Anthropic、DeepSeek、vLLM 兼容接口；Weaviate (默认)、Chroma、Milvus Lite、Qdrant；MCP / CXFC 协议；SQLite 知识图谱

### 当前默认配置（源自 `config/default.yaml`，唯一真相源）

| 项目 | 值 |
|------|-----|
| 主模型 | vLLM / `gemma4-e4b` @ http://localhost:8002 |
| 嵌入模型 | vLLM / `/models/Qwen3-Embedding-0.6B` @ http://localhost:8101 |
| 摘要/记忆副模型 | Ollama `qwen3-vl:8b`（默认禁用，回退主模型） |
| 后端 API | 0.0.0.0:8001（Swagger / ReDoc 同端口） |
| 前端开发服务器 | 3000 |
| 控制服务 | 8765 |
| 向量后端 | Weaviate @ 8090 (HTTP) / 50051 (gRPC)，`hybrid_search_enabled: false` |
| ACP 发现 | UDP 9999 / 广播 9998 |

## 拆分文档导航

原报告的完整内容已按以下主题迁移：

| 新文档 | 路径 | 涵盖原报告章节 |
|--------|------|---------------|
| **项目总览** | [docs/PROJECT_OVERVIEW.md](./docs/PROJECT_OVERVIEW.md) | 项目概述、技术栈、核心功能列表、技术亮点、项目结构优势 |
| **架构文档** | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | 核心架构设计（启动流程、全局依赖注入）、核心业务流程图（消息处理/记忆检索评分/ACP 消息）、配置系统、部署架构、错误处理、性能优化、安全、扩展性、监控、版本兼容、开发规范 |
| **模块详解** | [docs/MODULES.md](./docs/MODULES.md) | API 路由系统、记忆管理、向量搜索、上下文管理、聊天对话、ACP 协议、LLM 客户端、工具系统、图数据库、CXFC、提醒/备份/插件/WebSocket/会话管理、异常处理、前端实现、测试体系 |

## 其他相关文档

| 文档 | 路径 | 用途 |
|------|------|------|
| 部署指南 | [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | 环境要求、安装步骤、配置说明、Docker 部署、生产环境配置、故障排除 |
| API 文档 | [docs/API.md](./docs/API.md) | RESTful API 端点详细说明（聊天、记忆、上下文、ACP、工具、Agent 等） |
| 技术文档 | [docs/TECHNICAL.md](./docs/TECHNICAL.md) | 核心模块技术细节（记忆系统、向量搜索、上下文、工具、ACP、图数据库、LLM 客户端等） |
| 用户入口 | [README.md](./README.md) | 快速上手、启动脚本、服务端口、项目结构 |
| AI 代理规则 | [AGENTS.md](./AGENTS.md) | AI 协同行为规则、模块边界、操作约束 |

## 历史版本信息

- **原始报告版本**: CXHMS v1.0.0
- **原始报告生成时间**: 2026-06-19
- **拆分时间**: 2026-07-02
- **拆分原因**: 原报告 144KB 单文件过大，不利于维护与查阅；按主题拆分后单文档均 < 50KB，并消除与 `config/default.yaml` 的配置不一致（端口、模型提供商、向量后端开关等）。

> 如需查阅拆分前的完整历史报告，可参考 git 历史中 2026-07-02 之前的 `PROJECT_REPORT.md` 版本。
