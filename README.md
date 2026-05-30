# CXHMS (晨曦人格化记忆系统)

CXHMS (CX-O History & Memory Service) 是一个智能记忆管理平台，提供长期记忆存储、语义搜索、自动归档、多模型对话、ACP协议通信、图数据库、CXFC插件协议和工具调用功能。

## 核心特性

- **智能记忆系统**: 多向量存储后端（Milvus Lite/Chroma/Qdrant/Weaviate）、记忆衰减模型、三维评分、混合搜索
- **图数据库**: 知识图谱、语义搜索、路径分析、社区检测
- **ACP 协议**: 局域网自动发现、点对点通信、群组协同
- **CXFC 插件协议**: 插件发现、技能注册、心跳管理
- **工具生态**: MCP 协议支持、内置工具（计算器、记忆管理、提醒等）、动态注册
- **对话系统**: 流式响应、RAG 检索增强、多 Agent 支持、多模态视觉
- **提醒系统**: 定时提醒、闹钟管理
- **备份恢复**: 数据备份与恢复
- **WebSocket**: 实时通信
- **多模型支持**: 支持 Ollama 本地模型，可配置多个模型实例
- **国际化**: i18next 多语言支持

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Ollama (推荐) 或其他 LLM 服务

### 安装启动

```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 安装模型 (使用 Ollama)
ollama pull qwen3-vl:8b
ollama pull nomic-embed-text

# 3. 启动后端
python main.py

# 4. 安装并启动前端
cd frontend && npm install && npm run dev
```

**Windows 一键启动**: `.\1.1.启动前端(含控制服务)(Conda).bat`

### 服务地址

| 服务 | 地址 |
|------|------|
| API 文档 (Swagger) | http://localhost:8000/docs |
| API 文档 (ReDoc) | http://localhost:8000/redoc |
| 前端界面 | http://localhost:3000 |

## 主要 API

| 端点 | 描述 |
|------|------|
| `POST /api/chat/stream` | 流式聊天 |
| `GET/POST /api/memories` | 记忆管理 |
| `POST /api/memories/search` | 记忆搜索 |
| `POST /api/memories/semantic-search` | 语义搜索 |
| `GET/POST /api/agents` | Agent 管理 |
| `GET/POST /api/tools` | 工具管理 |
| `POST /api/acp/discover` | Agent 发现 |
| `GET/POST /api/nodes` | 图节点管理 |
| `GET/POST /api/edges` | 图边管理 |
| `POST /api/traverse/bfs\|dfs` | 图遍历 |
| `GET/POST /api/vector/*` | 向量数据库管理 |
| `GET/POST /api/cxfc/*` | CXFC 插件管理 |
| `GET/PUT /api/config` | 配置管理 |
| `GET /api/stats` | 统计信息 |
| `POST /api/archive/*` | 归档管理 |
| `POST /api/backup/*` | 备份恢复 |

完整 API 文档: http://localhost:8000/docs

## 项目结构

```
CXHMS/
├── backend/           # Python 后端 (FastAPI)
│   ├── api/routers/   # API 路由 (17个路由模块)
│   │   ├── acp.py     # ACP 协议
│   │   ├── admin.py   # 管理员
│   │   ├── agents.py  # Agent 管理
│   │   ├── archive.py # 归档管理
│   │   ├── backup.py  # 备份恢复
│   │   ├── chat.py    # 聊天接口
│   │   ├── config.py  # 配置管理
│   │   ├── context.py # 上下文管理
│   │   ├── cxfc.py    # CXFC 插件协议
│   │   ├── graph.py   # 图数据库
│   │   ├── memory.py  # 记忆管理
│   │   ├── memory_chat.py # 记忆聊天
│   │   ├── service.py # 服务管理
│   │   ├── stats.py   # 统计
│   │   ├── tools.py   # 工具管理
│   │   ├── vector.py  # 向量搜索
│   │   └── websocket.py # WebSocket
│   ├── core/          # 核心模块 (12个子模块)
│   │   ├── acp/       # ACP 协议
│   │   ├── alarm/     # 提醒管理
│   │   ├── backup/    # 备份管理
│   │   ├── context/   # 上下文管理
│   │   ├── cxfc/      # CXFC 插件协议
│   │   ├── graph/     # 图数据库
│   │   ├── llm/       # LLM 客户端
│   │   ├── memory/    # 记忆系统 (含5种向量后端)
│   │   ├── plugins/   # 插件管理
│   │   ├── session/   # 会话管理
│   │   ├── tools/     # 工具系统
│   │   └── websocket/ # WebSocket 管理
│   ├── models/        # 数据模型
│   └── tests/         # 测试用例 (17个测试文件)
├── frontend/          # React 前端
│   └── src/
│       ├── pages/     # 页面组件 (9个页面)
│       ├── components/# UI 组件 (27个文件)
│       ├── store/     # 状态管理 (Zustand)
│       └── api/       # API 客户端
├── config/            # 配置文件
│   └── default.yaml   # 默认配置
├── plugins/           # 插件目录
└── docs/              # 文档
    ├── API.md         # API 文档
    ├── ARCHITECTURE.md# 架构文档
    ├── DEPLOYMENT.md  # 部署指南
    └── TECHNICAL.md   # 技术文档
```

## 配置

主配置文件: `config/default.yaml`

```yaml
models:
  main:
    provider: ollama
    model: qwen3-vl:8b
  memory:
    provider: ollama
    model: qwen3-vl:8b

memory:
  vector_backend: weaviate
  decay_model: exponential
  emotion_enabled: true

server:
  host: 0.0.0.0
  port: 8000
```

## 技术栈

**后端**: FastAPI, Pydantic, Milvus Lite/Chroma/Qdrant/Weaviate, Ollama, SQLite
**前端**: React, TypeScript, Vite, Tailwind CSS, Zustand, React Query, i18next, Framer Motion, Recharts, Axios

## 开发

### 后端开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行测试
cd backend && pytest tests/ -v

# 运行测试覆盖率
pytest tests/ --cov=backend --cov-report=term-missing

# 代码格式化
black backend/
isort backend/
```

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build

# 运行测试
npm test

# 代码格式化
npm run format

# 类型检查
npm run typecheck
```

## 文档

- [API 文档](docs/API.md)
- [架构文档](docs/ARCHITECTURE.md)
- [部署指南](docs/DEPLOYMENT.md)
- [技术文档](docs/TECHNICAL.md)

## 许可证

MIT License
