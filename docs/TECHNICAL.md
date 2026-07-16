# CXHMS (晨曦人格化记忆系统) 详细技术文档

> **文档版本**: v3.0.0 | **最后更新**: 2026-07-17

## 项目概述

CXHMS (CX-O History & Memory Service) 是一个基于 FastAPI 的智能记忆管理平台，提供完整的记忆存储、语义搜索、自动归档、多模型对话、ACP 协议通信、图数据库、CXFC 插件协议、工具调用，以及 **RADIX-Lite 管理 Agent 扩展**（模板引擎 / 多模态管线 / 蒸馏服务 / 决策核心）能力。该项目采用前后端分离架构，后端使用 Python + FastAPI，前端使用 React + TypeScript。

RADIX-Lite 子系统（契约版本 v1.2.0，spec `add-management-agent-radix` 于 2026-07-16 闭合）在原有 15 个核心服务（`backend/core/` 下 13 个子模块 + Model Router + Service State）之上新增 4 个子模块（模块7-10），使 CXHMS 业务模块从 7 个扩展到 11 个，从被动记忆系统升级为可自主决策、多轮蒸馏、多模态理解的智能体记忆平台。

## 系统架构

### 整体架构设计

系统采用分层架构设计，从上到下依次为：

- **服务层** (API / WebUI / Memory / Tools)：对外暴露 RESTful API、WebSocket、WebUI 与记忆/工具操作接口
- **核心服务层**：包含 15 个原始核心服务（Memory Manager / Context Manager / Tools Registry / ACP Manager / Graph Database / CXFC Manager / Alarm Manager / Backup Manager / Plugin Manager / WebSocket Manager / Session Manager / LLM Client / Model Router / Secondary Router / Service State）+ 4 个 RADIX-Lite 子系统（Template Engine / Multimodal Pipeline / Distillation Service / Decision Core）
- **存储层** (SQLite / Redis / Weaviate / Chroma / Milvus Lite / Qdrant)：持久化记忆、会话、图数据、向量索引与蒸馏会话/审计日志

分层设计使得各模块职责清晰，便于维护和扩展。RADIX-Lite 子系统作为独立可插拔模块，通过 `try-except fallback` 到 Mock（rules-0 §三）实现与原有模块的松耦合，不硬依赖真实实现。

### 技术栈详情

**后端技术栈** 包含 Python 3.10+、FastAPI 0.104.1+ 作为 Web 框架、Pydantic 2.5.0+ 用于数据验证、SQLAlchemy 作为 ORM 层。向量存储支持 Weaviate（默认后端）、Chroma（Windows 兼容，0.4.x 版本）、Milvus Lite、Qdrant 等多种后端。LLM 集成方面支持 Ollama、VLLM、OpenAI、Anthropic、DeepSeek 和 Local 兼容接口，工具协议采用 MCP (Model Context Protocol)。RADIX-Lite 子系统额外引入 Jinja2（模板引擎 DSL 渲染）与 ThreadPoolExecutor（多模态 worker 池调度）。

**前端技术栈** 使用 React 18.3.1 构建 UI 框架、TypeScript 5.7.2 确保类型安全、Vite 6.0.6 作为构建工具、Tailwind CSS 3.4.17 处理样式、Zustand 5.0.2 进行状态管理、React Query 5.62.11 负责数据获取、Framer Motion 11.15.0 实现动画效果、Recharts 2.15.0 绘制图表、Lucide React 0.469.0 提供图标、Vitest 2.1.8 作为测试框架。此外还依赖：React Router 6.28.0（路由管理）、i18next 25.8.4 + react-i18next 16.5.4 + i18next-browser-languagedetector 8.2.0（国际化）、Axios 1.7.9（HTTP 客户端）、React Markdown 9.0.1 + remark-gfm 4.0.0（Markdown 渲染）、date-fns 4.1.0（日期处理）、class-variance-authority 0.7.1 + clsx 2.1.1 + tailwind-merge 2.6.0（样式工具）。

## 核心模块详解

### 1. 记忆管理系统 (Memory Manager)

记忆管理系统是 CXHMS 的核心模块，负责所有记忆相关操作。MemoryManager 采用单例模式实现，通过线程锁确保线程安全。数据库采用 SQLite，使用 WAL 模式提高并发性能，并实现了连接池管理。

**数据库架构设计** 包含四个主要表：memories 表存储所有记忆数据，包含 id、type、content、importance、importance_score、decay_type、reactivation_count、emotion_score、permanent、tags、metadata、workspace_id、agent_id 等字段。permanent_memories 表存储永久记忆，audit_logs 表记录所有操作日志，agent_memory_tables 表维护 Agent 与记忆表的映射关系。RADIX-Lite v1.2.0 新增 `rejected_content` 表，用于保留决策化写入被拒绝的内容（保留 30 天，详见 [write_with_decision 技术实现](#write_with_decision-技术实现)）。

**核心方法** 包括 write_memory() 用于创建新记忆、get_memory() 用于获取单条记忆、search_memories() 用于搜索记忆、update_memory() 用于更新记忆、delete_memory() 用于删除记忆（支持软删除）、hybrid_search() 用于混合搜索。混合搜索结合向量相似度和关键词匹配，使用 RRF (Reciprocal Rank Fusion) 算法融合两种搜索结果。RADIX-Lite v1.2.0 新增 3 个决策化方法：write_with_decision() / get_rejected_content() / cleanup_expired_rejected_content()。

**记忆衰减系统** 实现了两种衰减模型：双阶段指数衰减（默认）和艾宾浩斯遗忘曲线优化版（实验性）。双阶段指数衰减公式为 T(t) = α·e^(-λ₁·Δt) + (1-α)·e^(-λ₂·Δt)，其中 α = 0.6、λ₁ = 0.25、λ₂ = 0.04。艾宾浩斯模型公式为 T(t) = 1 / (1 + (Δt/T₅₀)^k)，可通过配置启用。

**情感分析** 系统支持情感评分，每条记忆包含 emotion_score 字段。情感强度会影响记忆重激活时的额外加分。

**去重检测** 系统支持记忆去重，通过 `dedup_threshold` 配置阈值（默认 0.85），在写入新记忆时自动检测相似度超过阈值的已有记忆。

**副模型路由** 系统支持 10 种副模型指令，通过 secondary_router 管理记忆处理、摘要生成等辅助任务。`model_defaults` 配置副模型回退策略：summary 与 memory 副模型默认回退到 main 主模型。

**三维评分系统** 在 search_memories_3d() 方法中实现，综合考虑重要性分数、时间分数和相关度分数。重要性分数由 importance_score 字段决定，时间分数根据衰减模型计算，相关度分数来自搜索匹配度。默认权重分配为 importance × 0.35 + time × 0.25 + relevance × 0.4。

**记忆重激活** recall_memory() 方法实现了记忆召回功能，每次召回会重置时间衰减分数，增加 reactivation_count 计数，并根据情感强度给予额外加分。reactivation_boost 默认 0.2，decay_interval_days 默认 7 天，decay_rate 默认 0.1。

### 2. 向量搜索系统

系统支持五种向量存储后端：Chroma（Windows 兼容，0.4.x 版本）、Milvus Lite（无需额外安装）、Qdrant（需要 Docker 部署）、Weaviate（支持嵌入式和客户端模式，gRPC 端口 50061）、Weaviate Embedded（嵌入式模式）。默认后端为 Weaviate，向量维度 768，使用余弦相似度 (COSINE) 度量。

HybridSearch 类实现了混合搜索功能，将向量搜索和 SQLite 关键词搜索的结果进行融合排序。搜索流程包括：生成查询向量、执行向量搜索、执行关键词搜索、分数融合（RFF 算法）、可选的重排序。`hybrid_search_enabled` 默认关闭，需显式启用。

### 3. 上下文管理系统 (Context Manager)

ContextManager 负责管理会话和消息历史，采用 SQLite 存储会话和消息数据，支持 Mono 上下文（持久化关键信息）功能。

**会话管理** 支持创建会话、获取会话列表、更新会话状态。会话数据包含 id、workspace_id、title、message_count、summary、is_active 等字段。

**消息管理** 支持添加消息、获取消息历史、消息分页。消息数据包含 id、session_id、role（system/user/assistant/mono_context）、content、content_type、tokens 等字段。

**Mono 上下文** 是一种持久化临时上下文的机制，可以在多轮对话中保持关键信息，支持过期时间（expires_at）和轮次限制（rounds_remaining）两种过期方式。

**上下文配置** `context.max_summaries_in_context` 控制上下文中保留的摘要数量，默认值为 10。

### 4. 工具系统

工具系统采用注册表模式设计，ToolRegistry 类负责工具的注册、发现和调用执行。

**内置工具** 包括 calculator（数学计算）、datetime（日期时间获取）、random（随机数生成）、json_format（JSON格式化）等。工具使用装饰器模式注册，通过 @registry.register() 装饰器将函数注册为工具。

**工具分类**:
- `builtin`: 内置工具（calculator, datetime, random, json_format）
- `master`: 主模型专属工具（13个工具，包括 write_long_term_memory, search_all_memories, call_assistant, set_alarm, mono, write_permanent_memory, ACP相关工具等）
- `summary`: 摘要模型工具（2个）
- `assistant`: 记忆管理模型工具（16个）
- `graph`: 图数据库工具
- `mcp`: MCP协议工具
- `memory`: 记忆工具

**主模型专属工具**:
- write_long_term_memory: 写入长期记忆
- search_all_memories: 搜索所有记忆
- call_assistant: 调用记忆管理模型
- set_alarm: 设置定时提醒
- mono: 保持信息在上下文中
- write_permanent_memory: 写入永久记忆
- acp_list_agents: 列出ACP Agent
- acp_connect/acp_disconnect: ACP连接管理
- acp_send_message: ACP消息发送
- acp_create_group/acp_join_group/acp_leave_group: ACP群组管理

**记忆管理模型工具** (16个):
1. update_memory_node - 更新记忆节点内容
2. search_memories - 搜索记忆（关键词搜索）
3. delete_memory - 删除记忆（软删除）
4. merge_memories - 合并多个相似记忆
5. clean_expired - 清理已软删除的记忆
6. export_memories - 导出记忆数据
7. get_memory_stats - 获取记忆库统计信息
8. search_by_time - 按时间范围搜索记忆
9. search_by_tag - 按标签搜索记忆
10. bulk_delete - 批量删除记忆
11. restore_memory - 恢复软删除的记忆
12. search_similar_memories - 搜索相似记忆
13. get_chat_history - 获取聊天历史
14. get_similar_memories - 获取相似记忆
15. get_memory_logs - 获取操作日志
16. get_available_commands - 获取可用命令列表

**MCP 协议支持** MCPManager 类实现了 Model Context Protocol 协议，支持启动/停止 MCP 服务器、同步工具列表、调用远程工具。MCP 工具通过 JSON-RPC 与服务器通信。

**工具调用流程** 工具定义以 OpenAI Functions 格式传递给 LLM，LLM 返回工具调用请求后，系统执行工具函数并将结果返回给 LLM 继续生成最终响应。`llm.max_tool_rounds` 默认 10，流式与非流式统一。

### 5. ACP 协议 (Agent Communication Protocol)

ACP 协议用于多 Agent 通信，支持局域网发现、点对点通信、群组协同和跨 Agent 记忆共享。

**局域网发现** ACPLanDiscovery 类实现 UDP 广播发现机制，使用端口 9999（发现请求）和 9998（广播响应）。每个 Agent 定期广播自己的存在，并扫描网络中的其他 Agent。

**消息传递** ACPManager 类负责消息的发送和接收，支持多种消息类型：CHAT（聊天消息）、MEMORY_REQUEST/RESPONSE（记忆请求/响应）、TOOL_CALL/RESULT（工具调用/结果）、BROADCAST（广播）、GROUP_MESSAGE（群组消息）。

**群组管理** 支持创建群组、加入/离开群组、向群组发送消息等操作。群组消息会被发送到所有群组成员。

### 6. 图数据库系统 (Graph Database)

图数据库系统位于 `backend/core/graph/`（15个文件），负责知识图谱管理、节点/边 CRUD、语义搜索、路径分析、社区检测、PageRank 算法、可视化、GraphML/DOT导出和Neo4j迁移。

**核心文件**:
- `database.py`: 数据库管理，负责图数据库的初始化和连接
- `repository.py`: 数据操作，提供图数据的增删改查接口
- `nodes.py`: 节点管理，支持节点的创建、更新、删除和查询
- `edges.py`: 边管理，支持边的创建、更新、删除和查询
- `semantic_search.py`: 语义搜索，基于向量相似度的图搜索
- `traversal.py`: 图遍历，支持 BFS、DFS 等遍历算法
- `hybrid_query.py`: 混合查询，结合结构化查询和语义搜索
- `vectorizer.py`: 向量化，将图数据转换为向量表示
- `visualization.py`: 可视化，生成图结构的可视化数据
- `monitoring.py`: 监控，图数据库运行状态监控

图数据库为条件启用模块，通过配置文件 `graph.enabled: true` 控制是否在启动时初始化。Weaviate 集成使用 gRPC 端口 50061、向量维度 768、HNSW 索引参数（ef_construction=128, max_connections=16）。

### 7. CXFC 插件协议 (CXFC Manager)

CXFC 插件协议系统位于 `backend/core/cxfc/`（6个文件），负责插件发现、技能注册、心跳管理、连接管理和事件推送。

**核心文件**:
- `manager.py`: 管理器，CXFC 协议的核心调度
- `discovery.py`: 发现服务，自动发现网络中的 CXFC 插件
- `skill_registry.py`: 技能注册，管理插件提供的技能
- `storage.py`: 存储，持久化插件和技能信息
- `models.py`: 数据模型，定义 CXFC 相关的数据结构

CXFC 管理器为条件启用模块，通过配置文件 `cxfc.enabled: true` 控制是否在启动时初始化。发现端口 19876，心跳超时 60 秒，支持自动重连。

### 8. 提醒管理系统 (Alarm Manager)

提醒管理系统位于 `backend/core/alarm/`，负责定时提醒、闹钟管理和触发回调。系统与 WebSocket 集成，实现实时提醒推送，确保用户在连接时能即时收到提醒通知。

### 9. 备份管理系统 (Backup Manager)

备份管理系统位于 `backend/core/backup/`，负责数据备份与恢复。支持选择性备份，可按类别选择备份内容，包括记忆、会话、Agent 配置等。备份文件以结构化格式存储，支持完整恢复和部分恢复。

### 10. 插件管理系统 (Plugin Manager)

插件管理系统位于 `backend/core/plugins/`，负责插件的加载、生命周期管理和上下文注入。插件系统支持动态加载和卸载，为插件提供运行时上下文注入能力，使插件能够访问系统核心功能。

### 11. WebSocket 管理

WebSocket 管理系统位于 `backend/core/websocket/`，负责 WebSocket 连接管理、实时通信和离线消息保存。系统与提醒管理器集成，支持实时提醒推送。当客户端离线时，消息会被保存，待客户端重新连接后推送。

### 12. 会话管理系统 (Session)

会话管理系统位于 `backend/core/session/`，负责会话存储、清理策略和数据模型定义。系统实现了自动化的会话清理策略，根据配置的时间和数量阈值清理过期会话。

### 13. LLM 客户端系统

**模型路由器** ModelRouter 类管理多个 LLM 模型客户端，支持按需切换不同模型。系统预配置三种模型用途：main（主对话模型，128k 上下文）、summary（摘要生成）、memory（记忆处理）。`model_defaults` 指定回退策略：summary 与 memory 均默认回退到 main。

**客户端实现** 支持 Ollama（本地）、VLLM/OpenAI 兼容接口、Anthropic Claude、DeepSeek 和 Local 五种客户端。所有客户端继承自 LLMClient 抽象基类，实现统一的 chat()、stream_chat()、get_embedding() 和 is_available() 接口。默认主模型为 vLLM 提供的 gemma4-e4b（http://localhost:8002），Embedding 模型为 Qwen3-Embedding-0.6B（http://localhost:8101）。

**多模态支持** 支持图片输入，通过 base64 编码传递图片数据。Agent 配置中的 vision_enabled 字段控制是否启用多模态功能。RADIX-Lite 多模态管线（模块8）进一步扩展了多模态预处理能力。

**流式响应** 使用 Server-Sent Events (SSE) 实现流式输出，客户端通过异步迭代器接收增量响应。支持多种事件类型：session、thinking、content、tool_call、tool_start、tool_result、done、error。`llm.temperature` 默认 1.5，`llm.max_tool_rounds` 默认 10。

### 14. Agent 系统

**Agent 配置管理** 位于 backend/api/routers/agents.py，提供 Agent 的 CRUD 操作、克隆、统计和上下文管理功能。RADIX-Lite v1.2.0 在 Agent 配置中新增 3 个字段：`tools_config`（8 工具方法配置）、`decision_rubric`（4 阈值）、`distillation_enabled`（蒸馏开关），使管理 Agent 具备自主决策能力。

**默认 Agent**:
- `default`: 默认助手，使用 main 模型，128k 上下文，支持记忆和工具
- `memory-agent`: 记忆管理助手，使用 memory 模型，128k 上下文，16个记忆管理工具

**Agent 上下文持久化** AgentContextManager 类负责管理 Agent 的持久化上下文，支持跨会话保存消息历史。

**聊天架构** 每个 Agent 对应一个固定会话（session_id = agent-{agent_id}），前端只发送最新消息，后端根据 Agent 配置构建完整上下文。

### 15. API 路由系统

FastAPI 应用包含 17 个路由模块：
- `chat.py`: 处理聊天对话请求（支持Agent和多模态）
- `memory.py`: 处理记忆 CRUD 操作、批量操作、语义搜索、决策化写入（write-with-decision / rejected-content）
- `context.py`: 处理会话和消息管理
- `tools.py`: 处理工具注册和调用、MCP服务器管理
- `acp.py`: 处理 ACP 协议
- `agents.py`: 处理 Agent 配置和上下文管理（含 RADIX-Lite tools_config / decision_rubric / distillation_enabled）
- `archive.py`: 处理归档管理
- `config.py`: 处理配置管理
- `cxfc.py`: 处理 CXFC 插件协议
- `graph.py`: 处理图数据库操作
- `stats.py`: 处理统计数据
- `vector.py`: 处理向量搜索操作
- `service.py`: 处理服务管理
- `backup.py`: 处理备份恢复
- `websocket.py`: 处理 WebSocket 连接
- `admin.py`: 处理管理员功能

RADIX-Lite 蒸馏服务作为独立 FastAPI 子服务运行在端口 8011，提供 4 个 API 端点（`/api/radix/distillation/*`）。

**聊天流程**:
1. 用户发送消息后，系统获取 Agent 配置
2. 管理 Agent 专属会话（每个 Agent 一个固定会话）
3. 检索相关记忆（如果启用）
4. 构建消息列表（系统提示词 + 记忆上下文 + 历史消息 + 当前消息）
5. 获取工具列表（根据 Agent 配置过滤）
6. 调用 LLM 生成响应（支持流式）
7. 处理工具调用（如有）
8. 保存助手响应到上下文

## RADIX-Lite 子系统技术详解 (v1.2.0 新增)

RADIX-Lite 是 spec `add-management-agent-radix`（2026-07-16 闭合）引入的管理 Agent 扩展子系统，采用融合方案 C（去除音视频模态，保留 3 独立子系统 + 7 状态机多轮蒸馏 + Jinja2 DSL 模板 + 6 决策点自主决策）。spec 三件套已通过 GN-004 交付前独立审查（6 维度全 PASS，0 阻断 0 警示 3 观察项非阻断），[V] 双重闸门已闭合（GN-004 通过 + 人类批准交付）。

### 16. 模板引擎技术 (模块7)

模板引擎系统位于 `modules/模块7_模板引擎/`，核心实现 `template_engine.py`（911 行）。负责 Jinja2 DSL 模板渲染、frontmatter 解析与模板 CRUD 管理，为蒸馏服务提供 prompt 模板支撑。

**Jinja2 DSL 渲染原理**:
- 采用 YAML frontmatter + Jinja2 原生渲染，支持完整 Jinja2 语法：`extends` / `block` / `if` / `elif` / `else` / `for` / `include` / `filter`
- 使用 `ChoiceLoader(FileSystemLoader)` 加载 `presets/` + `custom/` 双目录，预设模板与自定义模板分层管理
- 渲染配置：`autoescape=False`（模板是 prompt 而非 HTML）、`trim_blocks=True`、`lstrip_blocks=True`（减少空白噪声）
- 自定义 filter：`confidence_label`（将 0-1 的置信度浮点数映射为"低/中/高"标签）
- 模板仓库位于 `data/templates/`，分 `presets/`（预设）和 `custom/`（自定义）两个子目录
- `auto_init` 机制：目录不存在时自动创建并生成默认预设模板

**frontmatter 解析机制**:
- 使用正则 `_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)` 解析 YAML frontmatter 与模板体
- frontmatter 包含模板元数据（template_id / category / workflow_mode 等），body 为 Jinja2 模板内容
- 枚举约束：`_CATEGORIES = {"preset", "custom"}`，`_WORKFLOW_MODES = {"single_turn", "multi_turn"}`
- template_id 必须匹配 `^[a-zA-Z0-9_-]+$` 模式

**CRUD 实现**:
- `render_template()`: 渲染模板，传入上下文变量返回最终 prompt
- `create_template()` / `get_template()` / `update_template()` / `delete_template()`: 模板增删改查
- `list_templates()`: 列出模板
- `_parse_frontmatter()`: 内部 frontmatter 解析方法

**对应契约**:
- 接口契约: `public/interface_stub/template_engine.pyi`（7 方法）
- 数据契约: `public/schema/template_registry.schema.json`
- 配置契约: `public/config_template/radix_config.json`（template_engine 段）

### 17. 多模态管线技术 (模块8)

多模态管线系统位于 `modules/模块8_多模态管线/`，核心实现 `multimodal_pipeline.py` + 3 个 worker 文件（合计 1242 行）。负责多模态输入的预处理，接管 `backend/core/document/parser.py` 下沉的解析能力（Task 6 改造 parser.py 为 thin wrapper，调用本管线）。

**3 worker 架构**（源类型枚举：text / character_card / image）:
- **TextWorker**（文本预处理 worker）: 处理纯文本输入，提取结构与元数据
- **CharacterCardWorker**（角色卡 OCR worker）: 对角色卡进行 OCR 解析，提取角色卡字段（对应对外简称"OCR"）
- **ImageWorker**（图像视觉 worker）: 调用 vLLM 视觉模型进行图像理解（对应对外简称"视觉"）

对外 README 简称为"OCR / 视觉 / 文本"三模态架构。

**worker 池调度**:
- 使用 `ThreadPoolExecutor` 调度 worker 池（避免 Windows `ProcessPool` pickle 问题）
- 默认配置：`worker_pool_size=4`、`task_timeout_seconds=120`、`enabled_modalities=["text", "character_card", "image"]`
- `ocr_language="ch"`（中文 OCR）、`vision_base_url="http://127.0.0.1:8002"`、`vision_timeout_seconds=300`

**模态融合算法**:
- 产出统一的 `MultimodalArtifact` 数据模型，包含 3 模态的 `type` 枚举、`confidence` 置信度、`vision_degraded` 降级标志
- `_merge_ocr_vision()` 方法融合 OCR 文本与视觉理解结果
- 融合时综合考虑各模态置信度，低置信度模态降权

**降级开关机制**:
- `vision_degraded` 标志：当 vLLM 视觉模型不可用时，自动降级为仅返回 OCR 结果
- 降级时 `MultimodalArtifact.vision_degraded=True`，保留 OCR 通道输出
- 配合 `auto_fill` 兜底：缺失配置字段自动补齐默认值（rules-3 §三）

**对应契约**:
- 接口契约: `public/interface_stub/multimodal_pipeline.pyi`（7 方法：preprocess + 3 worker + _merge_ocr_vision）
- 数据契约: `public/schema/multimodal_artifact.schema.json`（3 模态 type 枚举 + confidence + vision_degraded）
- 配置契约: `public/config_template/radix_config.json`（multimodal_pipeline 段 + vllm 段）

### 18. 蒸馏服务技术 (模块9)

蒸馏服务系统位于 `modules/模块9_蒸馏服务/`，核心实现 `distillation_service.py`（720 行）+ API 子服务（`api/app.py` + `api/routes.py`）。作为独立 FastAPI 子服务运行在端口 8011，提供 7 状态机多轮蒸馏工作流。

**7 状态机多轮蒸馏原理**:

状态流转：`draft → collecting → distilling → refining → reviewing → finalizing → finalized`

| 状态 | 含义 |
|------|------|
| `draft` | 草稿初始状态，蒸馏会话创建 |
| `collecting` | 信息收集阶段，多轮收集输入素材 |
| `distilling` | 蒸馏执行阶段，LLM 提取核心内容 |
| `refining` | 精炼阶段，对蒸馏结果优化 |
| `reviewing` | 审查阶段，交叉验证与质量评估 |
| `finalizing` | 终化阶段，准备最终产出 |
| `finalized` | 终态，蒸馏完成 |

**状态转换规则**:
- 正向流转：按 `draft → collecting → distilling → refining → reviewing → finalizing → finalized` 顺序推进
- 回环：`reviewing → collecting`（由 D4_REDISTILL 决策驱动，受 `max_redistill_turns` 限制）
- 主动追问：`ask_user_on_ambiguity=True` 且处于 collecting 阶段时，agent_action=ask_user
- 拒绝路径：低置信度 / max_turns 超限 / quality_score 低于阈值时进入拒绝状态

**4 API 端点**（端口 8011，`/api/radix/distillation/*`）:
- `POST /start`: 启动蒸馏会话
- `POST /advance`: 推进状态机到下一阶段
- `POST /finalize`: 终化并产出最终结果
- `GET /get`: 获取会话状态与历史

**会话持久化**:
- 蒸馏会话存储于 `data/distillation_sessions/{session_id}.json`
- 决策审计日志存储于 `data/distillation_logs/{session_id}.json`

**对应契约**:
- 接口契约: `public/interface_stub/distillation_service.pyi`（4 API 端点 + 1 内部方法 _transition_state）
- 数据契约: `public/schema/distillation_session.schema.json`（7 状态 + turns 数组 + final_decision）
- 数据契约: `public/schema/distillation_log.schema.json`（6 决策点 + llm_reasoning + final_decision）
- 配置契约: `public/config_template/radix_config.json`（distillation_service 段）

### 19. 管理Agent扩展技术 (模块10)

管理 Agent 扩展系统位于 `modules/模块10_管理Agent扩展/`，核心实现 `decision_core.py`（580 行）+ `agent_tools.py`（560 行）。负责 6 决策点自主决策，由 rubric 驱动，使管理 Agent 具备自主蒸馏与存储决策能力。

**6 决策点自主决策原理**:

| 决策点 | 名称 | 触发时机 |
|--------|------|---------|
| D1 | `distill_start` | 蒸馏启动决策 |
| D2 | `distill_collect` | 蒸馏收集决策 |
| D3 | `distill_advance` | 蒸馏推进决策 |
| D4 | `distill_finalize` | 蒸馏终化决策 |
| D5 | `storage_decision` | 存储决策（3 location 枚举 + quality_score） |
| D6 | `content_merge` | 内容合并决策 |

**rubric 驱动机制**:
- `RubricSnapshot` 模型包含 4 个阈值：
  - `importance_threshold_permanent`: 永久记忆重要性阈值
  - `quality_reject_threshold`: 质量拒绝阈值
  - `max_redistill_turns`: 最大重蒸馏轮次
  - `ask_user_confidence_threshold`: 主动追问置信度阈值
- rubric 不可被 LLM 自行修改，仅人类通过编辑 `data/agents.json` 调整
- 决策输入 `DecisionInput`：artifact_summary / session_state / turn_history_summary / extracted_content / quality_score
- 最终决策 `FinalDecision.action` 枚举：`store` / `ask_user` / `redistill` / `cross_validate` / `reject` / `skip`

**审计日志**:
- 决策审计日志持久化到 `data/distillation_logs/{session_id}.json`
- 每条日志记录 6 决策点、`llm_reasoning`（LLM 推理过程）、`final_decision`
- 日志与蒸馏会话一一对应，支持完整回溯

**降级与回退**:
- LLM 置信度极低或不可用时，回退到 system_prompt 规则（rules-0 §三 fallback）
- 不硬依赖真实 LLM 实现，保证服务可用性

**8 工具方法**（`agent_tools.py`）:
- 管理 Agent 调用的 8 个工具方法，对应 `agent_tools_v2.pyi` 接口契约
- 通过 `tools_config` 字段配置启用状态

**对应契约**:
- 接口契约: `public/interface_stub/decision_core.pyi`（9 方法：6 决策点 + _load_rubric + _llm_decide + _write_audit_log）
- 接口契约: `public/interface_stub/agent_tools_v2.pyi`（8 工具方法）
- 数据契约: `public/schema/storage_decision.schema.json`（3 location 枚举 + rubric_snapshot + quality_score）
- 数据契约: `public/schema/distillation_log.schema.json`
- 数据契约: `public/schema/agent_config_v2.schema.json`（tools_config 8 工具 + decision_rubric 4 阈值 + distillation_enabled）
- 配置契约: `public/config_template/radix_config.json`（decision_core 段 + vllm 段）

### write_with_decision 技术实现

`write_with_decision` 是 RADIX-Lite v1.2.0 在 `backend/core/memory/manager.py` 新增的决策化写入能力，使记忆写入过程经过 DecisionCore 评估，被拒绝的内容保留 30 天供审计与回溯。

**WriteWithDecisionResult 数据结构**:
- 决策化写入返回 `WriteWithDecisionResult`，包含写入决策结果与（如被拒绝的）原始内容
- 与 `storage_decision.schema.json` 契约对齐：3 location 枚举（permanent / long_term / rejected）+ rubric_snapshot + quality_score

**rejected_content 表**（保留 30 天）:
- 新增 SQLite 表 `rejected_content`，存储被 DecisionCore 拒绝的记忆内容
- 保留期限 30 天，超期自动清理
- 支持审计回溯：可查询历史被拒绝内容及其拒绝理由

**3 个新增方法**:
- `write_with_decision()`: 决策化写入，先经 DecisionCore 评估再决定是否持久化
- `get_rejected_content()`: 获取被拒绝的内容列表（30 天保留期内）
- `cleanup_expired_rejected_content()`: 清理过期（超过 30 天）的拒绝内容

**对应契约**:
- 接口契约: `public/interface_stub/memory_manager_v2.pyi`（3 方法）
- 下游影响：`backend/core/document/parser.py` 新增 `parse_attachments_v2` 双模式入口（`legacy_parser_enabled` 开关，默认 True 向后兼容）

## 前端实现

### 应用结构

前端采用 React + TypeScript 构建，使用 React Router 进行路由管理。主要页面包括：
- `DashboardPage`: 仪表盘页面
- `ChatPage`: 聊天页面（支持Agent选择、流式响应、工具调用展示、双通信模式、图片上传、思考过程展示、提醒通知）
- `MemoriesPage`: 记忆管理页面
- `ArchivePage`: 归档管理页面
- `AgentsPage`: Agent 配置页面（含 RADIX-Lite tools_config / decision_rubric / distillation_enabled 字段）
- `AcpPage`: ACP 控制页面
- `ToolsPage`: 工具管理页面
- `SettingsPage`: 设置页面（支持离线超时时间配置）
- `MemoryAgentPage`: 记忆管理 Agent 专用页面（支持思考过程展示）

**ConnectionCheck 组件**: 检测后端可用性，不可用时显示配置界面，10秒自动重试，支持动态配置后端地址。

**双通信模式**: ChatPage 同时支持 WebSocket（实时）和 SSE 流式（降级）两种通信方式，优先使用 WebSocket，连接失败时自动降级为 SSE。

**提醒功能**: WebSocket 支持 alarm 类型消息，ChatPage 显示定时提醒通知。

**视觉/多模态支持**: ChatPage 支持图片上传，当 Agent 启用 vision_enabled 时，最多可上传4张图片（base64编码）。

**思考过程展示**: ChatPage 和 MemoryAgentPage 支持展示AI思考过程和工具调用详情。

**离线超时机制**: SettingsPage 可配置离线超时时间，断开连接超过此时间后自动保存上下文到长期记忆。

### 状态管理

使用 Zustand 进行状态管理，主要 store 包括：

**chatStore**: 管理聊天相关状态，包括：
- agents, currentAgentId, isLoadingAgents, agentsError, isHydrated
- sessions, currentSessionId, isLoadingSessions, sessionsError
- isChatExpanded
- 持久化策略：仅 currentAgentId、currentSessionId、isChatExpanded 持久化到 localStorage

**themeStore**: 管理主题设置，支持 light/dark/system 三种模式。状态持久化使用 localStorage。

### API 客户端

前端采用双客户端架构：

**主后端客户端**（端口8001）：封装所有主后端 API 调用，包括记忆 CRUD、聊天发送（支持流式接收）、会话管理、ACP 操作、工具管理、决策化写入（write-with-decision / rejected-content）等。内置缓存和重试机制，支持 SSE 流式响应。

**控制服务客户端**（端口8765）：封装控制服务 API 调用，包括图数据库 API、向量数据库 API、CXFC API、配置 API 等。

两个客户端均使用 Axios 发送 HTTP 请求，支持请求拦截器和响应拦截器。

### 国际化

前端使用 i18next + react-i18next 实现多语言支持，i18next-browser-languagedetector 自动检测用户语言偏好。默认语言为 zh-CN，同时支持 en-US。语言资源文件按模块组织，支持动态切换语言。

### 组件设计

**布局组件**（4个）：Layout（布局容器）、Header（顶部导航）、Sidebar（侧边栏）、PageHeader（页面标题栏）。

**UI 组件库**（11个）：Badge（徽标）、Button（按钮）、Card（卡片）、Drawer（抽屉）、Dropdown（下拉菜单）、EmptyState（空状态）、Input（输入框）、Modal（弹窗）、Skeleton（骨架屏）、Toast（消息提示）、Tooltip（提示框）。

**功能组件**：GraphManager（图数据库管理）、ConnectionCheck（连接检测）、VirtualList（虚拟列表）、SummaryModal（摘要保存弹窗）、ErrorBoundary（错误边界）、LanguageSwitcher（语言切换）。

聊天页面实现了 Markdown 渲染（React Markdown + remark-gfm）、代码高亮、思考过程显示、工具调用状态展示等功能。

### Hooks

**useWebSocket**: WebSocket 连接管理 Hook，支持5次自动重连、30秒心跳检测、离线超时处理。

**useHotkey**: 快捷键管理 Hook，预定义快捷键包括 Ctrl+K（搜索）、Ctrl+N（新建）、Ctrl+S（保存）等。

## 配置系统

### 配置文件

系统使用 YAML 格式配置文件 (`config/default.yaml`)，配置结构包含：server（服务器配置）、cors（CORS配置）、logging（日志配置）、database（数据库配置）、llm（LLM 参数，max_tool_rounds=10 / temperature=1.5 / max_tokens=4096）、models（多模型配置，含 main/embedding/summary/memory 各自的 provider/host/model/apiKey/enabled/port/temperature/max_tokens/timeout）、model_defaults（模型默认回退：summary=main / memory=main）、agent（Agent配置）、memory（记忆配置，包括衰减、向量存储、归档、去重等）、context（上下文配置）、tools（工具配置）、acp（ACP 协议配置）、cxfc（CXFC配置）、graph（图数据库配置）、security（安全配置）、monitoring（监控配置）、llm_params（LLM参数，仅参考）。

**关键配置值**（对齐 `config/default.yaml`）:

```yaml
server:
  port: 8001              # API 服务端口

models:
  main:                   # 默认主模型（vLLM, gemma4-e4b）
    provider: vllm
    host: http://localhost:8002
    enabled: true
    temperature: 0.7
  embedding:              # Embedding 模型（Qwen3-Embedding-0.6B）
    provider: vllm
    host: http://localhost:8101
    enabled: true
  summary:                # 摘要副模型（默认禁用，回退 main）
    provider: ollama
    model: qwen3-vl:8b
    enabled: false
  memory:                 # 记忆副模型（默认禁用，回退 main）
    provider: ollama
    model: qwen3-vl:8b
    enabled: false

model_defaults:
  summary: main           # 摘要副模型回退到 main
  memory: main            # 记忆副模型回退到 main

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
    grpc_port: 50061             # Weaviate gRPC 端口
    vector_dim: 768

llm:
  max_tool_rounds: 10            # 流式与非流式统一
  temperature: 1.5
  max_tokens: 4096
```

**注意**: `default.yaml` 中的 `llm_params`、`agent`、`security`、`monitoring`、`tools` 配置段不会被 CXHMSConfig 加载，仅作为参考。`graph` 和 `cxfc` 是 `settings.py` 中的配置段，用于控制图数据库和 CXFC 的条件启用。

**RADIX-Lite 子系统配置** 见 `public/config_template/radix_config.json`（5 段：distillation_service / multimodal_pipeline / template_engine / decision_core / vllm）。

### 配置加载

Settings 类采用单例模式，使用 PyYAML 解析配置文件。配置类使用 Python dataclass 定义，支持类型检查和默认值设置。配置系统支持环境变量覆盖（CXHMS_前缀），并通过 `config/validation.py` 进行配置验证，`config/repair.py` 提供自动修复功能。

## 部署与运维

### 启动流程

主程序 `main.py` 加载配置、初始化日志、启动 Uvicorn 服务器。FastAPI 应用使用 lifespan 上下文管理器处理启动和关闭逻辑，启动时依次初始化 18 个核心组件 + RADIX-Lite 子系统：

**核心组件初始化顺序**（18 项）:
1. 模型路由器
2. 记忆管理器
3. 上下文管理器
4. ACP管理器 (含start())
5. LLM客户端 (优先从model_router获取)
6. 副模型路由器
7. MCP管理器
8. 内置工具注册
9. 主模型工具注册
10. 摘要模型工具注册
11. 记忆管理模型工具注册
12. 向量搜索启用
13. 提醒管理器 + WebSocket离线保存
14. 异步记忆管理器
15. 图数据库 + SQLiteGraphStore (条件启用，graph.enabled=true)
16. CXFC管理器 (条件启用，cxfc.enabled=true，含start())
17. 图数据库工具注册 (条件注册)
18. ServiceState注入

**RADIX-Lite 子系统初始化**:
- 蒸馏服务作为独立 FastAPI 子服务启动（端口 8011），与主服务并行运行
- 多模态管线在首次调用时懒加载 worker 池（ThreadPoolExecutor，pool_size=4）
- 模板引擎在首次调用时加载 `data/templates/` 目录（presets + custom）
- DecisionCore 从 `data/agents.json` 读取 rubric 配置，初始化审计日志目录

**ServiceState 属性**: memory_manager, async_memory_manager, context_manager, acp_manager, llm_client, secondary_router, mcp_manager, model_router, graph_database, graph_store, cxfc_manager(Optional)

**关闭顺序**: CXFCManager → GraphDatabase → AlarmManager → WebSocketManager(stop_cleanup_task) → ACPManager(stop) → MemoryManager → BackupManager → PluginManager → ModelRouter → RADIX-Lite 蒸馏服务（独立关闭）

### Docker 部署

项目提供 Dockerfile 和 docker-compose.yml，支持容器化部署。Dockerfile 基于 Python 镜像，安装依赖后启动服务。docker-compose 编排后端服务和可选的 Qdrant/Weaviate 服务。

## 测试体系

### 后端单元测试

使用 pytest 框架，测试文件位于 `tests/` 目录。pytest 配置：`asyncio_mode=auto`，支持异步测试自动检测。`conftest.py` 提供常用 fixture：client（TestClient）、async_client（AsyncClient）、mock_settings。

**后端单元测试**：753 passed，位于 `tests/units/` + `tests/simulation/`。测试分类包括：test_api（API 端点测试）、test_core（核心模块单元测试）、test_integration（集成测试）。测试覆盖了健康检查、聊天功能、记忆管理、Agent 管理等主要功能。

### RADIX-Lite 单元测试

**RADIX-Lite 单元测试**：262 passed，位于 `tests/contract/`。分布如下：
- `radix_contract_test.py`: 105 用例（契约校验）
- `test_distillation_service_unit.py`: 50 用例（蒸馏服务状态机）
- `test_decision_core_unit.py`: 55 用例（决策核心 6 决策点）
- `test_multimodal_pipeline_unit.py`: 28 用例（多模态管线 3 worker）
- `test_template_engine_smoke.py`: 24 用例（模板引擎 CRUD + 渲染）

### 接口契约测试

**接口契约测试**：437 passed，位于 `tests/contracts/`。校验 `public/interface_stub/*.pyi` 存根与真实实现的签名匹配，覆盖 RADIX-Lite 6 类 locator。

### E2E 测试

**E2E 测试**：37 passed，位于 `tests/e2e/`，包含 `test_radix_task6_integration.py`（RADIX-Lite Task 6 集成测试，依赖真实 vLLM）。

### 测试统计合计

| 套件 | 数量 | 位置 |
|------|------|------|
| 后端单元测试 | 753 passed | `tests/units/` + `tests/simulation/` |
| RADIX-Lite 单元测试 | 262 passed | `tests/contract/` |
| 接口契约测试 | 437 passed | `tests/contracts/` |
| E2E 测试 | 37 passed | `tests/e2e/` |
| **合计** | **1489 passed** | — |

### 前端测试

使用 Vitest + React Testing Library，测试文件位于 `frontend/src` 目录。测试覆盖 API 客户端、状态管理 (chatStore/themeStore)、工具函数等。

### LLM E2E 测试框架

项目包含 LLM 端到端测试框架，用于验证 LLM 集成的完整性和正确性。

### 统一测试运行器

`run_tests.py` 提供统一的测试入口，支持选择性运行前后端测试、生成覆盖率报告。

## 扩展能力

### 插件系统

项目实现了完整的插件管理系统（位于 `backend/core/plugins/`），支持工具插件、存储后端插件、LLM 提供商插件的扩展。插件系统提供动态加载、生命周期管理和上下文注入能力。此外，CXFC 插件协议（位于 `backend/core/cxfc/`）提供了插件发现、技能注册、心跳管理和连接管理功能，支持网络中的插件自动发现和协同工作。插件目录为 plugins/，包含示例插件实现。

### 水平扩展

系统设计为无状态，支持负载均衡部署。共享存储（PostgreSQL/Redis/Qdrant Cluster）可用于生产环境多节点部署。RADIX-Lite 蒸馏服务作为独立子服务，可单独水平扩展。

## 契约版本

当前三层契约版本：**v1.2.0**（2026-07-16）

契约资产清单（v1.2.0 累计）：
- **13 份数据契约** (`public/schema/`)：JSON Schema (draft-07+)
  - v1.0.0：memory.json / agent.json / message.json / tool.json / error.json（5 份）
  - v1.0.1：graph_node.json / graph_edge.json（2 份）
  - v1.1.0：anythingllm_workspace.json / openai_chat_completion.json（2 份）
  - v1.2.0：distillation_session / multimodal_artifact / template_registry / storage_decision / distillation_log / agent_config_v2（6 份）
- **13 份接口契约** (`public/interface_stub/`)：.pyi 存根
  - v1.0.0：memory_service / chat_service / agent_service / tool_service / graph_service（5 份）
  - v1.1.0：anythingllm_service（1 份）
  - v1.2.0：distillation_service / template_engine / multimodal_pipeline / decision_core / memory_manager_v2 / agent_tools_v2（6 份）
- **5 份配置契约** (`public/config_template/`)：JSON Schema（含默认值）
  - v1.0.0：llm_config / vector_config / system_config（3 份）
  - v1.2.0：radix_config.json（1 份，5 段）
- **12 份预生成 Mock** (`public/pre_generated_mock/`)：对应接口的默认 Mock 实现
  - v1.0.0：5 份
  - v1.2.0：6 份（RADIX-Lite 对应接口）+ 1 份 anythingllm

契约变更历史详见 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md)。

---

*文档版本: v3.0.0*
*最后更新: 2026-07-17*
