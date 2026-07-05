# CXHMS 模块详解

> **文档版本**: v2.3.0 | **最后更新**: 2026-07-02
>
> 本文为 CXHMS 后端模块、API 路由、前端实现与测试体系的精简目录。完整实现细节请参考对应源码文件。项目总览见 [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)，架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 一、API 路由系统

FastAPI 应用包含 17 个路由模块，挂载于 `backend/api/routers/`。所有 API 返回 JSON，包含 `status` 字段表示请求状态。

### 路由文件总览

| 文件 | 路径前缀 | 主要功能 | 核心端点 |
|------|---------|---------|---------|
| chat.py | `/api/chat` | 聊天对话、流式响应 | POST /api/chat, POST /api/chat/stream, GET /api/chat/history/{session_id}, POST /api/memory-agent/chat/stream |
| memory.py | `/api/memories` | 记忆 CRUD、搜索、RAG | 30+ 端点（含 batch、secondary、semantic-search、3d 等） |
| context.py | `/api/context` | 会话管理、消息历史 | 10 端点（sessions, messages, summary, stats） |
| tools.py | `/api/tools` | 工具注册与调用、MCP 服务器管理 | — |
| acp.py | `/api/acp` | ACP 协议通信 | — |
| agents.py | `/api/agents` | Agent 配置与上下文管理 | CRUD、clone、stats、context |
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

### 聊天流程

1. 用户发送消息 → 获取 Agent 配置（系统提示词、模型、温度等）
2. 管理 Agent 专属会话（每个 Agent 一个固定会话，`session_id = agent-{agent_id}`）
3. 检索相关记忆（如启用）
4. 构建消息列表（系统提示词 + 记忆上下文 + 历史消息 + 当前消息）
5. 获取工具列表（按 Agent 配置过滤）
6. 调用 LLM 生成响应（支持流式 SSE）
7. 处理工具调用（如有，最多 `max_tool_rounds=10` 轮）
8. 保存助手响应到上下文

> 完整聊天路由实现见 [backend/api/routers/chat.py](../backend/api/routers/chat.py)；记忆路由实现见 [memory.py](../backend/api/routers/memory.py)。

## 二、记忆管理系统 (Memory Manager)

记忆管理系统是 CXHMS 核心模块，位于 `backend/core/memory/`。`MemoryManager` 采用单例模式 + 线程锁，数据库为 SQLite (WAL 模式 + 连接池)。

### 数据库表

- `memories` — 全部记忆数据：id、type、content、importance、importance_score、decay_type、reactivation_count、emotion_score、permanent、tags、metadata、workspace_id、agent_id
- `permanent_memories` — 永久记忆
- `audit_logs` — 操作日志
- `agent_memory_tables` — Agent 与记忆表映射

### 核心方法

- `write_memory()` — 创建新记忆
- `get_memory()` — 获取单条记忆
- `search_memories()` — 搜索记忆
- `update_memory()` — 更新记忆
- `delete_memory()` — 删除记忆（支持软删除）
- `hybrid_search()` — 混合搜索（向量相似度 + 关键词匹配，RRF 融合）
- `search_memories_3d()` — 三维评分搜索
- `recall_memory()` — 记忆召回（重置时间衰减、增加 reactivation_count、情感加分）

### 记忆衰减系统

- **双阶段指数衰减（默认）**：`T(t) = α·e^(-λ₁·Δt) + (1-α)·e^(-λ₂·Δt)`，α=0.6、λ₁=0.25、λ₂=0.04
- **艾宾浩斯遗忘曲线（实验性）**：`T(t) = 1 / (1 + (Δt/T₅₀)^k)`，通过 `memory.decay_model: "ebbinghaus"` 启用

### 三维评分系统

`search_memories_3d()` 综合考虑：重要性分数 × 0.35 + 时间分数 × 0.25 + 相关度分数 × 0.4（权重可配置，支持场景感知：chat/task/creative）。

### 去重检测

写入时自动检测相似度，阈值 `dedup_threshold`（默认 0.95）。

### 副模型路由

`secondary_router` 支持 10 种副模型指令，管理记忆处理、摘要生成等辅助任务。

## 三、向量搜索系统

支持五种向量存储后端，默认 Weaviate（当前 `vector_backend: weaviate`，`hybrid_search_enabled: false`）：

| 后端 | 说明 |
|------|------|
| Chroma | Windows 兼容，0.4.x 版本 |
| Milvus Lite | 无需额外安装 |
| Qdrant | 需 Docker 部署，端口 6333 |
| Weaviate | 默认后端，HTTP 8090 / gRPC 50051，支持嵌入式 |
| Weaviate Embedded | 嵌入式模式 |

`HybridSearch` 类融合向量搜索与 SQLite 关键词搜索，使用 RRF (Reciprocal Rank Fusion) 算法排序。默认度量：余弦相似度 (COSINE)。

## 四、上下文管理系统 (Context Manager)

`ContextManager` 位于 `backend/core/context/`，SQLite 存储，支持 Mono 上下文（持久化临时信息，支持过期时间与轮次限制）。

- **会话**：id、workspace_id、title、message_count、summary、is_active
- **消息**：id、session_id、role（system/user/assistant/mono_context）、content、content_type、tokens
- **Mono 上下文**：跨多轮对话保持关键信息，支持 `expires_at` 与 `rounds_remaining` 两种过期方式

## 五、聊天对话系统

### Agent 配置管理

位于 `backend/api/routers/agents.py`，提供 CRUD、克隆、统计、上下文管理。

**默认 Agent**：
- `default` — 默认助手，main 模型，128k 上下文，支持记忆和工具
- `memory-agent` — 记忆管理助手，memory 模型，128k 上下文，16 个记忆管理工具

`AgentContextManager` 管理 Agent 持久化上下文，支持跨会话保存消息历史。每个 Agent 对应固定会话（`session_id = agent-{agent_id}`）。

### 流式响应

使用 SSE (Server-Sent Events)，事件类型：`session`、`thinking`、`content`、`tool_call`、`tool_start`、`tool_result`、`done`、`cancelled`、`error`。

## 六、ACP 协议 (Agent Communication Protocol)

ACP 用于多 Agent 通信，位于 `backend/core/acp/`。

- **局域网发现**：`ACPLanDiscovery` 实现 UDP 广播发现，端口 9999（发现请求）/ 9998（广播响应）。当前配置 `discovery_port: 9999`、`broadcast_port: 9998`、`discovery_interval: 30s`
- **消息传递**：`ACPManager` 负责收发，支持 CHAT、MEMORY_REQUEST/RESPONSE、TOOL_CALL/RESULT、BROADCAST、GROUP_MESSAGE
- **群组管理**：创建/加入/离开群组、群组消息广播

## 七、LLM 客户端系统

### 模型路由器

`ModelRouter` 管理多个 LLM 客户端，预配置三种用途：main（主对话，128k 上下文）、summary（摘要）、memory（记忆处理）。当前 `model_defaults`：summary 与 memory 均回退到 main。

### 客户端实现

所有客户端继承 `LLMClient` 抽象基类，统一 `chat()`、`stream_chat()`、`get_embedding()`、`is_available()` 接口。支持 Ollama、VLLM/OpenAI 兼容、Anthropic Claude、DeepSeek、Local 五种。

> **当前默认配置**：main = vLLM `gemma4-e4b` @8002；embedding = vLLM `Qwen3-Embedding-0.6B` @8101；summary/memory = Ollama `qwen3-vl:8b`（禁用，回退 main）。

### 多模态支持

支持图片输入（base64 编码），Agent 配置 `vision_enabled` 控制启用。前端最多上传 4 张图片。

## 八、工具系统

`ToolRegistry`（`backend/core/tools/`）负责工具注册、发现、调用。使用 `@registry.register()` 装饰器注册。

### 工具分类

| 分类 | 说明 | 数量 |
|------|------|------|
| builtin | 内置工具：calculator, datetime, random, json_format | 4 |
| master | 主模型专属工具：write_long_term_memory, search_all_memories, call_assistant, set_alarm, mono, write_permanent_memory, ACP 相关等 | 13 |
| summary | 摘要工具：summarize_content, save_summary_memory | 2 |
| assistant | 记忆管理工具 | 16 |
| graph | 图数据库工具（条件注册） | — |
| mcp | MCP 协议工具（动态注册） | — |
| memory | 记忆工具 | — |

### 记忆管理模型工具 (16 个)

update_memory_node、search_memories、delete_memory、merge_memories、clean_expired、export_memories、get_memory_stats、search_by_time、search_by_tag、bulk_delete、restore_memory、search_similar_memories、get_chat_history、get_similar_memories、get_memory_logs、get_available_commands。

### MCP 协议

`MCPManager` 实现 Model Context Protocol，通过 JSON-RPC 与服务器通信，支持启动/停止 MCP 服务器、同步工具列表、调用远程工具。

## 九、图数据库系统 (Graph Database)

位于 `backend/core/graph/`（15 个文件）。为条件启用模块（`settings.config.graph.enabled`）。

核心文件：`database.py`（初始化连接）、`repository.py`（增删改查）、`nodes.py`/`edges.py`（节点/边管理）、`semantic_search.py`（向量相似度图搜索）、`traversal.py`（BFS/DFS）、`hybrid_query.py`（混合查询）、`vectorizer.py`（向量化）、`visualization.py`（可视化）、`monitoring.py`（监控）。支持 PageRank、社区检测、GraphML/DOT 导出、Neo4j 迁移。

## 十、CXFC 插件协议 (CXFC Manager)

位于 `backend/core/cxfc/`（6 个文件），条件启用（`settings.config.cxfc.enabled`）。负责插件发现、技能注册、心跳管理、连接管理、事件推送。

核心文件：`manager.py`（核心调度）、`discovery.py`（自动发现）、`skill_registry.py`（技能注册）、`storage.py`（持久化）、`models.py`（数据模型）。

## 十一、提醒管理系统 (Alarm Manager)

位于 `backend/core/alarm/`，负责定时提醒、闹钟管理、触发回调。与 WebSocket 集成实现实时提醒推送。

## 十二、备份管理系统 (Backup Manager)

位于 `backend/core/backup/`，支持选择性备份（记忆、会话、Agent 配置等），结构化存储，完整/部分恢复。

## 十三、插件管理系统 (Plugin Manager)

位于 `backend/core/plugins/`，负责插件加载、生命周期管理、运行时上下文注入。支持动态加载/卸载。插件目录为 `plugins/`。

## 十四、WebSocket 管理

位于 `backend/core/websocket/`，负责连接管理、实时通信、离线消息保存。与提醒管理器集成，客户端离线时消息保存，重连后推送。

## 十五、会话管理系统 (Session)

位于 `backend/core/session/`，负责会话存储、清理策略。根据配置的时间和数量阈值自动清理过期会话。

## 十六、异常处理体系

系统定义完整的自定义异常层次，位于 `backend/core/exceptions/`。统一定义全局错误码，避免模块间异常拦截歧义。所有接口契约包含异常说明，调用方必须处理约定异常。

## 十七、前端实现

### 应用结构

React 18 + TypeScript，React Router 路由管理。主要页面（9 个）：

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

### 组件

- **布局**（4 个）：Layout、Header、Sidebar、PageHeader
- **UI 库**（11 个）：Badge、Button、Card、Drawer、Dropdown、EmptyState、Input、Modal、Skeleton、Toast、Tooltip
- **功能**：GraphManager、ConnectionCheck、VirtualList、SummaryModal、ErrorBoundary、LanguageSwitcher

聊天页实现 Markdown 渲染（React Markdown + remark-gfm）、代码高亮、思考过程、工具调用状态展示。

### Hooks

- `useWebSocket` — 5 次自动重连、30 秒心跳、离线超时处理
- `useHotkey` — Ctrl+K（搜索）、Ctrl+N（新建）、Ctrl+S（保存）等

## 十八、测试体系

### 后端测试

pytest + pytest-asyncio（`asyncio_mode=auto`），测试位于 `backend/tests`（18 个文件）：
- `test_api` — API 端点测试
- `test_core` — 核心模块单元测试
- `test_integration` — 集成测试

`conftest.py` 提供 fixture：`client`（TestClient）、`async_client`（AsyncClient）、`mock_settings`。

### 前端测试

Vitest + React Testing Library，位于 `frontend/src`（6 个文件），覆盖 API 客户端、chatStore/themeStore、工具函数。

### LLM E2E 测试

LLM 端到端测试框架（8 个文件），验证 LLM 集成完整性与正确性。

### 统一测试运行器

`run_tests.py` 提供统一入口，支持选择性运行前后端测试、生成覆盖率报告。

## 相关文档

- [项目总览 PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)
- [架构文档 ARCHITECTURE.md](./ARCHITECTURE.md)
- [部署指南 DEPLOYMENT.md](./DEPLOYMENT.md)
- [API 文档 API.md](./API.md)
- [技术文档 TECHNICAL.md](./TECHNICAL.md)
