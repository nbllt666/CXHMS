# CXHMS - CX-O History & Memory Service

## 简介

CXHMS 是一个类似AnythingLLM的AI代理中间层服务，提供：

- 🧠 **RAG增强记忆系统** - 长期记忆、短期记忆、向量检索
- 🔧 **工具调用系统** - OpenAI Functions兼容
- 🔗 **ACP Connect 2.0** - 局域网Agent发现与群组通讯
- 📊 **强大管理API** - 完整CRUD操作
- 🖥️ **WebUI界面** - Gradio管理界面
- ⚡ **高性能异步架构**
- 🔍 **向量存储支持** - Milvus Lite / Qdrant 双后端

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python main.py
```

服务将在以下地址启动：
- **API服务**: http://localhost:8000
- **WebUI**: http://localhost:7860
- **API文档**: http://localhost:8000/docs

### 3. Docker部署

```bash
docker-compose up -d
```

## 目录结构

```
CXHMS/
├── backend/                 # 后端服务
│   ├── api/                # FastAPI应用
│   │   ├── app.py          # 主应用
│   │   └── routers/        # 路由
│   ├── core/               # 核心服务
│   │   ├── memory/         # 记忆系统
│   │   │   ├── manager.py           # 记忆管理器
│   │   │   ├── vector_store.py      # 向量存储（Milvus Lite/Qdrant）
│   │   │   ├── milvus_lite_store.py # Milvus Lite实现
│   │   │   ├── decay.py            # 衰减计算
│   │   │   ├── emotion.py          # 情感分析
│   │   │   └── secondary_router.py # 副模型路由
│   │   ├── context/        # 上下文管理
│   │   ├── tools/          # 工具系统
│   │   ├── acp/            # ACP互联
│   │   └── llm/            # LLM服务
│   ├── models/             # 数据模型
│   └── storage/            # 存储层
├── webui/                  # Gradio界面
├── config/                 # 配置
├── docs/                   # 文档
│   └── MILVUS_LITE_INTEGRATION.md  # Milvus Lite集成文档
├── data/                   # 数据目录
├── main.py                 # 入口文件
├── requirements.txt        # Python依赖
├── test_vector_store.py   # 向量存储测试脚本
└── Dockerfile             # Docker镜像
```

## API接口

### 记忆管理
- `GET /api/memories` - 列出记忆
- `POST /api/memories` - 创建记忆
- `GET /api/memories/{id}` - 获取记忆
- `PUT /api/memories/{id}` - 更新记忆
- `DELETE /api/memories/{id}` - 删除记忆
- `POST /api/memories/search` - 搜索记忆
- `POST /api/memories/semantic-search` - 语义搜索（向量）
- `POST /api/memories/hybrid-search` - 混合搜索（向量+关键词）
- `GET /api/memories/vector-info` - 向量存储信息
- `POST /api/memories/3d` - 三维评分搜索（重要性、时间、相关性）
- `POST /api/memories/recall/{id}` - 记忆召回与重激活
- `POST /api/memories/batch/write` - 批量写入记忆
- `POST /api/memories/batch/update` - 批量更新记忆
- `POST /api/memories/batch/delete` - 批量删除记忆
- `POST /api/memories/sync-decay` - 同步衰减值
- `GET /api/memories/decay-stats` - 获取衰减统计

### 永久记忆管理
- `POST /api/memories/permanent` - 创建永久记忆（零衰减）
- `GET /api/memories/permanent/{id}` - 获取永久记忆
- `GET /api/memories/permanent` - 列出永久记忆
- `PUT /api/memories/permanent/{id}` - 更新永久记忆
- `DELETE /api/memories/permanent/{id}` - 删除永久记忆

### 副模型命令
- `POST /api/memories/secondary/execute` - 执行副模型指令
- `GET /api/memories/secondary/commands` - 获取可用命令列表
- `GET /api/memories/secondary/history` - 获取执行历史

### 上下文管理
- `GET /api/context/sessions` - 会话列表
- `POST /api/context/sessions` - 创建会话
- `GET /api/context/messages/{session_id}` - 消息历史
- `POST /api/context/summary` - 生成摘要

### ACP互联
- `POST /api/acp/discover` - 发现Agents
- `GET /api/acp/agents` - Agent列表
- `POST /api/acp/groups` - 创建群组
- `POST /api/acp/groups/{id}/join` - 加入群组
- `POST /api/acp/send` - 发送消息
- `POST /api/acp/send/group` - 群发消息

### 工具系统
- `GET /api/tools` - 工具列表
- `POST /api/tools` - 注册工具
- `POST /api/tools/call` - 调用工具

### 管理API
- `GET /api/admin/dashboard` - 仪表盘
- `GET /api/admin/health` - 健康检查
- `GET /api/admin/stats` - 统计信息

## 配置

编辑 `config/default.yaml` 修改配置：

```yaml
server:
  host: "0.0.0.0"
  port: 8000

llm:
  provider: "ollama"
  host: "http://localhost:11434"
  model: "llama3.2:3b"
  temperature: 0.7
  max_tokens: 2048

memory:
  enabled: true
  vector_enabled: true
  vector_backend: "milvus_lite"  # 或 "qdrant"
  milvus_lite:
    db_path: "data/milvus_lite.db"
    vector_size: 768
  qdrant:
    host: "localhost"
    port: 6333
    vector_size: 768
  decay_enabled: true
  decay_rate: 0.1
  decay_interval_days: 7
  reactivation_boost: 0.2
  emotion_enabled: true

acp:
  enabled: true
  agent_id: "cxhms_agent_001"
  agent_name: "CXHMS Agent"
  discovery_enabled: true
  discovery_port: 9999

webui:
  enabled: true
  host: "0.0.0.0"
  port: 7860
```

## 功能特性

### 记忆系统
- 三维记忆评分（重要性、时间、相关性）
- 重要性衰减机制（双阶段指数衰减、艾宾浩斯优化衰减）
- 情感分析与情感加权
- 混合搜索（向量+关键词）
- RAG增强检索
- 永久记忆系统（独立存储、零衰减）
- 记忆召回与重激活机制
- 批量操作支持（批量写入、更新、删除）
- 网络效应增强
- 相关性评分（语义相似度、上下文关联、关键词匹配）
- 衰减统计与洞察
- **向量存储支持**（Milvus Lite / Qdrant）

### 向量存储
- **Milvus Lite** - 零配置，嵌入式向量数据库
  - 无需额外服务器进程
  - 文件存储，简单部署
  - 适合本地开发和小型应用
- **Qdrant** - 高性能向量数据库
  - 需要独立服务器
  - 适合生产环境和大型应用
- **灵活切换** - 配置文件中轻松切换后端
- **统一接口** - 两种后端使用相同的API

### 多模型架构
- 主模型与副模型分离
- 10种副模型命令（摘要、归档、清理、分析、衰减、洞察、批量处理、对话摘要、关键点提取、报告生成）
- 权限控制（副模型无法操作永久记忆）
- 命令执行历史记录
- 场景感知路由（7种场景类型：task、chat、first_interaction、recall、learning、problem_solving、creative）
- 批量衰减处理器（定时执行，默认24小时）

### 上下文管理
- Mono上下文（保持信息在上下文中，支持过期机制）
- LRU缓存（100条缓存上限）
- 自动清理过期缓存
- 会话管理与消息历史

### ACP互联
- UDP局域网发现
- 群组管理
- 群发消息
- 会话同步

### 工具系统
- 动态工具注册
- MCP协议支持
- OpenAI Functions兼容

## 测试

### 向量存储测试

运行向量存储测试脚本：

```bash
python test_vector_store.py
```

选择要测试的向量存储后端：
- 选项 1: Milvus Lite（推荐）
- 选项 2: Qdrant
- 选项 3: 全部测试

## 文档

- [Milvus Lite 集成文档](docs/MILVUS_LITE_INTEGRATION.md) - 详细的向量存储配置和使用指南
- [API文档](http://localhost:8000/docs) - Swagger UI
- [ReDoc文档](http://localhost:8000/redoc) - ReDoc UI

## 向量存储对比

| 特性 | Milvus Lite | Qdrant |
|------|-------------|---------|
| 部署 | 嵌入式，无需服务器 | 需要独立服务器 |
| 配置 | 简单，只需文件路径 | 需要主机和端口 |
| 性能 | 适合中小规模 | 适合大规模 |
| 资源占用 | 低 | 中等 |
| 适用场景 | 本地开发、小型应用 | 生产环境、大型应用 |

## 故障排除

### 向量存储问题

**问题**: 向量搜索不可用

**解决方案**:
1. 检查配置文件中的 `vector_enabled: true`
2. 检查 `vector_backend: "milvus_lite"` 或 `"qdrant"`
3. 安装依赖：`pip install pymilvus>=2.3.0` 或 `pip install qdrant-client>=1.7.0`
4. 查看应用日志中的错误信息

**问题**: 导入错误

```
ImportError: No module named 'pymilvus'
```

**解决方案**:
```bash
pip install pymilvus>=2.3.0
```

## License

MIT License
