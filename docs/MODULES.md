# CXHMS 模块详解

> **文档版本**: v3.0.0 | **最后更新**: 2026-07-17
>
> 本文为 CXHMS 后端模块、API 路由、前端实现、RADIX-Lite 子系统与测试体系的精简目录。完整实现细节请参考对应源码文件与 `public/interface_stub/` 下的接口契约存根。项目总览见 [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)，架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)，契约变更见 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md)。

---

## 一、模块总览

CXHMS 采用 AC 范式 v6 的模块化架构，业务模块区位于 `modules/`，共 11 个模块。模块 0-6 为既有核心系统，模块 7-10 为 RADIX-Lite v1.2.0（2026-07-16 闭合）新增的管理 Agent 扩展子系统。

| 模块编号 | 模块名称 | 模块职责 | RADIX-Lite |
|---------|---------|---------|:----------:|
| 模块0 | 全局调度面板 | 全局调度与进度监控（无业务逻辑） | — |
| 模块1 | 记忆服务 | 记忆存储、搜索、决策化写入 | 部分 |
| 模块2 | 对话服务 | 对话与上下文管理 | — |
| 模块3 | 工具与ACP | 工具系统与 ACP 协议 | — |
| 模块4 | 图数据库 | 知识图谱与语义搜索 | — |
| 模块5 | 前端展示 | React 前端 | — |
| 模块6 | 辅助服务 | 提醒 / 备份 / 插件 / WebSocket / 会话 | — |
| 模块7 | 模板引擎 | Jinja2 DSL 模板渲染 + frontmatter + CRUD | ✅ v1.2.0 新增 |
| 模块8 | 多模态管线 | 3 worker 多模态预处理 + 模态融合 + 降级 | ✅ v1.2.0 新增 |
| 模块9 | 蒸馏服务 | 7 状态机多轮蒸馏 + 4 API 端点 | ✅ v1.2.0 新增 |
| 模块10 | 管理Agent扩展 | 6 决策点自主决策 + 8 工具方法 + rubric 驱动 | ✅ v1.2.0 新增 |

### 三层契约总览（v1.2.0）

| 契约层 | 位置 | 数量 |
|--------|------|------|
| 数据契约（JSON Schema draft-07+） | `public/schema/` | 13 份 |
| 接口契约（.pyi 存根） | `public/interface_stub/` | 13 份 |
| 配置契约（JSON Schema） | `public/config_template/` | 5 份（含 `radix_config.json`） |
| 预生成 Mock | `public/pre_generated_mock/` | 12 份 |

> 详见 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md)。

---

## 二、API 路由系统

FastAPI 应用包含 17 个路由模块，挂载于 `backend/api/routers/`。所有 API 返回 JSON，包含 `status` 字段表示请求状态。RADIX-Lite 蒸馏服务为独立子服务，挂载于端口 8011（见 §模块9）。

### 路由文件总览

| 文件 | 路径前缀 | 主要功能 | 核心端点 |
|------|---------|---------|---------|
| chat.py | `/api/chat` | 聊天对话、流式响应 | POST /api/chat, POST /api/chat/stream, GET /api/chat/history/{session_id}, POST /api/memory-agent/chat/stream |
| memory.py | `/api/memories` | 记忆 CRUD、搜索、RAG、决策化写入 | 30+ 端点（含 batch、secondary、semantic-search、3d、write-with-decision、rejected-content） |
| context.py | `/api/context` | 会话管理、消息历史 | 10 端点（sessions, messages, summary, stats） |
| tools.py | `/api/tools` | 工具注册与调用、MCP 服务器管理 | — |
| acp.py | `/api/acp` | ACP 协议通信 | — |
| agents.py | `/api/agents` | Agent 配置与上下文管理（含 tools_config / decision_rubric / distillation_enabled 字段） | CRUD、clone、stats、context |
| archive.py | `/api/archive` | 归档管理 | — |
| config.py | `/api/config` | 配置管理 | — |
| cxfc.py | `/api/cxfc` | CXFC 插件协议 | — |
| graph.py | `/api/graph` | 图数据库操作 | 节点/边 CRUD、语义搜索 |
| stats.py | `/api/stats` | 统计数据 | — |
| vector.py | `/api/vector` | 向量搜索操作 | — |
| service.py | `/api/service` | 服务管理 | — |
| backup.py | `/api/backup` | 备份恢复 | — |
| websocket.py | `/ws` | WebSocket 连接 | 实时通信、提醒推送 |
| admin.py | `/api/admin` | 管理员功能 | — |
| anythingllm.py | `/api/anythingllm` | AnythingLLM 兼容层（v1.1.0） | workspace / chat_completion |

### 聊天流程

1. 用户发送消息 → 获取 Agent 配置（系统提示词、模型、温度、`tools_config`、`decision_rubric`、`distillation_enabled`）
2. 管理 Agent 专属会话（每个 Agent 一个固定会话，`session_id = agent-{agent_id}`）
3. 检索相关记忆（如启用）
4. 构建消息列表（系统提示词 + 记忆上下文 + 历史消息 + 当前消息）
5. 获取工具列表（按 Agent `tools_config` 过滤，RADIX-Lite 启用后含 8 个新增工具）
6. 调用 LLM 生成响应（支持流式 SSE）
7. 处理工具调用（如有，最多 `max_tool_rounds=10` 轮）
8. 保存助手响应到上下文

> 完整聊天路由实现见 [backend/api/routers/chat.py](../backend/api/routers/chat.py)；记忆路由实现见 [memory.py](../backend/api/routers/memory.py)。

---

## 三、模块0_全局调度面板

### 定位

项目级调度与进度监控入口，**无业务逻辑**。负责 11 个模块之间的协同调度、进度汇总与状态可视化。

### 核心文件

- `modules/模块0_全局调度面板/AGENTS.md` — 模块规则入口

### 接口契约

无独立接口契约。该模块仅消费其他模块的进度元信息，不对外提供 API。

### 依赖关系

- 依赖全部 11 个模块的状态元信息（只读）
- 不被任何业务模块依赖

### 测试统计

无独立测试（仅元信息聚合）。

---

## 四、模块1_记忆服务

### 定位

CXHMS 核心模块，提供长期记忆存储、多策略搜索、衰减管理、决策化写入能力。RADIX-Lite v1.2.0 在原 `MemoryManager` 基础上扩展了 `write_with_decision` 决策化写入接口。

### 核心文件

- `backend/core/memory/manager.py` — `MemoryManager` 单例实现（含 v1.2.0 新增 3 方法）
- `backend/core/memory/hybrid_search.py` — `HybridSearch` RRF 融合搜索
- `backend/core/memory/vector_backends/` — 5 向量后端实现（Chroma / Milvus Lite / Qdrant / Weaviate / Weaviate Embedded）
- `backend/api/routers/memory.py` — 30+ 端点路由
- `modules/模块1_记忆服务/AGENTS.md` — 模块规则

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约（既有） | `public/interface_stub/memory_service.pyi` | write_memory / get_memory / search_memories / hybrid_search / search_memories_3d / batch_* |
| 接口契约（v1.2.0 新增） | `public/interface_stub/memory_manager_v2.pyi` | write_with_decision / get_rejected_content / cleanup_expired_rejected_content |
| 数据契约 | `public/schema/memory.json` | 记忆数据结构 |
| 数据契约 | `public/schema/storage_decision.schema.json` | 存储决策结果（3 location 枚举 + rubric_snapshot + quality_score） |
| Mock | `public/pre_generated_mock/memory_mock.py` + `mock_memory_manager_v2.py` | 默认 Mock 实现 |

### write_with_decision 决策化写入（v1.2.0 新增）

`backend/core/memory/manager.py` 新增 3 方法，由 `DecisionCore`（模块10）驱动：

| 方法 | 说明 |
|------|------|
| `write_with_decision(content, decision, metadata)` | 根据 `decision.location` 写入：`memories`（临时）/ `permanent_memories`（永久）/ `rejected`（拒绝，写入 `rejected_content` 表保留 30 天） |
| `get_rejected_content(session_id, limit)` | 获取被拒绝内容列表，用于 GN-004 抽样审查和人类 override_decision |
| `cleanup_expired_rejected_content(retention_days=30)` | 清理过期拒绝内容，默认保留 30 天 |

**`rejected_content` 表**：保留被拒绝内容 30 天，支持人类 override 与审计回溯。对应 API 端点：

- `POST /api/memories/write-with-decision`
- `GET /api/memories/rejected-content`
- `DELETE /api/memories/rejected-content/cleanup-expired`

### 数据库表

- `memories` — 全部记忆数据：id、type、content、importance、importance_score、decay_type、reactivation_count、emotion_score、permanent、tags、metadata、workspace_id、agent_id
- `permanent_memories` — 永久记忆
- `rejected_content` — **v1.2.0 新增**：被 DecisionCore 拒绝的内容，保留 30 天
- `audit_logs` — 操作日志
- `agent_memory_tables` — Agent 与记忆表映射

### 记忆衰减系统

- **双阶段指数衰减（默认）**：`T(t) = α·e^(-λ₁·Δt) + (1-α)·e^(-λ₂·Δt)`，α=0.6、λ₁=0.25、λ₂=0.04
- **艾宾浩斯遗忘曲线（实验性）**：`T(t) = 1 / (1 + (Δt/T₅₀)^k)`，通过 `memory.decay_model: "ebbinghaus"` 启用

### 三维评分系统

`search_memories_3d()` 综合考虑：重要性分数 × 0.35 + 时间分数 × 0.25 + 相关度分数 × 0.4（权重可配置，支持场景感知：chat/task/creative）。

### 去重检测

写入时自动检测相似度，阈值 `dedup_threshold`（默认 0.85，见 `config/default.yaml`）。

### 依赖关系

- 被模块2（对话服务）、模块3（工具系统）、模块9（蒸馏服务，通过 `write_with_decision`）、模块10（管理Agent扩展，通过 `decide_storage`）调用
- 依赖模块4（图数据库，可选）做语义搜索增强
- vLLM Embedding 服务（端口 8101）

### 测试统计

后端单元测试覆盖 `write_memory` / `search_memories` / `hybrid_search` / `search_memories_3d` / `batch_*` / `write_with_decision`（详见 §十四）。

---

## 五、模块2_对话服务

### 定位

`ContextManager` + Agent 配置 + 流式响应，SQLite 存储，支持 Mono 上下文（持久化临时信息，支持过期时间与轮次限制）。

### 核心文件

- `backend/core/context/` — `ContextManager` 实现
- `backend/api/routers/context.py` — 会话与消息路由
- `backend/api/routers/agents.py` — Agent CRUD / clone / stats / context
- `backend/api/routers/chat.py` — 流式聊天路由
- `modules/模块2_对话服务/AGENTS.md` — 模块规则

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约 | `public/interface_stub/chat_service.pyi` | chat / stream_chat / get_history |
| 接口契约 | `public/interface_stub/agent_service.pyi` | Agent CRUD + clone + context |
| 数据契约 | `public/schema/agent.json` | Agent 配置（含 v1.2.0 扩展字段） |
| 数据契约 | `public/schema/message.json` | 消息结构 |
| 数据契约 | `public/schema/agent_config_v2.schema.json` | **v1.2.0 新增**：tools_config 8 工具 + decision_rubric 4 阈值 + distillation_enabled |
| Mock | `public/pre_generated_mock/chat_mock.py` + `agent_mock.py` | 默认 Mock 实现 |

### 会话与消息

- **会话**：id、workspace_id、title、message_count、summary、is_active
- **消息**：id、session_id、role（system/user/assistant/mono_context）、content、content_type、tokens
- **Mono 上下文**：跨多轮对话保持关键信息，支持 `expires_at` 与 `rounds_remaining` 两种过期方式

### Agent 配置管理

**默认 Agent**：
- `default` — 默认助手，main 模型，128k 上下文，支持记忆和工具
- `memory-agent` — 记忆管理助手，memory 模型，128k 上下文，16 个记忆管理工具

`AgentContextManager` 管理 Agent 持久化上下文，支持跨会话保存消息历史。每个 Agent 对应固定会话（`session_id = agent-{agent_id}`）。

### 流式响应

使用 SSE (Server-Sent Events)，事件类型：`session`、`thinking`、`content`、`tool_call`、`tool_start`、`tool_result`、`done`、`cancelled`、`error`。

### 依赖关系

- 依赖模块1（记忆服务）做 RAG 检索
- 依赖模块3（工具系统）执行工具调用
- 依赖模块7（模板引擎，v1.2.0）渲染 prompt（可选）
- vLLM 主模型服务（端口 8002）

---

## 六、模块3_工具与ACP

### 定位

`ToolRegistry` 工具注册/发现/调用 + ACP 局域网多 Agent 通信 + MCP 协议支持。

### 核心文件

- `backend/core/tools/` — `ToolRegistry`、`MCPManager`
- `backend/core/acp/` — `ACPManager`、`ACPLanDiscovery`
- `backend/api/routers/tools.py` — 工具路由
- `backend/api/routers/acp.py` — ACP 路由
- `modules/模块3_工具与ACP/AGENTS.md` — 模块规则

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约 | `public/interface_stub/tool_service.pyi` | 工具注册/调用/列表 |
| 接口契约 | `public/interface_stub/agent_tools_v2.pyi` | **v1.2.0 新增**：8 工具方法（agent CRUD + 蒸馏 + 模板 + 决策） |
| 数据契约 | `public/schema/tool.json` | 工具定义 |
| Mock | `public/pre_generated_mock/tool_mock.py` + `mock_agent_tools_v2.py` | 默认 Mock 实现 |

### 工具分类

| 分类 | 说明 | 数量 |
|------|------|------|
| builtin | 内置工具：calculator, datetime, random, json_format | 4 |
| master | 主模型专属工具：write_long_term_memory, search_all_memories, call_assistant, set_alarm, mono, write_permanent_memory, ACP 相关等 | 13 |
| summary | 摘要工具：summarize_content, save_summary_memory | 2 |
| assistant | 记忆管理工具 | 16 |
| graph | 图数据库工具（条件注册） | — |
| mcp | MCP 协议工具（动态注册） | — |
| radix_v2 | **v1.2.0 新增**：管理 Agent 扩展工具（add_agent / update_agent / delete_agent / start_distillation / advance_distillation / finalize_distillation / render_template / decide_storage） | 8 |

### ACP 协议

- **局域网发现**：`ACPLanDiscovery` 实现 UDP 广播发现，端口 9999（发现请求）/ 9998（广播响应）。当前配置 `discovery_port: 9999`、`broadcast_port: 9998`、`discovery_interval: 10s`
- **消息传递**：`ACPManager` 负责收发，支持 CHAT、MEMORY_REQUEST/RESPONSE、TOOL_CALL/RESULT、BROADCAST、GROUP_MESSAGE
- **群组管理**：创建/加入/离开群组、群组消息广播

### 依赖关系

- 依赖模块1（记忆服务）执行记忆工具
- 依赖模块7（模板引擎，v1.2.0）执行 `render_template` 工具
- 依赖模块9（蒸馏服务，v1.2.0）执行蒸馏工具（HTTP 调用端口 8011）
- 依赖模块10（管理Agent扩展，v1.2.0）执行 `decide_storage` 工具

---

## 七、模块4_图数据库

### 定位

知识图谱系统，条件启用模块（`graph.enabled: true`）。支持节点/边 CRUD、语义搜索、路径分析、社区检测、PageRank、GraphML/DOT 导出、Neo4j 迁移。

### 核心文件

- `backend/core/graph/database.py` — 初始化连接
- `backend/core/graph/repository.py` — 增删改查
- `backend/core/graph/nodes.py` / `edges.py` — 节点/边管理
- `backend/core/graph/semantic_search.py` — 向量相似度图搜索
- `backend/core/graph/traversal.py` — BFS/DFS 遍历
- `backend/core/graph/hybrid_query.py` — 混合查询
- `backend/core/graph/vectorizer.py` — 向量化
- `backend/core/graph/visualization.py` — 可视化
- `backend/core/graph/monitoring.py` — 监控
- `backend/api/routers/graph.py` — 图路由
- `modules/模块4_图数据库/AGENTS.md` — 模块规则

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约 | `public/interface_stub/graph_service.pyi` | 节点/边 CRUD + shortest_path + semantic_search |
| 数据契约 | `public/schema/graph_node.json` | 图节点结构 |
| 数据契约 | `public/schema/graph_edge.json` | 图边结构 |
| Mock | `public/pre_generated_mock/graph_mock.py` | 默认 Mock 实现 |

### 依赖关系

- 依赖模块1（记忆服务）做语义增强
- 依赖 vLLM Embedding 服务（端口 8101）
- Weaviate 向量库（端口 8090，gRPC 50061）

---

## 八、模块5_前端展示

### 定位

React 18 + TypeScript 单页应用，9 个页面 + 双客户端架构 + 双通信模式（WebSocket 优先 + SSE fallback）。

### 核心文件

- `frontend/src/pages/` — 9 个页面组件
- `frontend/src/components/` — UI 库（11 个）+ 布局（4 个）+ 功能组件
- `frontend/src/store/` — Zustand 状态管理（chatStore + themeStore）
- `frontend/src/hooks/` — useWebSocket + useHotkey
- `frontend/src/api/` — 双 API 客户端
- `frontend/src/i18n/` — 国际化（zh-CN + en-US）
- `modules/模块5_前端展示/AGENTS.md` — 模块规则

### 主要页面（9 个）

- `DashboardPage` 仪表盘
- `ChatPage` 聊天页（Agent 选择、流式响应、工具调用展示、双通信模式、图片上传、思考过程展示、提醒通知）
- `MemoriesPage` 记忆管理
- `ArchivePage` 归档管理
- `AgentsPage` Agent 配置
- `AcpPage` ACP 控制
- `ToolsPage` 工具管理
- `SettingsPage` 设置（离线超时配置）
- `MemoryAgentPage` 记忆管理 Agent 专用页

### 核心特性

- **ConnectionCheck 组件**：检测后端可用性，不可用时显示配置界面，10 秒自动重试，支持动态配置后端地址
- **双通信模式**：ChatPage 同时支持 WebSocket（实时）与 SSE 流式（降级），优先 WebSocket
- **提醒功能**：WebSocket 支持 alarm 类型消息，实时推送通知
- **多模态支持**：Agent 启用 `vision_enabled` 时最多上传 4 张图片（base64）
- **思考过程展示**：ChatPage 与 MemoryAgentPage 展示 AI 思考过程和工具调用详情
- **离线超时机制**：断开超过配置时间后自动保存上下文到长期记忆

### 状态管理

Zustand，主要 store：
- `chatStore` — agents, currentAgentId, sessions, currentSessionId, isChatExpanded；仅 currentAgentId/currentSessionId/isChatExpanded 持久化到 localStorage
- `themeStore` — light/dark/system 三种模式，localStorage 持久化

### API 客户端（双客户端架构）

- **主后端客户端**（端口 8001）：记忆 CRUD、聊天发送（流式）、会话管理、ACP、工具管理；内置缓存和重试，支持 SSE
- **控制服务客户端**（端口 8765）：图数据库、向量数据库、CXFC、配置 API

均使用 Axios，支持请求/响应拦截器。

### 国际化

i18next + react-i18next + i18next-browser-languagedetector，默认 zh-CN，支持 en-US，资源按模块组织，动态切换。

### 依赖关系

- 依赖全部后端 API（端口 8001 + 8765 + 8011）
- 不被任何后端模块依赖

### 测试统计

- 前端单元测试：19 文件 / 299 项（Vitest + React Testing Library）
- Playwright E2E：2 文件

---

## 九、模块6_辅助服务

### 定位

辅助功能集合：提醒 / 备份 / CXFC 插件 / WebSocket / 会话管理。

### 核心文件

| 子系统 | 路径 | 说明 |
|--------|------|------|
| 提醒管理 | `backend/core/alarm/` | 定时提醒、闹钟管理、触发回调 |
| 备份管理 | `backend/core/backup/` | 选择性备份（记忆/会话/Agent 配置等）、结构化存储、完整/部分恢复 |
| CXFC 插件 | `backend/core/cxfc/`（6 个文件） | 插件发现、技能注册、心跳管理、连接管理、事件推送（`cxfc.enabled: true`） |
| WebSocket | `backend/core/websocket/` | 连接管理、实时通信、离线消息保存、与提醒管理器集成 |
| 会话管理 | `backend/core/session/` | 会话存储、清理策略（时间/数量阈值） |
| 插件管理 | `backend/core/plugins/` | 插件加载、生命周期管理、运行时上下文注入、动态加载/卸载 |

### CXFC 核心文件

- `manager.py`（核心调度）、`discovery.py`（自动发现）、`skill_registry.py`（技能注册）、`storage.py`（持久化）、`models.py`（数据模型）

### 异常处理体系

系统定义完整的自定义异常层次，位于 `backend/core/exceptions/`。统一定义全局错误码，避免模块间异常拦截歧义。所有接口契约包含异常说明，调用方必须处理约定异常。

### 依赖关系

- CXFC 依赖模块3（工具系统）做技能注册
- WebSocket 依赖模块2（对话服务）做会话推送
- 备份依赖模块1（记忆服务）+ 模块2（对话服务）做数据导出

### 测试统计

后端单元测试覆盖（详见 §十四）。

---

## 十、模块7_模板引擎（RADIX-Lite v1.2.0 新增）

### 定位

RADIX-Lite 子系统之一，**YAML frontmatter + Jinja2 原生渲染**的进程内模板引擎；提供模板渲染 + 模板 CRUD + 工作流定义解析能力。是模块9（蒸馏服务）和模块10（管理Agent扩展）的依赖项。

### 核心文件

- `modules/模块7_模板引擎/__init__.py` — 模块初始化，导出公开 API
- `modules/模块7_模板引擎/template_engine.py` — `TemplateEngine` 真实实现（911 行）
- `data/templates/presets/*.j2` — 预设模板（只读，由 auto_init 创建 `default.j2` + `distillation.j2`）
- `data/templates/custom/*.j2` — 自定义模板（可 CRUD）
- `modules/模块7_模板引擎/AGENTS.md` — 模块规则

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约 | `public/interface_stub/template_engine.pyi` | 7 方法（render_template + list/get/create/update/delete + _parse_frontmatter） |
| 数据契约 | `public/schema/template_registry.schema.json` | frontmatter + body + CRUD 元数据 |
| 配置契约 | `public/config_template/radix_config.json` 的 `template_engine` 段 | templates_dir / presets_dir / custom_dir / autoescape / trim_blocks / lstrip_blocks |
| Mock | `public/pre_generated_mock/mock_template_engine.py` | `MockTemplateEngine` |

### 7 方法签名

| 方法 | 说明 |
|------|------|
| `render_template(template_id, variables, workflow_mode=None)` | 渲染 Jinja2 模板，返回 `RenderResult`（rendered_prompt + workflow_definition + expected_turns） |
| `list_templates(category=None)` | 列出模板（按 `template_id` 升序） |
| `get_template(template_id)` | 获取单个模板 |
| `create_template(request)` | 创建自定义模板（仅 custom，preset 由系统预置） |
| `update_template(template_id, request)` | 更新自定义模板（preset 不可更新） |
| `delete_template(template_id)` | 删除自定义模板（preset 不可删除） |
| `_parse_frontmatter(content)` | 内部方法：解析 YAML frontmatter，返回 (frontmatter_dict, body_string) |

### Jinja2 Environment 配置

- `Loader`: `ChoiceLoader([FileSystemLoader(presets_dir), FileSystemLoader(custom_dir)])`
- `autoescape`: `False`（模板是 prompt，不是 HTML）
- `trim_blocks`: `True`、`lstrip_blocks`: `True`
- 自定义 filter: `confidence_label`（0-1 → "低"/"中"/"高"）
- 支持：extends / block / if / elif / else / for / include / filter

### 错误码与异常契约

| 异常类型 | HTTP 码 | 触发条件 |
|---------|--------|---------|
| KeyError | 404 | template_id 不存在 |
| ValueError | 422 | frontmatter 无效 / 缺 required_vars / workflow_mode 无效 |
| PermissionError | 403 | 尝试更新/删除 preset 模板 |
| FileExistsError | 409 | template_id 已存在 |
| jinja2.TemplateSyntaxError | 422 | Jinja2 语法错误 |
| jinja2.TemplateNotFound | 422 | extends 引用的父模板不存在 |

### 依赖关系

- 不依赖其他 RADIX-Lite 模块（独立子系统）
- 被模块9（蒸馏服务）进程内调用渲染 prompt
- 被模块10（管理Agent扩展）的 `render_template` 工具进程内调用

### 测试统计

- Spike 回归：`tests/spike_jinja2.py` 5/5 PASS
- 模块实例化测试：`tests/units/test_template_engine_smoke.py` 24 PASS
- 契约测试：`tests/contract/radix_contract_test.py` 105 PASS（无回归）

---

## 十一、模块8_多模态管线（RADIX-Lite v1.2.0 新增）

### 定位

RADIX-Lite 多模态预处理管线，3 模态（text / character_card / image）统一入口，产出 `MultimodalArtifact`。接管 `parser.py` 下沉的解析能力（Task 6 改造 `parser.py` 为 thin wrapper，调用本管线）。

### 核心文件

- `modules/模块8_多模态管线/__init__.py` — 模块初始化，导出 `MultimodalPipeline` / `MultimodalArtifact` / `OCRBlock` / `CharacterCardFields`
- `modules/模块8_多模态管线/multimodal_pipeline.py` — `MultimodalPipeline` 主类（数据模型 + worker 池调度 + 配置加载）
- `modules/模块8_多模态管线/workers/text_worker.py` — 文本模态 worker（编码检测 + NFKC + strip）
- `modules/模块8_多模态管线/workers/character_card_worker.py` — 角色卡模态 worker（PNG tEXt → base64 → JSON → 字段标准化）
- `modules/模块8_多模态管线/workers/image_worker.py` — 图片模态 worker（PaddleOCR + vLLM vision 双通道 + 降级 + merge）
- `modules/模块8_多模态管线/AGENTS.md` — 模块规则

> 主类 + 3 workers 合计 1242 行。

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约 | `public/interface_stub/multimodal_pipeline.pyi` | 7 方法（preprocess + 3 worker + _ocr_worker + _vision_worker + _merge_ocr_vision） |
| 数据契约 | `public/schema/multimodal_artifact.schema.json` | 3 模态 type 枚举 + confidence + vision_degraded |
| 配置契约 | `public/config_template/radix_config.json` 的 `multimodal_pipeline` + `vllm` 段 | worker_pool_size / task_timeout_seconds / enabled_modalities / ocr_language / vision_base_url / vision_model |
| Mock | `public/pre_generated_mock/mock_multimodal_pipeline.py` | `MockMultimodalPipeline` |

### 3 模态 worker

| 模态 | worker | 处理流程 |
|------|--------|---------|
| text | `_text_worker` | chardet 编码检测 + NFKC 归一化 + strip |
| character_card | `_character_card_worker` | Pillow PNG tEXt "chara" chunk → base64 decode → JSON → 字段标准化 |
| image | `_image_worker` | PaddleOCR 通道（`_ocr_worker`）+ vLLM vision 通道（`_vision_worker`）双通道，`_merge_ocr_vision` 合并 |

### 降级路径

- **PaddleOCR 不可用**：`_ocr_worker` raise RuntimeError（500 OCR_FAILED），**不降级**（OCR 是图片模态必需通道）
- **vLLM vision 不可用**：`_vision_worker` raise ConnectionError（503），`_image_worker` 捕获后降级（`vision_degraded=True`，仅返回 OCR）
- **chardet 不可用**：`TextWorker` 降级为 utf-8/gbk 依次尝试，全部失败 raise ValueError（422）

### 依赖关系

- 不依赖其他 RADIX-Lite 模块（独立子系统，便于 Task 6 下沉时单向引用）
- 不依赖 `backend/` 现有实现
- 被模块9（蒸馏服务）进程内调用做预处理
- 被 `backend/core/document/parser.py`（Task 6 改造后）作为 thin wrapper 调用

### 测试统计

- 模块实例化测试：`tests/contract/test_multimodal_pipeline_unit.py` 28 PASS
- 契约测试：`tests/contract/radix_contract_test.py` 105 PASS（无回归）

---

## 十二、模块9_蒸馏服务（RADIX-Lite v1.2.0 新增）

### 定位

RADIX-Lite 子系统之一，**独立 FastAPI 子服务（端口 8011）**，承载 7 状态机多轮蒸馏工作流。与主后端（8001）通过 HTTP REST API 通信；编排 `MultimodalPipeline`（预处理）+ `TemplateEngine`（模板渲染）+ `DecisionCore`（决策）三大子系统。

### 核心文件

- `modules/模块9_蒸馏服务/__init__.py` — 模块初始化，导出 `DistillationService` + Pydantic 模型
- `modules/模块9_蒸馏服务/distillation_service.py` — `DistillationService` 主类实现（720 行，状态机 + 子系统协同 + 持久化）
- `modules/模块9_蒸馏服务/api/__init__.py` — API 子包初始化，导出 `create_app` / `router`
- `modules/模块9_蒸馏服务/api/app.py` — FastAPI app 构造入口（`create_app` + `main` + `/health`）
- `modules/模块9_蒸馏服务/api/routes.py` — 4 个 REST API 端点路由定义
- `modules/模块9_蒸馏服务/AGENTS.md` — 模块规则

### 持久化目录（auto_init 自动创建）

- `data/distillation_sessions/{session_id}.json` — 会话状态持久化
- `data/distillation_logs/{session_id}.json` — 决策审计日志（符合 `distillation_log.schema.json`）

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约 | `public/interface_stub/distillation_service.pyi` | 4 API 端点 + 1 内部方法（start/advance/finalize/get + _transition_state） |
| 数据契约 | `public/schema/distillation_session.schema.json` | 蒸馏会话状态机契约（7 状态 + turns 数组 + final_decision） |
| 数据契约 | `public/schema/distillation_log.schema.json` | 决策审计日志契约（6 决策点 + llm_reasoning + final_decision） |
| 配置契约 | `public/config_template/radix_config.json` 的 `distillation_service` + `decision_core` + `vllm` 段 | host / port / max_turns / session_timeout_seconds / session_storage_dir / log_storage_dir / main_backend_url |
| Mock | `public/pre_generated_mock/mock_distillation_service.py` | `MockDistillationService` |

### 4 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/radix/distillation/start` | POST | 启动蒸馏会话，异步触发 `MultimodalPipeline` 预处理，session 进入 `collecting` 状态 |
| `/api/radix/distillation/{session_id}/advance` | POST | 推进蒸馏状态机一步（由 `distill_advance` 决策点驱动） |
| `/api/radix/distillation/{session_id}/finalize` | POST | 终结蒸馏会话，调用 `DecisionCore` 执行 6 决策点 |
| `/api/radix/distillation/{session_id}` | GET | 查询会话状态 |

### 7 状态机

蒸馏服务采用 7 状态机驱动多轮蒸馏流程，状态单向推进，终态 `finalized` 不可回退。

```
draft → collecting → distilling → refining → reviewing → finalizing → finalized
```

| 状态 | 中文名 | 触发决策点 | 说明 |
|------|--------|-----------|------|
| draft | 草稿 | distill_start | 蒸馏会话初始状态，等待启动 |
| collecting | 收集 | distill_collect | 收集多模态输入与历史上下文 |
| distilling | 蒸馏 | distill_advance | LLM 多轮蒸馏处理 |
| refining | 精炼 | distill_advance | 精炼输出内容 |
| reviewing | 审查 | distill_advance | 审查蒸馏结果质量 |
| finalizing | 定稿 | distill_finalize | 准备最终产出 |
| finalized | 终态 | — | 蒸馏完成，不可回退 |

- **状态单向推进**：draft → collecting → distilling → refining → reviewing → finalizing → finalized，终态不可回退
- **回环控制**：`distill_advance` 决策点在 distilling/refining/reviewing 阶段决定推进路径，受 `rubric.max_redistill_turns` 限制，总轮次不得超过 `session.max_turns`
- **拒绝路径**：`storage_decision` 决策点判定存储位置为 `rejected` 时，内容落入 `rejected_content` 表（保留 30 天）
- **蒸馏会话契约**：`distillation_session.schema.json`（7 状态 + turns 数组 + final_decision）

### 失败回退

- **MultimodalPipeline 不可用**：`_run_preread` 捕获异常后降级到占位摘要（不阻断 start_distillation）
- **TemplateEngine 不可用**：`_run_preread` 跳过模板渲染（best-effort）
- **DecisionCore 不可用**：`_invoke_decision_core` 捕获异常后降级到 `_fallback_decision` 内置规则决策
- **审计日志写入失败**：best-effort，不阻断主流程

### 依赖关系

- 进程内调用模块7（`TemplateEngine`）
- 进程内调用模块8（`MultimodalPipeline`）
- 进程内调用模块10（`DecisionCore`，真实实现不可用时 fallback Mock）
- HTTP 调用模块1（主后端 8001 的 `write_with_decision` 端点，由 DecisionCore 间接调用）
- 被模块10（管理Agent扩展）的蒸馏工具 HTTP 调用

### 测试统计

- 模块实例化测试：`tests/contract/test_distillation_service_unit.py` 50 PASS
- 契约测试：`tests/contract/radix_contract_test.py` 105 PASS（无回归）

---

## 十三、模块10_管理Agent扩展（RADIX-Lite v1.2.0 新增）

### 定位

RADIX-Lite 管理 Agent 扩展，实现 `DecisionCore`（6 决策点自主决策，rubric 驱动）+ `AgentToolsV2`（8 个新增工具：agent CRUD + 蒸馏 + 模板 + 决策）。决策审计日志持久化到 `data/distillation_logs/{session_id}.json`。

### 核心文件

- `modules/模块10_管理Agent扩展/__init__.py` — 模块初始化，导出 `DecisionCore` / `AgentToolsV2` + 全部模型类
- `modules/模块10_管理Agent扩展/decision_core.py` — `DecisionCore` 真实实现（580 行，6 决策点 + rubric 加载 + 审计日志 + LLM 决策 + system_prompt 回退）
- `modules/模块10_管理Agent扩展/agent_tools.py` — `AgentToolsV2` 真实实现（560 行，8 工具）
- `modules/模块10_管理Agent扩展/AGENTS.md` — 模块规则

### 接口契约

| 契约 | 路径 | 说明 |
|------|------|------|
| 接口契约 | `public/interface_stub/decision_core.pyi` | 9 方法（6 决策点 + _load_rubric + _llm_decide + _write_audit_log） |
| 接口契约 | `public/interface_stub/agent_tools_v2.pyi` | 8 工具方法 |
| 接口契约 | `public/interface_stub/memory_manager_v2.pyi` | `write_with_decision` 关联（由模块1 实现） |
| 数据契约 | `public/schema/storage_decision.schema.json` | 存储决策（3 location 枚举 + rubric_snapshot + quality_score） |
| 数据契约 | `public/schema/agent_config_v2.schema.json` | 管理 Agent 配置（tools_config 8 工具 + decision_rubric 4 阈值 + distillation_enabled） |
| 数据契约 | `public/schema/distillation_log.schema.json` | 决策审计日志（6 决策点 + llm_reasoning + final_decision） |
| 配置契约 | `public/config_template/radix_config.json` 的 `decision_core` + `vllm` 段 | rubric 默认值 + LLM 调用 |
| Mock | `public/pre_generated_mock/mock_decision_core.py` + `mock_agent_tools_v2.py` | 默认 Mock 实现 |

### 6 决策点（DecisionCore）

| 决策点 | 职责 | 输出 |
|--------|------|------|
| distill_start | 判断是否启动蒸馏会话 | 启动 / 暂缓 |
| distill_collect | 决定收集哪些输入 | 输入选择策略 |
| distill_advance | 决定状态机推进路径 | 下一状态 |
| distill_finalize | 决定是否定稿 | 定稿 / 回退 |
| storage_decision | 决定存储位置（3 location 枚举） | memory / archive / rejected |
| content_merge | 决定内容合并策略 | 合并 / 替换 / 跳过 |

每个决策点由 `_llm_decide` 驱动并写入 `_write_audit_log`，统一流程：`_load_rubric → 决策输入 → _llm_decide → 决策输出 → _write_audit_log`。

**决策审计日志契约**：`distillation_log.schema.json`（6 决策点 + llm_reasoning + final_decision）

**决策 rubric**：4 阈值（quality_threshold / dedup_threshold / importance_threshold / merge_threshold），读取 `data/agents.json` 的 `decision_rubric` 字段，**不可被 LLM 自行修改**，仅人类编辑。LLM 置信度极低时回退 `system_prompt` 规则。

### 8 工具方法（AgentToolsV2）

| 分类 | 工具 | 说明 |
|------|------|------|
| Agent CRUD（3） | `add_agent(request)` | 创建新 agent 配置 |
|  | `update_agent(agent_id, request)` | 更新 agent 配置 |
|  | `delete_agent(agent_id)` | 删除 agent（含级联清理） |
| 蒸馏（3） | `start_distillation(request)` | 启动多轮蒸馏会话（HTTP 调用模块9） |
|  | `advance_distillation(request)` | 推进蒸馏状态机 |
|  | `finalize_distillation(request)` | 终结蒸馏会话 |
| 模板（1） | `render_template(request)` | 渲染 Jinja2 模板（进程内调用模块7） |
| 决策（1） | `decide_storage(request)` | `DecisionCore` 智能存储决策 |

工具调用前检查 `tools_config` 启用状态和 `distillation_enabled` 开关。

### 失败回退

- **LLM 不可用**：`_llm_decide` raise ConnectionError（503），`DecisionCore` 捕获后回退 `system_prompt` 规则（`llm_confidence=None` / `llm_reasoning=None`）
- **agents.json 不存在**：`_load_rubric` 回退默认 rubric（auto_init 兜底）
- **审计日志写入失败**：best-effort，不阻断主流程
- **DistillationService 不可用**：蒸馏工具 raise ConnectionError（500）

### async 约束

- 禁止子线程 asyncio + aiohttp
- 蒸馏工具通过 `_run_async()` 在主线程同步桥接 `MockDistillationService` 的 async 方法（`asyncio.run`）
- LLM 调用使用同步 `requests` 库，不用 aiohttp

### 依赖关系

- 进程内调用模块7（`TemplateEngine`，`render_template` 工具）
- HTTP 调用模块9（`DistillationService`，蒸馏工具）
- 通过模块1（`MemoryManagerV2.write_with_decision`）执行实际写入（由 DecisionCore 决策后调用）
- 被模块3（工具系统）注册为 `radix_v2` 工具分类
- LLM 服务（vLLM 端口 8002）

### 测试统计

- 模块实例化测试：`tests/contract/test_decision_core_unit.py` 55 PASS
- 契约测试：`tests/contract/radix_contract_test.py` 105 PASS（无回归）

---

## 十四、测试体系

### 测试统计总览

| 套件 | 数量 | 位置 |
|------|------|------|
| 后端单元测试 | 753 passed | `tests/units/` + `tests/simulation/` |
| RADIX-Lite 单元测试 | 262 passed | `tests/contract/` |
| 接口契约测试 | 437 passed | `tests/contracts/` |
| E2E 测试 | 37 passed | `tests/e2e/` |
| 前端单元测试 | 19 文件 / 299 项 | `frontend/src/` |
| Playwright E2E | 2 文件 | `frontend/e2e/` |
| **合计** | **1489 passed** | — |

### RADIX-Lite 测试套件明细（v1.2.0 新增）

| 测试文件 | 用例数 | 覆盖范围 |
|---------|-------|---------|
| `tests/contract/radix_contract_test.py` | 105 | 6 schema + 6 .pyi + 1 config + 6 Mock 契约校验 |
| `tests/contract/test_distillation_service_unit.py` | 50 | 4 端点 + 7 状态机 + 回环 + 拒绝 + schema 校验 + 异常路径 |
| `tests/contract/test_decision_core_unit.py` | 55 | 6 决策点 + rubric 驱动 + 审计日志 schema + system_prompt 回退 + 8 工具 + 异常路径 |
| `tests/contract/test_multimodal_pipeline_unit.py` | 28 | 3 模态 worker + 降级路径 + schema 校验 |
| `tests/units/test_template_engine_smoke.py` | 24 | render_template + CRUD 闭环 + 异常路径 |
| `tests/e2e/test_radix_task6_integration.py` | 37 | parser.py thin wrapper 集成 + 模块间协同 |

### 后端测试

pytest + pytest-asyncio（`asyncio_mode=auto`），测试位于 `backend/tests`（18 个文件）：
- `test_api` — API 端点测试
- `test_core` — 核心模块单元测试
- `test_integration` — 集成测试

`conftest.py` 提供 fixture：`client`（TestClient）、`async_client`（AsyncClient）、`mock_settings`。

### 前端测试

Vitest + React Testing Library，位于 `frontend/src`（19 个文件），覆盖 API 客户端、chatStore/themeStore、工具函数。

### LLM E2E 测试

LLM 端到端测试框架（8 个文件），验证 LLM 集成完整性与正确性。

### 统一测试运行器

`run_tests.py` 提供统一入口，支持选择性运行前后端测试、生成覆盖率报告。

---

## 十五、向量搜索系统

支持五种向量存储后端，默认 Weaviate（当前 `vector_backend: weaviate`，`hybrid_search_enabled: false`）：

| 后端 | 说明 |
|------|------|
| Chroma | Windows 兼容，0.4.x 版本 |
| Milvus Lite | 无需额外安装 |
| Qdrant | 需 Docker 部署，端口 6333 |
| Weaviate | 默认后端，HTTP 8090 / gRPC 50061，支持嵌入式 |
| Weaviate Embedded | 嵌入式模式 |

`HybridSearch` 类融合向量搜索与 SQLite 关键词搜索，使用 RRF (Reciprocal Rank Fusion) 算法排序。默认度量：余弦相似度 (COSINE)。

---

## 十六、LLM 客户端系统

### 模型路由器

`ModelRouter` 管理多个 LLM 客户端，预配置三种用途：main（主对话，128k 上下文）、summary（摘要）、memory（记忆处理）。当前 `model_defaults`：summary 与 memory 均回退到 main。

### 客户端实现

所有客户端继承 `LLMClient` 抽象基类，统一 `chat()`、`stream_chat()`、`get_embedding()`、`is_available()` 接口。支持 Ollama、VLLM/OpenAI 兼容、Anthropic Claude、DeepSeek、Local 五种。

> **当前默认配置**（见 `config/default.yaml`）：main = vLLM `gemma4-e4b` @8002；embedding = vLLM `Qwen3-Embedding-0.6B` @8101；summary/memory = Ollama `qwen3-vl:8b`（禁用，回退 main）。

### 多模态支持

支持图片输入（base64 编码），Agent 配置 `vision_enabled` 控制启用。前端最多上传 4 张图片。RADIX-Lite v1.2.0 后，图片预处理下沉至模块8（`MultimodalPipeline`）。

---

## 十七、相关文档

- [项目概述 PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)
- [架构文档 ARCHITECTURE.md](./ARCHITECTURE.md)
- [部署指南 DEPLOYMENT.md](./DEPLOYMENT.md)
- [API 文档 API.md](./API.md)
- [技术文档 TECHNICAL.md](./TECHNICAL.md)
- [测试文档 TESTING.md](../TESTING.md)
- [契约变更日志 CHANGELOG.md](../public/schema/CHANGELOG.md)
- [AI 协同规则 AGENTS.md](../AGENTS.md)

---

*文档版本: v3.0.0*

*最后更新: 2026-07-17*
