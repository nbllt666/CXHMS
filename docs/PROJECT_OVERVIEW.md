# CXHMS 项目总览

> **文档版本**: v2.3.0 | **最后更新**: 2026-07-02
>
> 本文为 CXHMS 项目总览文档，汇总项目定位、技术栈与核心特性。架构细节见 [ARCHITECTURE.md](./ARCHITECTURE.md)，模块与 API 细节见 [MODULES.md](./MODULES.md)，部署与接口见 [DEPLOYMENT.md](./DEPLOYMENT.md) / [API.md](./API.md)。

## 项目概述

CXHMS (晨曦人格化记忆系统, CX-O History & Memory Service) 是一个基于 FastAPI 的智能记忆管理平台，提供完整的记忆存储、语义搜索、对话系统、ACP 协议通信和工具调用功能。系统采用前后端分离架构，后端使用 Python + FastAPI，前端使用 React + TypeScript，定位为面向人格化 Agent 的仿生记忆中间层服务。

## 技术栈

**后端技术**
- 框架: Python 3.10+ / FastAPI + Uvicorn
- 数据验证: Pydantic v2
- 数据库: SQLite + SQLAlchemy
- HTTP 客户端: httpx 异步支持
- 测试框架: pytest + pytest-asyncio

**前端技术**
- 框架: React 18 + TypeScript
- 构建工具: Vite 6
- 状态管理: Zustand + React Query
- 国际化: i18next + react-i18next
- 样式: Tailwind CSS
- 测试: Vitest + jsdom

**AI 与向量**
- LLM 集成: Ollama、OpenAI、Anthropic、DeepSeek、vLLM 兼容接口
- 向量数据库: Weaviate (默认)、Chroma、Milvus Lite、Qdrant
- 工具协议: MCP (Model Context Protocol)、CXFC (插件协议)
- 图数据库: SQLite 知识图谱

**当前默认配置** (源自 `config/default.yaml`，作为唯一真相源)
- 主模型: vLLM / `gemma4-e4b` @ http://localhost:8002
- 嵌入模型: vLLM / `/models/Qwen3-Embedding-0.6B` @ http://localhost:8101
- 摘要/记忆副模型: Ollama `qwen3-vl:8b` (默认禁用，回退到主模型)
- 后端 API: 0.0.0.0:8001 (Swagger/ReDoc 同端口)
- 前端开发服务器: 3000
- 控制服务: 8765
- 向量后端: Weaviate @ 8090 (HTTP) / 50051 (gRPC)，`hybrid_search_enabled: false`
- ACP 发现: UDP 9999 / 广播 9998

## 核心功能列表

| 功能模块 | 功能项 | 状态 | 说明 |
|---------|-------|------|------|
| **记忆管理** | 记忆 CRUD | 已实现 | 支持创建、读取、更新、删除 |
| | 语义搜索 | 已实现 | 基于向量的相似度搜索 |
| | 混合搜索 | 已实现 | 向量 + 关键词融合搜索 |
| | 记忆衰减 | 已实现 | 双阶段指数衰减 + 艾宾浩斯遗忘曲线 |
| | 归档管理 | 已实现 | 智能去重、层级压缩 |
| | 情感分析 | 已实现 | 记忆情感标记 |
| **对话系统** | 聊天对话 | 已实现 | 支持流式/非流式 |
| | Agent 配置 | 已实现 | 灵活的系统提示词 |
| | 上下文管理 | 已实现 | 会话历史、Mono 上下文 |
| | 记忆增强 | 已实现 | RAG 检索增强生成 |
| **ACP 协议** | Agent 发现 | 已实现 | 局域网自动发现 |
| | 点对点通信 | 已实现 | 直接消息传递 |
| | 群组通信 | 已实现 | 多 Agent 协同 |
| | 记忆共享 | 已实现 | 跨 Agent 记忆访问 |
| **工具系统** | 内置工具 | 已实现 | calculator, datetime, random, json_format |
| | 主模型工具 | 已实现 | 记忆写入/搜索、ACP、提醒、Mono等13个 |
| | 记忆管理工具 | 已实现 | 16个助手工具 |
| | 摘要工具 | 已实现 | summarize_content, save_summary_memory |
| | MCP 集成 | 已实现 | Model Context Protocol |
| | 图工具 | 已实现 | 图数据库操作工具（条件注册） |
| **LLM 集成** | Ollama | 已实现 | 本地 LLM 支持 |
| | OpenAI | 已实现 | OpenAI 兼容 API |
| | Anthropic | 已实现 | Claude 兼容 |
| | DeepSeek | 已实现 | DeepSeek API |
| | vLLM | 已实现 | vLLM 推理服务（当前默认主模型提供商） |
| | 向量生成 | 已实现 | 文本嵌入（当前默认 vLLM Qwen3-Embedding-0.6B） |
| **图数据库** | 知识图谱 | 已实现 | 节点/边 CRUD、可视化 |
| | 语义搜索 | 已实现 | 图节点语义搜索 |
| | 路径分析 | 已实现 | 最短路径、PageRank、社区检测 |
| **CXFC 插件协议** | 插件发现 | 已实现 | 自动发现 CXFC 兼容插件 |
| | 技能注册 | 已实现 | 插件技能注册与调用 |
| **提醒系统** | 定时提醒 | 已实现 | 闹钟、定时回调 |
| **备份恢复** | 数据备份 | 已实现 | 系统数据快照 |
| | 数据恢复 | 已实现 | 从备份恢复 |
| **WebSocket** | 实时通信 | 已实现 | 推送提醒、状态更新 |
| | 离线保存 | 已实现 | Agent 离线时保存上下文 |
| **配置系统** | 三层配置 | 已实现 | YAML + 环境变量 + 自动修复 |
| | 配置验证 | 已实现 | ConfigValidation |
| | LLM 提供商 | 已实现 | OLLAMA/VLLM/OPENAI/ANTHROPIC/DEEPSEEK/LOCAL |
| **国际化** | 多语言支持 | 已实现 | 简体中文、英文 |
| **前端界面** | 聊天界面 | 已实现 | React 实现，双通信模式(WebSocket+SSE降级) |
| | 记忆管理 | 已实现 | CRUD 界面，图数据库管理(GraphManager) |
| | 归档管理 | 已实现 | 可视化界面 |
| | Agent 配置 | 已实现 | 配置编辑器 |
| | 工具管理 | 已实现 | 工具列表、测试 |
| | 记忆代理 | 已实现 | 记忆管理对话引擎 |
| | 连接检测 | 已实现 | ConnectionCheck 动态配置后端地址 |
| | 多模态支持 | 已实现 | 图片上传（Agent启用vision_enabled时） |
| | 提醒通知 | 已实现 | WebSocket alarm 消息实时推送 |
| | 离线超时 | 已实现 | 自动保存上下文到长期记忆 |

## 技术亮点

1. **多层次记忆系统** — 短期/长期/永久记忆分类；重要性动态评分；场景感知路由。
2. **智能衰减机制** — 双阶段指数衰减（默认）+ 艾宾浩斯遗忘曲线（实验性），参数可配置，自动重新激活。
3. **灵活的 ACP 协议** — 局域网自动发现、群组协同、跨 Agent 记忆共享。
4. **强大的工具生态** — MCP 协议支持；内置工具库；主模型工具 (13个) + 记忆管理工具 (16个) + 摘要工具；动态工具注册。
5. **知识图谱引擎** — 图遍历算法 (BFS/DFS)、语义搜索与混合查询、PageRank 与社区检测。
6. **CXFC 插件协议** — 插件自动发现、技能注册与调用、心跳健康检测。
7. **实时通信** — WebSocket 双向通信、离线消息自动保存、提醒系统实时推送。
8. **国际化支持** — i18next 多语言框架，简体中文/英文双语。
9. **三层配置体系** — YAML 配置文件 + 环境变量覆盖（CXHMS_ 前缀）+ 自动修复（ConfigRepair）+ 配置验证（ConfigValidation）。
10. **完善的前端体验** — React 18 + TypeScript；Zustand 状态管理 (chatStore + themeStore)；双客户端架构 (主后端 8001 + 控制服务 8765)；内置缓存 + 重试 + SSE 流式；响应式设计。

## 项目结构优势

- **模块化设计**: 各功能模块独立，便于扩展。
- **清晰的分层**: API → Core → Storage。
- **完善的测试**: 后端 18 文件 + 前端 6 文件 + LLM E2E 8 文件。
- **类型安全**: TypeScript + Pydantic 双重保障。
- **配置灵活**: 三层配置体系（YAML + 环境变量 + 自动修复）。

## 相关文档

- [架构文档 ARCHITECTURE.md](./ARCHITECTURE.md) — 架构设计、初始化流程、依赖注入、业务流程图、配置系统
- [模块详解 MODULES.md](./MODULES.md) — API 路由、核心组件、前端实现、测试体系
- [部署指南 DEPLOYMENT.md](./DEPLOYMENT.md) — 环境要求、安装、Docker、生产配置
- [API 文档 API.md](./API.md) — RESTful API 端点说明
- [技术文档 TECHNICAL.md](./TECHNICAL.md) — 核心模块技术细节
- [项目报告索引 PROJECT_REPORT.md](../PROJECT_REPORT.md) — 历史 报告索引
