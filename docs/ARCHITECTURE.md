# CXHMS 架构文档

## 系统概述

CXHMS (CX-O History & Memory Service) 是一个AI代理中间层服务，提供记忆管理、工具调用、ACP互联等核心功能。

## 架构设计

### 整体架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            CXHMS 服务层                                   │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   API    │  │  WebUI   │  │  Memory  │  │  Tools   │  │WebSocket │  │
│  │  Layer   │  │  Layer   │  │  Layer   │  │  Layer   │  │  Layer   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │             │             │             │          │
│  ┌────▼─────────────▼─────────────▼─────────────▼─────────────▼────┐    │
│  │                      Core Services Layer                        │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │    │
│  │  │ Memory  │ │ Context │ │  Tools  │ │   ACP   │ │ Session │  │    │
│  │  │ Manager │ │ Manager │ │Registry │ │ Manager │ │ Manager │  │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘  │    │
│  │  ┌────┴────┐ ┌────┴────┐ ┌────┴────┐ ┌────┴────┐ ┌────┴────┐  │    │
│  │  │  Graph  │ │  CXFC   │ │  Alarm  │ │ Backup  │ │ Plugins │  │    │
│  │  │Database │ │ Manager │ │ Manager │ │ Manager │ │ Manager │  │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘  │    │
│  └───────┼───────────┼───────────┼───────────┼───────────┼────────┘    │
│          │           │           │           │           │              │
│  ┌───────▼───────────▼───────────▼───────────▼───────────▼────────┐    │
│  │                        Storage Layer                           │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐  │    │
│  │  │ SQLite  │ │ Milvus  │ │ Chroma  │ │ Qdrant  │ │Weaviate│  │    │
│  │  │ (Local) │ │  (Lite) │ │(Win兼容)│ │(Server) │ │(Embed) │  │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └────────┘  │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                    Control Service (port 8765)                  │    │
│  └────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. 记忆管理系统 (Memory Manager)

**位置**: `backend/core/memory/manager.py`

**职责**:
- 记忆的CRUD操作
- 向量搜索（语义搜索）
- 混合搜索（向量+关键词）
- 三维评分（重要性、时间、相关性）
- 记忆衰减计算
- 记忆召回与重激活
- 批量操作支持

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
- **SQLite**: 结构化数据存储
- **向量存储**: Milvus Lite / Chroma / Qdrant / Weaviate（可选）

### 2. 上下文管理系统 (Context Manager)

**位置**: `backend/core/context/manager.py`

**职责**:
- 会话管理
- 消息历史存储
- Mono上下文（临时上下文）
- 上下文摘要生成

**特性**:
- LRU缓存（100条上限）
- 过期自动清理
- 工作区隔离

### 3. 工具系统 (Tools System)

**位置**: 
- `backend/core/tools/registry.py`
- `backend/core/tools/mcp.py`

**职责**:
- 工具注册与发现
- MCP服务器管理
- 工具调用执行
- OpenAI Functions兼容

**MCP服务器管理**:
- 进程生命周期管理
- HTTP端点通信
- 工具自动同步
- 健康检查

### 4. ACP互联系统 (ACP Manager)

**位置**: `backend/core/acp/manager.py`

**职责**:
- Agent发现（UDP广播）
- 连接管理
- 群组管理
- 消息传递

**通信协议**:
- **发现**: UDP广播（端口9998/9999）
- **连接**: HTTP/REST API
- **消息**: 异步消息队列

### 5. LLM客户端 (LLM Client)

**位置**: `backend/core/llm/client.py`

**支持的提供商**:
- Ollama（本地）
- VLLM（高性能）
- OpenAI 兼容接口
- Anthropic Claude

**特性**:
- 同步/流式对话
- 错误分类处理
- 请求验证
- 超时控制
- 多模态支持（图片输入）

### 6. 模型路由器 (Model Router)

**位置**: `backend/core/model_router.py`

**职责**:
- 管理多个LLM模型客户端
- 按用途路由请求（main/summary/memory）
- 模型配置热加载
- 健康检查和故障转移

**预配置模型用途**:
- `main`: 主对话模型（128k上下文）
- `summary`: 摘要生成模型
- `memory`: 记忆处理模型

### 7. 图数据库系统 (Graph Database)

**位置**: `backend/core/graph/`

**职责**:
- 知识图谱管理
- 节点/边CRUD操作
- 语义搜索
- 路径分析
- 社区检测
- PageRank算法

**文件列表** (15个):
- `config.py`: 图数据库配置
- `database.py`: 数据库连接管理
- `edges.py`: 边操作
- `hybrid_query.py`: 混合查询
- `migration.py`: 数据迁移
- `models.py`: 数据模型
- `monitoring.py`: 监控
- `nodes.py`: 节点操作
- `repository.py`: 数据仓库
- `semantic_query.py`: 语义查询
- `semantic_search.py`: 语义搜索
- `traversal.py`: 图遍历
- `vectorizer.py`: 向量化
- `visualization.py`: 可视化

### 8. CXFC 插件协议 (CXFC Manager)

**位置**: `backend/core/cxfc/`

**职责**:
- 插件发现
- 技能注册
- 心跳管理
- 连接管理

**文件列表** (6个):
- `discovery.py`: 插件发现
- `manager.py`: 管理器
- `models.py`: 数据模型
- `skill_registry.py`: 技能注册表
- `storage.py`: 存储

### 9. 提醒管理系统 (Alarm Manager)

**位置**: `backend/core/alarm/`

**职责**:
- 定时提醒
- 闹钟管理
- 触发回调

### 10. 备份管理系统 (Backup Manager)

**位置**: `backend/core/backup/`

**职责**:
- 数据备份
- 数据恢复

### 11. 插件管理系统 (Plugin Manager)

**位置**: `backend/core/plugins/`

**职责**:
- 插件加载
- 生命周期管理

### 12. WebSocket 管理

**位置**: `backend/core/websocket/`

**职责**:
- WebSocket连接管理
- 实时通信
- 离线消息保存

### 13. 会话管理系统 (Session Manager)

**位置**: `backend/core/session/`

**职责**:
- 会话存储
- 会话清理
- 模型定义

### 14. API 路由系统

FastAPI 应用包含17个路由模块：
- `chat.py`: 处理聊天对话请求（支持Agent和多模态）
- `memory.py`: 处理记忆 CRUD 操作
- `context.py`: 处理会话和消息管理
- `tools.py`: 处理工具注册和调用
- `acp.py`: 处理 ACP 协议
- `admin.py`: 处理管理员操作
- `archive.py`: 处理归档管理
- `service.py`: 处理服务管理
- `agents.py`: 处理 Agent 配置和上下文管理
- `backup.py`: 处理备份恢复
- `websocket.py`: 处理 WebSocket 连接
- `memory_chat.py`: 处理记忆聊天
- `stats.py`: 处理统计信息
- `config.py`: 处理配置管理
- `vector.py`: 处理向量搜索
- `graph.py`: 处理图数据库操作
- `cxfc.py`: 处理 CXFC 插件协议

**聊天流程**:
1. 用户发送消息后，系统获取 Agent 配置
2. 管理 Agent 专属会话（每个 Agent 一个固定会话）
3. 检索相关记忆（如果启用）
4. 构建消息列表（系统提示词 + 记忆上下文 + 历史消息 + 当前消息）
5. 获取工具列表（根据 Agent 配置过滤）
6. 调用 LLM 生成响应（支持流式）
7. 处理工具调用（如有）
8. 保存助手响应到上下文

### 15. Agent 系统

**位置**: `backend/api/routers/agents.py`

**职责**:
- Agent 配置管理（CRUD）
- Agent 上下文持久化
- Agent 克隆和统计

**默认 Agent**:
- `default`: 默认助手，128k上下文，支持记忆和工具
- `memory-agent`: 记忆管理助手，128k上下文，16个记忆管理工具

**Agent 配置字段**:
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
```

## 数据流

### 记忆写入流程

```
1. 用户请求 → API Router
2. 验证请求参数
3. MemoryManager.write_memory()
4. SQLite写入
5. 向量存储更新（如果启用）
6. 返回记忆ID
```

### 记忆搜索流程

```
1. 用户查询 → API Router
2. 混合搜索（如果启用向量）
   - 向量搜索（语义相似度）
   - 关键词搜索（SQLite LIKE）
   - 结果融合排序
3. 三维评分计算
4. 返回排序后的结果
```

### 工具调用流程

```
1. 用户请求 → API Router
2. ToolRegistry.get_tool()
3. 执行工具函数
4. 返回执行结果

MCP工具调用:
1. 用户请求 → API Router
2. MCPManager.call_tool()
3. HTTP POST到MCP服务器
4. 返回执行结果
```

## 配置系统

**配置文件**: `config/default.yaml`

**配置结构**:
```yaml
server:        # 服务器配置
  host: "0.0.0.0"
  port: 8000

llm:           # LLM配置
  provider: "ollama"
  host: "http://localhost:11434"
  model: "qwen3-vl:8b"

models:        # 模型槽位配置
  main: "qwen3-vl:8b"
  summary: "qwen3-vl:8b"
  memory: "qwen3-vl:8b"

llm_params:    # LLM参数配置
  temperature: 1.3
  topP: 0.9
  timeout: 30

memory:        # 记忆配置
  enabled: true
  vector_enabled: true
  vector_backend: "weaviate"

tools:         # 工具配置
  auto_discovery: true
  mcp_enabled: true
  builtin_tools:
    - memory_write
    - memory_search
    - memory_delete
    - context_search

monitoring:    # 监控配置
  enabled: true

acp:           # ACP配置
  enabled: true
  agent_id: "cxhms_agent_001"
  discovery_enabled: true
```

**配置加载**: `config/settings.py`
- 单例模式
- YAML解析
- 环境变量支持
- 热重载

## 错误处理

### 错误分类

1. **LLMError**: LLM调用错误
   - LLMConnectionError: 连接错误
   - LLMTimeoutError: 超时错误
   - LLMRateLimitError: 速率限制

2. **MCPError**: MCP服务器错误
   - MCPConnectionError: 连接错误
   - MCPTimeoutError: 超时错误

3. **MemoryError**: 记忆操作错误
4. **ContextError**: 上下文操作错误

### 错误响应格式

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

## 性能优化

### 1. 连接池
- SQLite连接池
- HTTP客户端复用
- 向量存储连接复用

### 2. 缓存策略
- LRU缓存（上下文）
- 向量索引缓存
- 工具定义缓存

### 3. 异步处理
- 所有IO操作使用async/await
- 批量操作并发执行
- 后台任务（衰减计算）

## 安全考虑

### 1. 输入验证
- 请求体验证（Pydantic）
- SQL注入防护（参数化查询）
- XSS防护（输出转义）

### 2. 访问控制
- CORS配置
- API密钥（可选）
- 速率限制（待实现）

### 3. 数据安全
- 敏感信息不记录日志
- 配置文件权限控制
- 数据库文件权限

## 部署架构

### 单节点部署

```
┌─────────────────────────────────────┐
│           Docker Container          │
│  ┌───────────────────────────────┐  │
│  │         CXHMS Service         │  │
│  │  - FastAPI (port 8000)        │  │
│  │  - Control (port 8765)        │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │      SQLite Database          │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  Weaviate Embedded (default)  │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │    Milvus Lite (optional)     │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │     Chroma (Win compatible)   │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 多节点部署（生产环境）

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

## 扩展性设计

### 1. 插件系统
- CXFC 插件协议（发现、注册、心跳）
- 工具插件（MCP协议）
- 存储后端插件（多向量后端支持）
- LLM提供商插件

### 2. 水平扩展
- 无状态设计
- 共享存储
- 负载均衡

### 3. 垂直扩展
- 异步处理
- 连接池
- 缓存优化

## 监控与日志

### 日志级别
- DEBUG: 详细调试信息
- INFO: 正常操作信息
- WARNING: 警告信息
- ERROR: 错误信息

### 监控指标（预留）
- 请求QPS
- 响应延迟
- 错误率
- 资源使用率

### 健康检查
- `/health` - 基础健康检查
- `/api/admin/health` - 详细组件状态
- `/api/vector/health` - 向量存储健康检查

## 版本兼容性

### API版本
- 当前版本: v1.0.0
- 版本控制: URL路径（预留）

### 数据迁移
- SQLite迁移脚本
- 配置自动升级

## 开发规范

### 代码风格
- PEP 8
- 类型注解
- 文档字符串

### 测试
- 单元测试（待完善）
- 集成测试（待完善）
- 性能测试（待完善）

### 文档
- API文档（OpenAPI/Swagger）
- 架构文档（本文档）
- 部署文档

---

## 附录

### 术语表

- **RAG**: Retrieval-Augmented Generation，检索增强生成
- **MCP**: Model Context Protocol，模型上下文协议
- **ACP**: Agent Communication Protocol，代理通信协议
- **CXFC**: CXHMS Function Call Protocol，CXHMS 函数调用协议
- **LLM**: Large Language Model，大语言模型

### 参考文档

- [FastAPI文档](https://fastapi.tiangolo.com/)
- [MCP协议规范](https://modelcontextprotocol.io/)
