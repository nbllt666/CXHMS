# CXHMS 项目总览

> **文档版本**: v3.0.0 | **最后更新**: 2026-07-17

## 项目简介

CXHMS (晨曦人格化记忆系统, CX-O History & Memory Service) 是一个基于 FastAPI 的智能记忆管理平台，提供完整的记忆存储、语义搜索、对话系统、ACP 协议通信、工具调用、图数据库、CXFC 插件协议，以及 RADIX-Lite 管理 Agent 扩展（模板引擎 / 多模态管线 / 蒸馏服务 / 决策核心）功能。系统采用前后端分离架构，后端使用 Python + FastAPI，前端使用 React + TypeScript，定位为面向人格化 Agent 的仿生记忆中间层服务。

## 技术栈

### 后端技术栈

- **语言**: Python 3.10+
- **Web 框架**: FastAPI + Uvicorn
- **数据验证**: Pydantic v2
- **ORM**: SQLAlchemy
- **数据库**: SQLite（WAL 模式 + 连接池）
- **HTTP 客户端**: httpx
- **系统监控**: psutil
- **模板引擎**: Jinja2（RADIX-Lite 模块7）
- **LLM 集成**: vLLM（默认）/ Ollama / OpenAI / Anthropic / DeepSeek / Local 兼容接口
- **向量存储**: Weaviate（默认）/ Chroma / Milvus Lite / Qdrant
- **协议**: ACP (Agent Communication Protocol) / CXFC 插件协议 / MCP (Model Context Protocol)

### 前端技术栈

- **UI 框架**: React 18.3.1
- **类型系统**: TypeScript 5.7.2
- **构建工具**: Vite 6.0.6
- **样式**: Tailwind CSS 3.4.17
- **状态管理**: Zustand 5.0.2
- **数据获取**: React Query 5.62.11
- **国际化**: i18next 25.8.4 + react-i18next 16.5.4
- **动画**: Framer Motion 11.15.0
- **图表**: Recharts 2.15.0
- **图标**: Lucide React 0.469.0
- **HTTP 客户端**: Axios 1.7.9
- **Markdown 渲染**: React Markdown 9.0.1 + remark-gfm 4.0.0
- **日期处理**: date-fns 4.1.0
- **测试框架**: Vitest 2.1.8

### AC 范式 v6 基础设施

- **规则体系**: `.trae/rules/rules-0..6.md`（7 个核心规则文件）
- **技能矩阵**: `.trae/skills/`（s0101-s0602 全生命周期 Skill）
- **GN-004 独立审查**: 交付前 6 维度审查
- **三层契约**: `public/`（13 schema + 13 .pyi + 5 config + 12 mock，v1.2.0）
- **变更追踪**: `.trae/documents/`（rules-6 闸门）

## 核心功能列表

### 1. 智能记忆系统

- **多向量存储后端**: Milvus Lite / Chroma / Qdrant / Weaviate / Weaviate Embedded
- **衰减模型**: 双阶段指数衰减（默认）+ 艾宾浩斯遗忘曲线（实验性）
- **三维评分**: importance × 0.35 + time × 0.25 + relevance × 0.4
- **混合搜索**: 向量相似度 + 关键词匹配，RRF 算法融合
- **情感分析**: emotion_score 字段，影响重激活加分
- **去重检测**: dedup_threshold = 0.85
- **副模型路由**: 10 种副模型指令，secondary_router 管理
- **write_with_decision**（v1.2.0 新增）: 决策化写入 + rejected_content 表（保留 30 天）

### 2. RADIX-Lite 管理 Agent 扩展（v1.2.0 新增）

- **模块7 模板引擎**: Jinja2 DSL 模板渲染 + frontmatter 解析 + CRUD（911 行，24 测试）
- **模块8 多模态管线**: 3 worker（OCR / 视觉 / 文本）+ 模态融合 + 降级开关（1242 行，28 测试）
- **模块9 蒸馏服务**: 7 状态机多轮蒸馏 + 4 API 端点（720 行，50 测试）
- **模块10 管理Agent扩展**: 6 决策点自主决策 + 8 工具方法 + rubric 驱动（1140 行，55 测试）

### 3. 图数据库系统

- 知识图谱管理、节点/边 CRUD
- 语义搜索、路径分析、社区检测、PageRank
- GraphML/DOT 导出、Neo4j 迁移
- 条件启用（`graph.enabled: true`）

### 4. ACP 协议

- 局域网自动发现（UDP 9999/9998）
- 点对点通信、群组协同
- 跨 Agent 记忆共享

### 5. CXFC 插件协议

- 插件发现、技能注册、心跳管理
- 连接管理、事件推送
- 条件启用（`cxfc.enabled: true`）

### 6. 工具系统

- **内置工具**: calculator / datetime / random / json_format
- **主模型工具**: write_long_term_memory / search_all_memories / call_assistant / set_alarm / mono / write_permanent_memory / ACP 工具
- **记忆管理工具**: 16 个（update_memory_node / search_memories / delete_memory / merge_memories 等）
- **MCP 协议**: Model Context Protocol 支持

### 7. 对话系统

- 流式响应（SSE + WebSocket 双通信模式）
- RAG 检索增强
- 多 Agent 支持
- 多模态视觉（图片上传与识别）
- WebSocket 实时通信

### 8. 辅助服务

- **提醒管理**: 定时提醒、闹钟管理
- **备份恢复**: 选择性备份、导入导出
- **插件管理**: 动态加载、生命周期管理
- **WebSocket**: 连接管理、离线消息保存
- **会话管理**: 自动清理策略

## 技术亮点

### 1. AC 范式 v6 工程化

- 文档驱动迭代、MVP + Mock 驱动
- 三层契约（数据 / 接口 / 配置）作为唯一真相源
- GN-004 独立审查、[V] 双重闸门
- 变更追踪闸门（rules-6）

### 2. 智能衰减系统

- 双阶段指数衰减：T(t) = α·e^(-λ₁·Δt) + (1-α)·e^(-λ₂·Δt)
- 艾宾浩斯遗忘曲线：T(t) = 1 / (1 + (Δt/T₅₀)^k)
- 记忆重激活：reactivation_count + 情感加分

### 3. RADIX-Lite 多轮蒸馏

- 7 状态机：draft → collecting → distilling → refining → reviewing → finalizing → finalized
- 6 决策点：distill_start / distill_collect / distill_advance / distill_finalize / storage_decision / content_merge
- rubric 驱动决策，审计日志可追溯

### 4. 模拟化测试

- 零外部依赖（FakeLLMClient + FakeEmbeddingModel + InMemoryVectorStore）
- 确定性 + 语义性（n-gram 词袋使向量检索真实有效）
- 1489 passed（753 后端单测 + 262 RADIX-Lite + 437 契约 + 37 E2E）

## 项目结构优势

### 1. 模块化设计

11 个业务模块按「模块N_中文名」组织：
- 模块0_全局调度面板 ~ 模块6_辅助服务（原有）
- 模块7_模板引擎 ~ 模块10_管理Agent扩展（RADIX-Lite v1.2.0 新增）

### 2. 契约优先

- `public/` 目录为只读契约载体
- 13 schema + 13 .pyi + 5 config + 12 pre_generated_mock
- 契约变更走 s0601 流程

### 3. 双文档体系

- **用户文档**: README.md（用户向入口锚点）
- **代理文档**: AGENTS.md（AI 侧最高优先级规则载体）
- **真相源**: 三层契约定义跨角色公共真相

### 4. 配置驱动

- `config/default.yaml` 为唯一配置真相源
- 环境变量覆盖（CXHMS_ 前缀）
- 自动修复 + 验证

## 当前状态

- **版本**: v3.0.0（2026-07-17）
- **契约版本**: v1.2.0（2026-07-16）
- **测试统计**: 1489 passed
- **RADIX-Lite spec**: `add-management-agent-radix` 已闭合（2026-07-16）
- **模块数**: 11 个
- **AC 范式**: v6 全生命周期闭合

## 相关文档

- [架构文档](./ARCHITECTURE.md)
- [模块详解](./MODULES.md)
- [API 文档](./API.md)
- [部署指南](./DEPLOYMENT.md)
- [技术文档](./TECHNICAL.md)
- [测试文档](../TESTING.md)
- [项目报告索引](../PROJECT_REPORT.md)
- [用户入口](../README.md)
- [AI 协同规则](../AGENTS.md)
- [契约变更日志](../public/schema/CHANGELOG.md)
