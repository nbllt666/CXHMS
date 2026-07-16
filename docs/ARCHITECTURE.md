# CXHMS 架构文档

> **文档版本**: v3.0.0 | **最后更新**: 2026-07-17

## 系统概述

CXHMS（CX-O History & Memory Service / 晨曦人格化记忆系统）是一个 AI 代理中间层服务，提供长期记忆存储、语义搜索、自动归档、多模型对话、ACP 协议通信、图数据库、CXFC 插件协议、工具调用以及 RADIX-Lite 管理 Agent 扩展（模板引擎 / 多模态管线 / 蒸馏服务 / 决策核心）功能。

CXHMS 采用 AC 范式 v6 的模块化架构，业务模块区共 11 个模块（模块0 ~ 模块10），其中模块7-10 为 RADIX-Lite v1.2.0 新增子系统。三层契约版本 v1.2.0（13 schema + 13 .pyi + 5 config + 12 mock），通过 GN-004 交付前审查与 [V] 双重闸门闭合（2026-07-16）。

---

## 一、整体架构

### 1.1 模块全景图（11 模块）

CXHMS 按 AC 范式 v6 划分为 11 个业务模块，模块0-6 为主干服务，模块7-10 为 RADIX-Lite v1.2.0 新增子系统。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CXHMS 业务模块区（11 模块）                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  模块0_全局调度面板   全局调度与进度监控（无业务逻辑，仅编排）                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  模块1_记忆服务       记忆存储 / 向量检索 / 三维评分 / 衰减 / 决策化写入        │
│  模块2_对话服务       对话与上下文 / 流式响应 / RAG / 多 Agent                  │
│  模块3_工具与ACP      工具系统（MCP）+ ACP 代理通信协议                        │
│  模块4_图数据库       知识图谱 / 语义搜索 / 路径分析 / PageRank               │
│  模块5_前端展示       React 18 + Vite + Tailwind + i18next                    │
│  模块6_辅助服务       提醒 / 备份 / 插件 / WebSocket / 会话                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ▼▼ RADIX-Lite v1.2.0 新增子系统（模块7-10）▼▼                              │
│  模块7_模板引擎       Jinja2 DSL 模板渲染 + frontmatter 解析 + CRUD           │
│  模块8_多模态管线     3 worker（OCR / 视觉 / 文本）+ 模态融合 + 降级开关       │
│  模块9_蒸馏服务       7 状态机多轮蒸馏 + 4 API 端点（端口 8011）              │
│  模块10_管理Agent扩展 6 决策点 + 8 工具方法 + rubric 驱动                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 分层架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          接口层 interfaces/                              │
│   app.py (FastAPI lifespan)  ·  main.py (Uvicorn)  ·  start.bat         │
├──────────────────────────────────────────────────────────────────────────┤
│                          API 层 backend/api/routers/                    │
│  chat · memory · context · tools · acp · admin · archive · service     │
│  agents · backup · websocket · memory_chat · stats · config            │
│  vector · graph · cxfc                                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                       核心服务层 backend/core/                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Memory   │ │ Context  │ │ Tools    │ │ ACP      │ │ Session  │      │
│  │ Manager  │ │ Manager  │ │ Registry │ │ Manager  │ │ Manager  │      │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘      │
│  ┌────┴─────┐ ┌─────┴────┐ ┌─────┴────┐ ┌─────┴────┐ ┌─────┴────┐       │
│  │ Graph    │ │ CXFC     │ │ Alarm    │ │ Backup   │ │ Plugins  │       │
│  │ Database │ │ Manager  │ │ Manager  │ │ Manager  │ │ Manager  │       │
│  └────┬─────┘ └─────┬────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌────┴──────────────┴─────────────────────────────────────────────┐    │
│  │                  LLM 层                                          │    │
│  │  ModelRouter (main/summary/memory) · LLMClient · SecondaryRouter │    │
│  └──────────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────┤
│              ▼▼ RADIX-Lite 子系统层（v1.2.0 新增）▼▼                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 模块7        │  │ 模块8        │  │ 模块9        │  │ 模块10      │  │
│  │ Template     │  │ Multimodal   │  │ Distillation │  │ Decision    │  │
│  │ Engine       │  │ Pipeline     │  │ Service:8011 │  │ Core        │  │
│  │ (Jinja2 DSL) │  │ (3 worker)  │  │ (7 状态机)   │  │ (6 决策点)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │
├──────────────────────────────────────────────────────────────────────────┤
│                          存储层                                          │
│  SQLite · Weaviate (默认 8090/50061) · Milvus Lite · Chroma · Qdrant     │
│  SQLiteGraphStore · rejected_content 表（30 天保留）                      │
├──────────────────────────────────────────────────────────────────────────┤
│                       控制服务 backend/control_service.py                │
│                  Control Service (独立端口 8765)                         │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.3 服务端口表

| 服务 | 端口 | 说明 |
|------|------|------|
| API 服务（FastAPI） | 8001 | 主服务，Swagger /docs · ReDoc /redoc |
| 前端开发服务器 | 3000 | Vite dev server，代理转发至 8001 |
| 控制服务 | 8765 | 独立进程，管理后端启停 |
| vLLM 主模型 | 8002 | gemma4-e4b 主对话模型 |
| vLLM Embedding | 8101 | Qwen3-Embedding-0.6B 嵌入模型 |
| Weaviate HTTP | 8090 | 向量数据库 HTTP 接口 |
| Weaviate gRPC | 50061 | 向量数据库 gRPC 接口 |
| RADIX-Lite 蒸馏服务 | 8011 | v1.2.0 新增，4 API 端点 |
| ACP 发现 | UDP 9999 / 广播 9998 | Agent 通信协议发现 |

---

## 二、核心组件

### 2.1 记忆管理系统（Memory Manager）

**位置**: `backend/core/memory/manager.py`

**职责**:
- 记忆的 CRUD 操作
- 向量搜索（语义搜索）与混合搜索（向量+关键词）
- 三维评分（重要性、时间、相关性）
- 记忆衰减计算（双阶段指数衰减 + 艾宾浩斯遗忘曲线）
- 记忆召回与重激活
- 批量操作支持
- **决策化写入**（`write_with_decision`，v1.2.0 新增）：依据 6 决策点的 `storage_decision` 结果决定写入 / 拒绝 / 归档，被拒绝内容落入 `rejected_content` 表，保留 30 天

**数据模型**:
```python
class Memory:
    id: int
    type: str  # long_term, short_term, permanent
    content: str
    importance: int  # 1-5
    importance_score: float
    decay_type: str
    reactivation_count: int
    emotion_score: float
    tags: List[str]
    created_at: datetime
```

**存储架构**:
- **SQLite**: 结构化数据存储（memories.db / sessions.db / acp / cxhms.db）
- **向量存储**: Weaviate（默认）/ Milvus Lite / Chroma / Qdrant / Weaviate Embedded

### 2.2 上下文管理系统（Context Manager）

**位置**: `backend/core/context/manager.py`

**职责**: 会话管理、消息历史存储、Mono 上下文（临时上下文）、上下文摘要生成（保留 `max_summaries_in_context = 10` 条）

**特性**: LRU 缓存（100 条上限）、过期自动清理、工作区隔离

### 2.3 工具系统（Tools System）

**位置**: `backend/core/tools/registry.py` · `backend/core/tools/mcp.py`

**职责**: 工具注册与发现、MCP 服务器管理、工具调用执行、OpenAI Functions 兼容

**内置工具**: calculator · datetime · random · json_format
**主模型工具**: write_long_term_memory · search_all_memories · call_assistant · set_alarm · mono · write_permanent_memory · ACP 工具
**记忆管理工具**: 16 个（memory-agent 默认启用）
**摘要工具 / 图工具**: 按需注册

### 2.4 ACP 互联系统（ACP Manager）

**位置**: `backend/core/acp/manager.py`

**职责**: Agent 发现（UDP 广播端口 9998/9999）、连接管理、群组管理、消息传递

**通信协议**: 发现 UDP 广播 · 连接 HTTP/REST · 消息异步队列

### 2.5 LLM 客户端与模型路由（LLM Client + Model Router）

**位置**: `backend/core/llm/client.py` · `backend/core/model_router.py`

**支持的提供商**: OLLAMA · VLLM · OPENAI 兼容 · ANTHROPIC Claude · DEEPSEEK · LOCAL

**模型路由用途**:
- `main`: 主对话模型（vLLM gemma4-e4b @8002，128k 上下文）
- `summary`: 摘要生成模型（默认回退到 main）
- `memory`: 记忆处理模型（默认回退到 main）
- `embedding`: 嵌入模型（vLLM Qwen3-Embedding-0.6B @8101）

**特性**: 同步/流式对话、错误分类处理、请求验证、超时控制、多模态支持（图片输入）、`max_tool_rounds = 10`（流式与非流式统一）

### 2.6 图数据库系统（Graph Database）

**位置**: `backend/core/graph/`（14 个文件）

**职责**: 知识图谱管理、节点/边 CRUD、语义搜索、路径分析、社区检测、PageRank、GraphML/DOT 导出、Neo4j 迁移

**文件列表**: config · database · edges · hybrid_query · migration · models · monitoring · nodes · repository · semantic_query · semantic_search · traversal · vectorizer · visualization

### 2.7 CXFC 插件协议（CXFC Manager）

**位置**: `backend/core/cxfc/`（5 个文件）

**职责**: 插件发现（discovery_port 19876）、技能注册、心跳管理（timeout 60s）、连接管理、事件推送、自动重连

### 2.8 辅助服务

| 组件 | 位置 | 职责 |
|------|------|------|
| Alarm Manager | `backend/core/alarm/` | 定时提醒、闹钟管理、触发回调 |
| Backup Manager | `backend/core/backup/` | 数据备份、选择性恢复、导入导出 |
| Plugin Manager | `backend/core/plugins/` | 插件加载、生命周期管理 |
| WebSocket Manager | `backend/core/websocket/` | WebSocket 连接管理、实时通信、离线消息保存、SSE fallback |
| Session Manager | `backend/core/session/` | 会话存储、会话清理、模型定义 |

### 2.9 API 路由系统

FastAPI 应用包含 17 个路由模块：chat · memory · context · tools · acp · admin · archive · service · agents · backup · websocket · memory_chat · stats · config · vector · graph · cxfc

**聊天流程**:
1. 用户发送消息 → 获取 Agent 配置（系统提示词、模型、温度等）
2. 管理 Agent 专属会话（每个 Agent 一个固定会话）
3. 检索相关记忆（如果启用）
4. 构建消息列表（系统提示词 + 记忆上下文 + 历史消息 + 当前消息）
5. 获取工具列表（根据 Agent 配置过滤）
6. 调用 LLM 生成响应（支持流式，max_tool_rounds=10）
7. 处理工具调用（如有）
8. 保存助手响应到上下文

### 2.10 Agent 系统

**位置**: `backend/api/routers/agents.py`

**职责**: Agent 配置管理（CRUD）、Agent 上下文持久化、Agent 克隆和统计

**默认 Agent**:
- `default`: 默认助手，128k 上下文，支持记忆和工具
- `memory-agent`: 记忆管理助手，128k 上下文，16 个记忆管理工具

**Agent 配置字段（v1.2.0 扩展）**:
```python
class AgentConfig:
    id: str
    name: str
    description: str
    system_prompt: str
    model: str  # main/summary/memory 或具体模型名
    temperature: float
    max_tokens: int
    use_memory: bool
    use_tools: bool
    memory_scene: str  # chat/task/first_interaction
    decay_model: str  # exponential/ebbinghaus
    vision_enabled: bool
    is_default: bool
    # ▼▼ v1.2.0 新增字段 ▼▼
    tools_config: dict          # 工具配置（8 工具方法）
    decision_rubric: dict       # 决策 rubric（4 阈值）
    distillation_enabled: bool  # 蒸馏功能开关
```

### 2.11 控制服务（Control Service）

**位置**: `backend/control_service.py`

**职责**: 独立 FastAPI 服务（端口 8765）、服务管理与监控、配置动态调整、性能指标收集

> **注意**: 控制服务作为独立进程运行，不在主服务 `app.py` 的 lifespan 初始化序列中。它通过独立入口启动，与主服务生命周期解耦。

**API 响应格式**: `APIResponse[T]` 泛型统一响应封装 · `PaginatedResponse[T]` 分页数据封装

**性能中间件**: `PerformanceMiddleware` 自动添加 `X-Process-Time-Ms` 响应头，记录请求处理耗时

---

## 三、RADIX-Lite 架构（v1.2.0 新增）

RADIX-Lite 是 CXHMS v1.2.0 引入的管理 Agent 扩展子系统，由 spec `add-management-agent-radix`（2026-07-16 闭合）定义。方案 C 去除音视频模态，保留 **3 独立子系统 + 7 状态机多轮蒸馏 + Jinja2 DSL 模板 + 6 决策点自主决策**。

### 3.1 三独立子系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                  RADIX-Lite 三独立子系统                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐ │
│  │  模块7           │   │  模块8           │   │  模块9           │ │
│  │  Template Engine │   │  Multimodal     │   │  Distillation    │ │
│  │  (Jinja2 DSL)   │   │  Pipeline       │   │  Service         │ │
│  │                  │   │  (3 worker)     │   │  (端口 8011)     │ │
│  │  - frontmatter   │   │  - OCR worker   │   │  - 7 状态机      │ │
│  │  - CRUD          │   │  - 视觉 worker   │   │  - 4 API 端点    │ │
│  │  - 渲染          │   │  - 文本 worker   │   │  - 多轮蒸馏      │ │
│  └────────┬─────────┘   └────────┬────────┘   └────────┬─────────┘ │
│           │                      │                     │           │
│           └──────────────────────┼─────────────────────┘           │
│                                  ▼                                 │
│           ┌──────────────────────────────────────────┐              │
│           │  模块10 Decision Core（6 决策点）        │              │
│           │  - distill_start                        │              │
│           │  - distill_collect                      │              │
│           │  - distill_advance                      │              │
│           │  - distill_finalize                     │              │
│           │  - storage_decision                     │              │
│           │  - content_merge                        │              │
│           └──────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

**三子系统职责**:

| 子系统 | 位置 | 职责 |
|--------|------|------|
| 模板引擎 | `modules/模块7_模板引擎/` | Jinja2 DSL 模板渲染 + frontmatter 解析 + CRUD |
| 多模态管线 | `modules/模块8_多模态管线/` | 3 worker 预处理（OCR / 视觉 / 文本）+ 模态融合 + 降级开关 |
| 蒸馏服务 | `modules/模块9_蒸馏服务/` | 7 状态机多轮蒸馏 + 4 API 端点（端口 8011） |
| 管理Agent扩展 | `modules/模块10_管理Agent扩展/` | 6 决策点自主决策 + 8 工具方法 + rubric 驱动 |

### 3.2 七状态机多轮蒸馏架构

蒸馏服务采用 7 状态机驱动多轮蒸馏流程，状态单向推进，终态 `finalized` 不可回退。

```
┌─────────┐     ┌────────────┐     ┌────────────┐     ┌──────────┐     ┌───────────┐     ┌────────────┐     ┌───────────┐
│  draft  │ ──▶ │ collecting │ ──▶ │ distilling │ ──▶ │ refining │ ──▶ │ reviewing │ ──▶ │ finalizing │ ──▶ │ finalized │
│ (草稿)  │     │ (收集)     │     │ (蒸馏)     │     │ (精炼)   │     │ (审查)    │     │ (定稿)     │     │ (终态)    │
└─────────┘     └────────────┘     └────────────┘     └──────────┘     └───────────┘     └────────────┘     └───────────┘
     │                │                  │                 │                │                 │
     │                │                  │                 │                │                 │
     ▼                ▼                  ▼                 ▼                ▼                 ▼
  蒸馏启动         收集输入           蒸馏处理           精炼输出          审查结果          写入存储
  distill_start   distill_collect    distill_advance   distill_advance  distill_advance  distill_finalize
```

**状态说明**:

| 状态 | 中文名 | 触发决策点 | 说明 |
|------|--------|-----------|------|
| draft | 草稿 | distill_start | 蒸馏会话初始状态，等待启动 |
| collecting | 收集 | distill_collect | 收集多模态输入与历史上下文 |
| distilling | 蒸馏 | distill_advance | LLM 多轮蒸馏处理 |
| refining | 精炼 | distill_advance | 精炼输出内容 |
| reviewing | 审查 | distill_advance | 审查蒸馏结果质量 |
| finalizing | 定稿 | distill_finalize | 准备最终产出 |
| finalized | 终态 | — | 蒸馏完成，不可回退 |

**蒸馏会话契约**: `distillation_session.schema.json`（7 状态 + turns 数组 + final_decision）

### 3.3 六决策点架构

管理 Agent 扩展通过 6 个决策点实现自主决策，每个决策点由 `_llm_decide` 驱动并写入 `_write_audit_log`。

```
┌─────────────────────────────────────────────────────────────────────┐
│                    6 决策点架构（Decision Core）                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ distill_start   │  │ distill_collect │  │ distill_advance │     │
│  │ 蒸馏启动决策     │  │ 收集策略决策     │  │ 推进策略决策     │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ distill_finalize│  │ storage_decision│  │ content_merge   │     │
│  │ 定稿决策        │  │ 存储位置决策     │  │ 内容合并决策     │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│                                                                     │
│  统一流程:                                                            │
│    _load_rubric → 决策输入 → _llm_decide → 决策输出 → _write_audit_log │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**决策点说明**:

| 决策点 | 职责 | 输出 |
|--------|------|------|
| distill_start | 判断是否启动蒸馏会话 | 启动 / 暂缓 |
| distill_collect | 决定收集哪些输入 | 输入选择策略 |
| distill_advance | 决定状态机推进路径 | 下一状态 |
| distill_finalize | 决定是否定稿 | 定稿 / 回退 |
| storage_decision | 决定存储位置（3 location 枚举） | memory / archive / rejected |
| content_merge | 决定内容合并策略 | 合并 / 替换 / 跳过 |

**决策审计日志契约**: `distillation_log.schema.json`（6 决策点 + llm_reasoning + final_decision）

**决策 rubric**: 4 阈值（quality_threshold / dedup_threshold / importance_threshold / merge_threshold）

### 3.4 write_with_decision 决策化写入架构

v1.2.0 在 Memory Manager 新增 `write_with_decision` 方法，实现决策化写入。被拒绝内容落入 `rejected_content` 表，保留 30 天。

```
┌─────────────────────────────────────────────────────────────────────┐
│              write_with_decision 决策化写入架构                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   写入请求                                                           │
│      │                                                              │
│      ▼                                                              │
│   ┌──────────────────────┐                                          │
│   │ storage_decision     │ ◀── Decision Core（6 决策点之一）        │
│   │ 决策点判断            │      rubric_snapshot + quality_score     │
│   └──────────┬───────────┘                                          │
│              │                                                      │
│      ┌───────┼───────┐                                              │
│      ▼       ▼       ▼                                              │
│   ┌──────┐ ┌──────┐ ┌──────────────┐                                │
│   │memory│ │archive│ │ rejected     │                                │
│   │写入  │ │归档   │ │ rejected_    │                                │
│   └──────┘ └──────┘ │ content 表   │                                │
│                     │ (保留 30 天) │                                │
│                     └──────┬───────┘                                │
│                            │                                         │
│                            ▼                                         │
│                     ┌──────────────┐                                  │
│                     │ cleanup_     │                                  │
│                     │ expired_     │  清理过期拒绝内容                 │
│                     │ rejected_    │                                  │
│                     │ content      │                                  │
│                     └──────────────┘                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**WriteWithDecisionResult 结构**:
- `accepted`: bool（是否接受写入）
- `location`: str（memory / archive / rejected）
- `quality_score`: float（质量评分）
- `rubric_snapshot`: dict（决策时的 rubric 快照）
- `memory_id`: Optional[int]（写入成功时返回记忆 ID）

**API 端点**:
- `POST /api/memories/write-with-decision`：决策化写入
- `GET /api/memories/rejected-content`：获取拒绝写入内容（30 天保留）
- `DELETE /api/memories/rejected-content/cleanup-expired`：清理过期拒绝内容

**契约**: `memory_manager_v2.pyi`（3 方法）· `storage_decision.schema.json`（3 location 枚举 + rubric_snapshot + quality_score）

### 3.5 三 worker 多模态管线架构

多模态管线由 3 个 worker 组成，分别处理 OCR、视觉、文本三种模态，支持模态融合与降级开关。

```
┌─────────────────────────────────────────────────────────────────────┐
│                  多模态管线（3 worker 架构）                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   输入（图片 / 文本 / 附件）                                          │
│      │                                                              │
│      ├───────────────────┬───────────────────┐                      │
│      ▼                   ▼                   ▼                      │
│   ┌──────────┐      ┌──────────┐      ┌──────────┐                  │
│   │ OCR      │      │ 视觉     │      │ 文本     │                  │
│   │ worker   │      │ worker   │      │ worker   │                  │
│   │          │      │          │      │          │                  │
│   │ 图片→文本 │      │ 图片理解 │      │ 文本处理 │                  │
│   └────┬─────┘      └────┬─────┘      └────┬─────┘                  │
│        │                 │                 │                        │
│        └─────────────────┼─────────────────┘                        │
│                          ▼                                          │
│                   ┌──────────────┐                                   │
│                   │ _merge_      │  模态融合                        │
│                   │ ocr_vision   │                                   │
│                   └──────┬───────┘                                   │
│                          │                                          │
│                          ▼                                          │
│                   ┌──────────────┐                                   │
│                   │ Multimodal   │  产出契约                         │
│                   │ Artifact     │  (3 模态 type 枚举 +               │
│                   │              │   confidence + vision_degraded)  │
│                   └──────────────┘                                   │
│                                                                     │
│   降级开关: vision_degraded（视觉模型不可用时降级为纯 OCR + 文本）      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Worker 职责**:

| Worker | 职责 | 输入 | 输出 |
|--------|------|------|------|
| OCR worker | 图片转文本 | 图片 | 文本 |
| 视觉 worker | 图片理解 | 图片 | 描述 + confidence |
| 文本 worker | 文本处理 | 文本 | 结构化文本 |

**模态融合**: `_merge_ocr_vision` 方法融合 OCR 与视觉结果

**产出契约**: `multimodal_artifact.schema.json`（3 模态 type 枚举 + confidence + vision_degraded）

**接口契约**: `multimodal_pipeline.pyi`（7 方法：preprocess + 3 worker + _merge_ocr_vision）

### 3.6 Jinja2 DSL 模板引擎架构

模板引擎基于 Jinja2 DSL，支持 frontmatter 解析、CRUD 操作与模板渲染。

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Jinja2 DSL 模板引擎架构                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   模板输入                                                           │
│   ┌────────────────────────────────────────┐                         │
│   │ ---                                     │                        │
│   │ template_id: xxx                        │  frontmatter 段        │
│   │ version: 1.0.0                          │  (YAML 元数据)         │
│   │ variables:                              │                        │
│   │   - name: user_input                    │                        │
│   │     type: string                        │                        │
│   │ ---                                     │                        │
│   │ Hello {{ user_input }}!                │  body 段               │
│   └────────────────────────────────────────┘  (Jinja2 DSL 模板)      │
│      │                                                              │
│      ▼                                                              │
│   ┌──────────────┐                                                  │
│   │ _parse_      │  frontmatter 解析                               │
│   │ frontmatter  │                                                  │
│   └──────┬───────┘                                                  │
│          │                                                          │
│          ▼                                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐         │
│   │ create       │    │ read         │    │ update       │  CRUD   │
│   │ template     │    │ template     │    │ template     │         │
│   └──────────────┘    └──────────────┘    └──────────────┘         │
│          │                                                          │
│          ▼                                                          │
│   ┌──────────────┐                                                  │
│   │ render_      │  模板渲染（Jinja2 DSL → 最终文本）                 │
│   │ template     │                                                  │
│   └──────────────┘                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**模板仓库契约**: `template_registry.schema.json`（frontmatter + body + CRUD 元数据）

**接口契约**: `template_engine.pyi`（7 方法：render_template + CRUD + _parse_frontmatter）

**配置契约**: `radix_config.json`（5 段：distillation_service / multimodal_pipeline / template_engine / decision_core / vllm）

---

## 四、应用初始化流程

主程序 `main.py` 加载配置、初始化日志、启动 Uvicorn，FastAPI 应用使用 lifespan 上下文管理器处理启停。

### 4.1 主服务初始化顺序（18 步）

`backend/api/app.py` 的 lifespan 初始化序列：

1. **ModelRouter** — 模型路由器（最先初始化，其他组件可能依赖它）
2. **MemoryManager** — 记忆管理器
3. **ContextManager** — 上下文管理器
4. **ACPManager** — ACP 管理器（含 start()）
5. **LLMClient** — LLM 客户端（优先从 model_router 获取主模型客户端，回退到 LLMFactory）
6. **SecondaryModelRouter** — 副模型路由器
7. **MCPManager** — MCP 管理器
8. **内置工具注册** — register_builtin_tools()
9. **主模型工具注册** — register_master_tools()
10. **摘要模型工具注册** — register_summary_tools()
11. **记忆管理模型工具注册** — register_assistant_tools()
12. **向量搜索启用** — 根据 vector_backend 配置初始化（chroma/milvus_lite/qdrant/weaviate/weaviate_embedded，默认 weaviate）
13. **AlarmManager + WebSocket 离线保存**
14. **AsyncMemoryManager** — 异步记忆管理器
15. **GraphDatabase + SQLiteGraphStore** — 图数据库 + SQLite 图存储（条件启用：`graph.enabled = true`）
16. **CXFCManager** — CXFC 管理器（条件启用：`cxfc.enabled = true`，含 start()）
17. **图数据库工具注册** — register_graph_tools()（条件注册：graph_database && graph_store）
18. **ServiceState** — 注入所有组件

### 4.2 RADIX-Lite 子系统初始化（v1.2.0 新增）

在主服务初始化完成后，RADIX-Lite 子系统按以下顺序初始化（由配置 `radix_config.json` 驱动）：

1. **模板引擎初始化** — 加载 Jinja2 DSL 模板仓库，解析 frontmatter
2. **多模态管线初始化** — 启动 3 worker（OCR / 视觉 / 文本），加载降级开关配置
3. **蒸馏服务初始化** — 启动端口 8011 的 FastAPI 子服务，初始化 7 状态机
4. **决策核心初始化** — 加载 6 决策点 rubric，初始化审计日志
5. **write_with_decision 钩子注册** — 在 MemoryManager 注册决策化写入方法，初始化 `rejected_content` 表（30 天保留）

> **降级策略**: 模块间通过 try-except fallback 到 Mock（rules-0 §三），不硬依赖真实实现。RADIX-Lite 子系统不可用时自动降级到预生成 Mock（`public/pre_generated_mock/`，12 份）。

### 4.3 关闭顺序

CXFCManager → GraphDatabase → AlarmManager → WebSocketManager(stop_cleanup_task) → ACPManager(stop) → MemoryManager → BackupManager → PluginManager → ModelRouter

> **注意**：控制服务（Control Service，端口 8765）独立于 FastAPI lifespan 运行，不在上述初始化序列中。RADIX-Lite 蒸馏服务（端口 8011）随主服务 lifespan 关闭。

---

## 五、数据流

### 5.1 记忆写入流程（含决策化写入）

```
1. 用户请求 → API Router
2. 验证请求参数
3. 调用 write_with_decision
   ├─ storage_decision 决策点判断
   ├─ 依据 rubric_snapshot + quality_score
   └─ 输出: memory / archive / rejected
4. 分支处理:
   ├─ memory  → SQLite 写入 + 向量存储更新
   ├─ archive → 归档存储
   └─ rejected → rejected_content 表（保留 30 天）
5. 返回 WriteWithDecisionResult
```

### 5.2 记忆搜索流程

```
1. 用户查询 → API Router
2. 混合搜索（如果启用）
   - 向量搜索（语义相似度，余弦）
   - 关键词搜索（SQLite LIKE / BM25）
   - 结果融合排序（RRF: 0.6*vector + 0.4*text）
3. 三维评分计算（场景感知）
   - chat: 0.45/0.20/0.35
   - task: 0.30/0.20/0.50
   - creative: 0.30/0.40/0.30
4. 过滤低分记忆（阈值 0.3）
5. 返回 Top-K
```

### 5.3 RADIX-Lite 蒸馏流程

```
1. 蒸馏启动 → distill_start 决策
2. 状态: draft → collecting
3. 收集输入 → distill_collect 决策
   ├─ 多模态管线预处理（3 worker）
   ├─ 模态融合 (_merge_ocr_vision)
   └─ 模板渲染（Jinja2 DSL）
4. 状态: collecting → distilling
5. LLM 多轮蒸馏 → distill_advance 决策
6. 状态: distilling → refining → reviewing
7. 审查质量 → distill_advance 决策
8. 状态: reviewing → finalizing
9. 定稿决策 → distill_finalize
10. 状态: finalizing → finalized（终态）
11. 存储决策 → storage_decision
    ├─ memory（写入记忆）
    ├─ archive（归档）
    └─ rejected（拒绝，保留 30 天）
12. 内容合并 → content_merge 决策
13. 审计日志写入 _write_audit_log
```

### 5.4 工具调用流程

```
1. 用户请求 → API Router
2. ToolRegistry.get_tool()
3. 执行工具函数
4. 返回执行结果

MCP 工具调用:
1. 用户请求 → API Router
2. MCPManager.call_tool()
3. HTTP POST 到 MCP 服务器
4. 返回执行结果
```

---

## 六、配置系统

### 6.1 配置真相源

**配置文件**: `config/default.yaml`（唯一真相源）

**CXHMSConfig 数据类层级**:
```
CXHMSConfig
  ├── server: ServerConfig (host/port/debug)
  ├── llm: LLMConfig (max_tool_rounds/temperature/max_tokens)
  ├── models: ModelsConfig (main/summary/memory/embedding)
  ├── model_defaults: ModelDefaults (summary: main / memory: main)
  ├── vector: VectorConfig
  ├── acp: ACPConfig (discovery/connection/group)
  ├── database: DatabaseConfig
  ├── memory: MemoryConfig
  ├── context: ContextConfig (max_summaries_in_context: 10)
  ├── rate_limit: RateLimitConfig
  ├── cors: CORSConfig
  ├── system: SystemConfig
  ├── graph: GraphConfigSection (enabled: true / weaviate.grpc_port: 50061)
  └── cxfc: CXFCConfig (enabled: true)
```

> **RADIX-Lite 子系统配置**: 见 `public/config_template/radix_config.json`（5 段：distillation_service / multimodal_pipeline / template_engine / decision_core / vllm）

### 6.2 关键配置值（对齐 default.yaml）

```yaml
server:
  host: 0.0.0.0
  port: 8001
  debug: true

llm:
  max_tool_rounds: 10
  temperature: 1.5
  max_tokens: 4096

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
  enabled: true
  max_memories: 10000
  default_importance: 3
  decay_enabled: true
  decay_rate: 0.1
  decay_interval_days: 7
  reactivation_boost: 0.2
  emotion_enabled: true
  vector_enabled: true
  vector_backend: weaviate
  decay_model: exponential
  hybrid_search_enabled: false
  archive_enabled: true
  dedup_threshold: 0.85
  archive_compression_enabled: true
  weaviate:
    host: localhost
    port: 8090
    grpc_port: 50061
    embedded: false
    vector_size: 768
    schema_class: CXHMSMemory

context:
  enabled: true
  max_context_length: 4000
  context_window: 10
  include_memories: true
  max_memories_in_context: 5
  max_summaries_in_context: 10

cxfc:
  enabled: true
  discovery_port: 19876
  discovery_enabled: true
  heartbeat_timeout: 60
  auto_reconnect: true

graph:
  enabled: true
  db_path: data/graph.db
  auto_create_schema: true
  pool_size: 10
  timeout: 30
  vector_size: 768
  weaviate:
    url: http://localhost:8090
    grpc_port: 50061
    vector_dim: 768
    batch_size: 100
    ef_construction: 128
    max_connections: 16

acp:
  enabled: true
  discovery_port: 9999
  broadcast_port: 9998
  broadcast_address: 255.255.255.255
  discovery_interval: 10
```

### 6.3 配置加载与验证

**加载机制**: `config/settings.py`
- 单例模式
- YAML 解析
- 环境变量支持（CXHMS_ 前缀）
- 验证（`config/validation.py`）
- 自动修复（`config/repair.py`）
- 热重载

> **注意**: `default.yaml` 中的 `llm_params`、`agent`、`security`、`monitoring`、`tools` 等配置节未被 `CXHMSConfig` 加载，属于配置孤儿（仅存在于 YAML 文件中，不会被代码消费）。

> **端口真相源**: 以 `config/default.yaml` 为唯一真相源，`server.port` 为 **8001**。`SystemConfig` 数据类默认值 (8000) 与 `.env.example` (8000) 为历史遗留。

---

## 七、错误处理

### 7.1 错误分类

1. **LLMError**: LLM 调用错误
   - LLMConnectionError: 连接错误
   - LLMTimeoutError: 超时错误
   - LLMRateLimitError: 速率限制
2. **MCPError**: MCP 服务器错误
   - MCPConnectionError: 连接错误
   - MCPTimeoutError: 超时错误
3. **MemoryError**: 记忆操作错误
4. **ContextError**: 上下文操作错误

### 7.2 错误响应格式

系统使用 `APIResponse[T]` 泛型封装统一响应，分页数据使用 `PaginatedResponse[T]` 封装。

```json
{
  "status": "error",
  "error": "错误描述",
  "error_details": {
    "status_code": 500,
    "exception": "详细异常信息"
  }
}
```

---

## 八、性能优化

### 8.1 连接池
- SQLite 连接池
- HTTP 客户端复用
- 向量存储连接复用

### 8.2 缓存策略
- LRU 缓存（上下文，100 条上限）
- 向量索引缓存
- 工具定义缓存

### 8.3 异步处理
- 所有 IO 操作使用 async/await
- 批量操作并发执行
- 后台任务（衰减计算）

### 8.4 性能中间件
- PerformanceMiddleware：自动添加 `X-Process-Time-Ms` 响应头
- 请求耗时追踪与记录

---

## 九、安全考虑

### 9.1 输入验证
- 请求体验证（Pydantic v2）
- SQL 注入防护（参数化查询）
- XSS 防护（输出转义）

### 9.2 访问控制
- CORS 配置（`origins: ['*']`）
- API 密钥（可选，默认禁用）
- 速率限制（默认禁用）

### 9.3 数据安全
- 敏感信息不记录日志
- 配置文件权限控制
- 数据库文件权限

---

## 十、部署架构

### 10.1 单节点部署

```
┌─────────────────────────────────────────────┐
│           Docker Container                  │
│  ┌───────────────────────────────────────┐  │
│  │         CXHMS Service                 │  │
│  │  - FastAPI (port 8001)                │  │
│  │  - Frontend (port 3000)               │  │
│  │  - Control (port 8765)                │  │
│  │  - RADIX-Lite Distillation (port 8011)│  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │      SQLite Database                  │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │  Weaviate (HTTP 8090 / gRPC 50061)    │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │    vLLM 主模型 (port 8002)            │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │    vLLM Embedding (port 8101)         │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 10.2 多节点部署（生产环境）

```
┌─────────────────────────────────────────────────────┐
│                  Load Balancer                      │
└──────────────────┬──────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
┌───▼───┐    ┌────▼────┐   ┌─────▼────┐
│ CXHMS │    │  CXHMS  │   │  CXHMS   │
│Node 1 │    │ Node 2  │   │  Node 3  │
└───┬───┘    └────┬────┘   └─────┬────┘
    │             │              │
    └─────────────┼──────────────┘
                  │
        ┌─────────▼──────────┐
        │   Shared Storage   │
        │  - PostgreSQL      │
        │  - Qdrant Cluster  │
        │  - Weaviate Cluster│
        └────────────────────┘
```

---

## 十一、扩展性设计

### 11.1 插件系统
- CXFC 插件协议（发现、注册、心跳）
- 工具插件（MCP 协议）
- 存储后端插件（多向量后端支持）
- LLM 提供商插件

### 11.2 水平扩展
- 无状态设计
- 共享存储
- 负载均衡

### 11.3 垂直扩展
- 异步处理
- 连接池
- 缓存优化

---

## 十二、监控与日志

### 12.1 日志级别
- DEBUG: 详细调试信息
- INFO: 正常操作信息
- WARNING: 警告信息
- ERROR: 错误信息

### 12.2 监控指标
- 请求 QPS
- 响应延迟
- 错误率
- 资源使用率

### 12.3 健康检查
- `/health` - 基础健康检查
- `/api/admin/health` - 详细组件状态
- `/api/vector/health` - 向量存储健康检查

---

## 十三、契约版本

### 13.1 三层契约版本

当前三层契约版本：**v1.2.0**（2026-07-16）

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0.0 | 2026-07-02 | 初始 5 schema + 5 .pyi + 3 config |
| v1.0.1 | 2026-07-04 | 接口契约补全 + graph schema 新增 |
| v1.0.2 | 2026-07-04 | jsonschema 严格化 |
| v1.1.0 | 2026-07-14 | AnythingLLM 兼容层（2 schema + 1 .pyi）|
| v1.2.0 | 2026-07-16 | RADIX-Lite 4 新模块契约（6 schema + 6 .pyi + 1 config + 6 Mock）|

### 13.2 v1.2.0 契约清单

| 类型 | 数量 | 位置 |
|------|------|------|
| 数据契约（JSON Schema draft-07+） | 13 份 | `public/schema/` |
| 接口契约（.pyi 存根） | 13 份 | `public/interface_stub/` |
| 配置契约（JSON Schema） | 5 份 | `public/config_template/` |
| 预生成 Mock | 12 份 | `public/pre_generated_mock/` |

**v1.2.0 新增契约**:
- 数据契约（6 份）: distillation_session · multimodal_artifact · template_registry · storage_decision · distillation_log · agent_config_v2
- 接口契约（6 份）: distillation_service · template_engine · multimodal_pipeline · decision_core · memory_manager_v2 · agent_tools_v2
- 配置契约（1 份）: radix_config.json（5 段）
- 预生成 Mock（6 份）

详见 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md)。

---

## 十四、测试统计

| 套件 | 数量 | 位置 |
|------|------|------|
| 后端单元测试 | 753 passed | `tests/units/` + `tests/simulation/` |
| RADIX-Lite 单元测试 | 262 passed | `tests/contract/` |
| 接口契约测试 | 437 passed | `tests/contracts/` |
| E2E 测试 | 37 passed | `tests/e2e/` |
| 前端单元测试 | 19 文件 / 299 项 | `frontend/src/` |
| Playwright E2E | 2 文件 | `frontend/e2e/` |
| **合计** | **1489 passed** | — |

**测试执行**:
```bash
# 后端单元测试
python -m pytest tests/ -v

# RADIX-Lite 单元测试
python -m pytest tests/contract/ -v

# 契约测试
python -m pytest public/test_cases/ -v

# E2E 测试（依赖真实 vLLM）
python -m pytest tests/e2e/ -v
```

---

## 附录

### 附录 A：全局依赖注入

系统通过 `ServiceState` 类和 `backend/dependencies.py` 提供以下依赖注入函数：

| 依赖函数 | 说明 |
|---------|------|
| get_memory_manager() | 记忆管理器 |
| get_async_memory_manager() | 异步记忆管理器 |
| get_context_manager() | 上下文管理器 |
| get_acp_manager() | ACP 管理器 |
| get_llm_client() | LLM 客户端 |
| get_secondary_router() | 副模型路由器 |
| get_mcp_manager() | MCP 管理器 |
| get_model_router() | 模型路由器 |
| get_graph_database() | 图数据库 |
| get_graph_store() | 图存储 |
| get_cxfc_manager() | CXFC 管理器（可选，返回 Optional） |

**ServiceState 属性**: `memory_manager` · `async_memory_manager` · `context_manager` · `acp_manager` · `llm_client` · `secondary_router` · `mcp_manager` · `model_router` · `graph_database`（可选）· `graph_store`（可选）· `cxfc_manager`（可选）

### 附录 B：核心业务流程图

#### B.1 消息处理完整流程

用户发送消息 → 获取 Agent 配置（系统提示词、模型、温度等）→ 会话管理（有 session_id 则获取已有会话，否则创建新会话）→ 添加用户消息到上下文 → 记忆检索（MemoryRouter.route 按场景路由 → HybridSearch 向量+关键词 → DecayCalculator 计算时间衰减 → 综合评分排序）→ 构建消息列表 [System 提示词 + 相关记忆 + 历史消息 + 当前消息] → 调用 LLM（选择模型 main/summary/memory，传递工具定义，max_tool_rounds=10）→ 普通响应（保存到上下文、返回用户）或 工具调用请求（执行工具、收集结果）→ 可选保存重要内容到记忆（write_with_decision 决策化写入）→ 返回响应。

#### B.2 记忆检索评分流程

检索请求 → 生成查询向量（LLMClient.get_embedding）→ 并行执行向量搜索（余弦相似度）与关键词搜索（BM25/TF-IDF）→ 分数融合（RRF: `score = 0.6*vector_rank + 0.4*text_rank`）→ 3D 评分（场景感知：`final = importance_w*importance + time_w*time + relevance_w*relevance`；chat=0.45/0.20/0.35，task=0.30/0.20/0.50，creative=0.30/0.40/0.30）→ 过滤低分记忆（阈值 0.3）→ 返回 Top-K。

#### B.3 ACP 消息流程

Agent A 发送消息 → 消息序列化（ACPMessageInfo → JSON，添加时间戳、相关性 ID）→ 路由选择（直接消息 / 广播 / 群组消息）→ HTTP POST `http://target:port/acp/receive` → Agent B 接收并验证格式、查找消息处理器 → 消息处理（chat / memory_request / tool_call）→ 发送响应（如需要）。

> 配置系统详情见本文档「六、配置系统」章节；LLM 提供商支持 OLLAMA/VLLM/OPENAI/ANTHROPIC/DEEPSEEK/LOCAL，当前默认主模型为 VLLM (`gemma4-e4b` @8002)，嵌入模型为 vLLM `Qwen3-Embedding-0.6B` @8101。

### 附录 C：术语表

- **RAG**: Retrieval-Augmented Generation，检索增强生成
- **MCP**: Model Context Protocol，模型上下文协议
- **ACP**: Agent Communication Protocol，代理通信协议
- **CXFC**: CXHMS Function Call Protocol，CXHMS 函数调用协议
- **LLM**: Large Language Model，大语言模型
- **RADIX-Lite**: 管理 Agent 扩展子系统（模板引擎 / 多模态管线 / 蒸馏服务 / 决策核心）
- **DSL**: Domain-Specific Language，领域特定语言
- **CRUD**: Create / Read / Update / Delete

### 附录 D：参考文档

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [Jinja2 文档](https://jinja.palletsprojects.com/)
- [Weaviate 文档](https://weaviate.io/developers/weaviate)
- [契约变更日志](../public/schema/CHANGELOG.md)
- [项目概述](PROJECT_OVERVIEW.md)
- [模块详解](MODULES.md)
- [API 文档](API.md)
- [部署指南](DEPLOYMENT.md)
- [技术文档](TECHNICAL.md)

---

*文档版本: v3.0.0*
*最后更新: 2026-07-17*
