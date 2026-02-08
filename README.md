# CXHMS (晨曦人格化记忆系统)

CXHMS 是一个智能记忆管理平台，支持长期记忆存储、语义搜索、自动归档、多模型对话等功能。

## 功能特性

### 核心功能
- **多向量存储后端**：支持 Weaviate、Milvus Lite、Qdrant、Ollama Embeddings
- **高级归档功能**：智能去重、自动合并、层级归档
- **记忆管理对话**：通过自然语言与记忆管理模型交互
- **ACP 协议支持**：Agent 通信协议，支持多 Agent 发现与协作
- **上下文管理**：智能上下文摘要、窗口管理、记忆检索增强

### 前端特性
- **现代化技术栈**：React 18 + TypeScript + Tailwind CSS
- **主题支持**：深色/浅色模式切换
- **响应式设计**：完美适配桌面和移动设备
- **实时状态**：React Query 数据管理、Zustand 状态管理

### 后端特性
- **高性能框架**：FastAPI + Uvicorn 异步服务器
- **多 LLM 支持**：Ollama、OpenAI、Anthropic 兼容接口
- **工具系统**：MCP 协议支持、内置工具注册表、自动工具发现
- **监控健康**：性能监控、健康检查、指标收集

### 开发与部署
- **完整测试套件**：Vitest 前端测试 + Pytest 后端测试 (30+ 测试用例)
- **类型安全**：TypeScript 完整类型检查 + Pydantic 数据验证
- **Docker 支持**：Dockerfile + docker-compose 一键部署
- **多环境支持**：Windows 批处理脚本、conda 环境配置

## 快速开始

### 环境要求

- **Python**: 3.10+
- **Node.js**: 18+
- **Ollama**: 本地运行 LLM 模型 (推荐)
- **向量数据库**: Milvus Lite / Qdrant / Weaviate (可选)

### 1. 克隆并安装后端依赖

```bash
# 创建 conda 环境 (推荐)
conda create -n cxhms python=3.10
conda activate cxhms

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Ollama (如需本地 LLM)
# Windows: https://ollama.com/download
# macOS: brew install ollama
```

### 2. 启动后端服务

```bash
# 方式一: 使用 conda 环境
.\2.启动后端(Conda环境).bat

# 方式二: 使用系统 Python
.\3.启动后端(系统环境).bat

# 方式三: 手动启动
python main.py
```

后端服务将在 http://localhost:8000 启动

API 文档: http://localhost:8000/docs

### 3. 启动前端开发服务器

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将在 http://localhost:3000 启动

### 4. 一键启动所有服务 (Windows)

```bash
# 使用 conda 环境启动前端和控制服务
.\1.1.启动前端(含控制服务)(Conda).bat

# 使用系统环境启动前端和控制服务
.\1.2.启动前端(含控制服务)(系统).bat

# 或运行所有测试
python run_tests.py
```

## 配置说明

### 默认配置

编辑 `config/default.yaml` 配置文件：

```yaml
server:
  host: "0.0.0.0"
  port: 8000

# LLM 模型配置
models:
  main:
    provider: "ollama"
    host: "http://localhost:11434"
    model: "qwen3vl:8b"
    enabled: true
  summary:
    provider: "ollama"
    model: "llama3.2:3b"
    enabled: false

# 向量存储后端配置
memory:
  vector_backend: "milvus_lite"  # milvus_lite, qdrant, weaviate
  hybrid_search_enabled: false
  archive_enabled: true
  
  # 记忆衰减模型配置（可选）
  # exponential - 双阶段指数衰减（默认，推荐用于生产环境）
  # ebbinghaus  - 艾宾浩斯遗忘曲线（实验性，更符合人类记忆规律）
  decay_model: exponential
  
  # 艾宾浩斯模型参数（仅当 decay_model 为 ebbinghaus 时生效）
  ebbinghaus_params:
    t50: 30.0  # 半衰期（天），记忆衰减到50%所需时间
    k: 2.0     # 曲线陡峭度，值越大遗忘越快

# ACP 协议配置
acp:
  enabled: true
  discovery_enabled: true
  discovery_port: 9999
```

### 必需服务

确保以下服务正在运行：

1. **Ollama** (本地 LLM)
   ```bash
   ollama serve
   ollama pull qwen3vl:8b    # 主模型
   ollama pull llama3.2:3b   # 辅助模型
   ```

2. **向量数据库** (根据配置选择)
   - **Milvus Lite** (默认): 自动创建本地数据库
   - **Qdrant**: `docker run -p 6333:6333 qdrant/qdrant`
   - **Weaviate**: `docker run -p 8080:8080 semitechnologies/weaviate`

## 项目结构

```
CXHMS/
├── backend/                    # 后端代码
│   ├── api/                   # FastAPI 路由
│   │   ├── routers/          # API 端点
│   │   │   ├── acp.py       # ACP 协议端点
│   │   │   ├── admin.py     # 管理端点
│   │   │   ├── agents.py    # Agent 管理
│   │   │   ├── archive.py    # 归档管理
│   │   │   ├── chat.py      # 聊天对话
│   │   │   ├── context.py   # 上下文管理
│   │   │   ├── memory.py     # 记忆管理
│   │   │   ├── memory_chat.py # 记忆对话
│   │   │   ├── service.py   # 服务状态
│   │   │   └── tools.py     # 工具管理
│   │   └── app.py            # FastAPI 应用
│   ├── core/                 # 核心业务逻辑
│   │   ├── acp/              # ACP 协议实现
│   │   │   ├── discover.py  # Agent 发现
│   │   │   └── group.py      # Agent 组管理
│   │   ├── context/          # 上下文管理
│   │   │   ├── manager.py   # 上下文管理器
│   │   │   └── summarizer.py # 摘要生成
│   │   ├── llm/             # LLM 客户端
│   │   │   ├── client.py    # 通用客户端
│   │   │   └── tools.py     # LLM 工具
│   │   ├── memory/           # 记忆管理核心
│   │   │   ├── archiver.py  # 归档处理器
│   │   │   ├── conversation.py # 对话记忆
│   │   │   ├── decay.py      # 记忆衰减
│   │   │   ├── deduplication.py # 去重
│   │   │   ├── embedding.py  # 嵌入生成
│   │   │   ├── emotion.py    # 情感分析
│   │   │   ├── hybrid_search.py # 混合搜索
│   │   │   ├── manager.py    # 记忆管理器
│   │   │   ├── router.py     # 路由管理
│   │   │   ├── vector_store.py # 向量存储
│   │   │   ├── milvus_lite_store.py
│   │   │   └── weaviate_store.py
│   │   └── tools/           # 工具系统
│   │       ├── mcp.py       # MCP 协议
│   │       └── registry.py   # 工具注册表
│   ├── models/               # Pydantic 数据模型
│   ├── storage/              # 数据存储层
│   │   └── database/         # 数据库管理
│   ├── tests/                # 后端测试
│   │   ├── test_api/        # API 测试
│   │   ├── test_core/        # 单元测试
│   │   └── test_integration/ # 集成测试
│   ├── control_service.py    # 控制服务
│   └── scripts/              # 启动脚本
├── frontend/                  # React 前端
│   ├── src/
│   │   ├── api/             # API 客户端
│   │   ├── components/       # React 组件
│   │   │   ├── Header.tsx
│   │   │   ├── Layout.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── pages/           # 页面组件
│   │   │   ├── AcpPage.tsx
│   │   │   ├── AgentsPage.tsx
│   │   │   ├── ArchivePage.tsx
│   │   │   ├── ChatPage.tsx
│   │   │   ├── MemoriesPage.tsx
│   │   │   ├── SettingsPage.tsx
│   │   │   └── ToolsPage.tsx
│   │   ├── store/           # Zustand 状态管理
│   │   │   ├── chatStore.ts
│   │   │   └── themeStore.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts        # Vite 配置
│   ├── tailwind.config.js   # Tailwind 配置
│   ├── tsconfig.json         # TypeScript 配置
│   └── vitest.config.ts      # Vitest 配置
├── config/                    # 配置文件
│   ├── default.yaml         # 默认配置
│   └── settings.py           # 配置加载器
├── docs/                      # 文档
│   ├── API.md               # API 文档
│   ├── ARCHITECTURE.md      # 架构文档
│   └── DEPLOYMENT.md        # 部署文档
├── webui/                     # Gradio WebUI
├── data/                      # 数据存储目录
├── logs/                      # 日志目录
├── main.py                   # 主入口
├── run_tests.py              # 测试运行器
├── pytest.ini                # pytest 配置
├── Dockerfile                # Docker 镜像
├── docker-compose.yml        # Docker Compose
└── requirements.txt          # Python 依赖
```

## API 文档

启动服务后访问 http://localhost:8000/docs 查看完整的 Swagger API 文档。

### 主要 API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/chat` | POST | 聊天对话 |
| `/api/chat/history` | GET | 获取对话历史 |
| `/api/memory` | GET/POST | 记忆管理 |
| `/api/memory/search` | POST | 语义搜索 |
| `/api/archive` | GET/POST | 归档管理 |
| `/api/agents` | GET/POST | Agent 管理 |
| `/api/tools` | GET | 工具列表 |
| `/api/context` | GET/POST | 上下文管理 |
| `/api/acp` | GET/POST | ACP 协议 |

## 测试

### 前端测试

```bash
cd frontend

# 运行测试
npm test

# 监视模式
npm run test:watch

# 类型检查
npm run typecheck

# 代码检查
npm run lint

# 生成覆盖率报告
npm run test:coverage
```

### 后端测试

```bash
# 运行所有测试
python -m pytest backend/tests -v

# 运行特定模块
python -m pytest backend/tests/test_api -v
python -m pytest backend/tests/test_core -v

# 生成覆盖率报告
python -m pytest backend/tests --cov=backend --cov-report=html
```

### 统一测试运行器

```bash
# 运行所有测试
python run_tests.py

# 只运行前端测试
python run_tests.py --frontend-only

# 只运行后端测试
python run_tests.py --backend-only

# 带覆盖率报告
python run_tests.py --coverage
```

**测试覆盖**: 30+ 测试用例覆盖所有主要功能模块

## Docker 部署

### 使用 Docker Compose

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f cxhms

# 停止服务
docker-compose down
```

### 手动构建

```bash
# 构建镜像
docker build -t cxhms:latest .

# 运行容器
docker run -d -p 8000:8000 -p 7860:7860 \
  -v ./data:/app/data \
  -v ./config:/app/config \
  --name cxhms \
  cxhms:latest
```

## 技术栈

### 前端
- **框架**: React 18 + TypeScript
- **构建工具**: Vite 6
- **样式**: Tailwind CSS
- **状态管理**: Zustand + React Query
- **UI 组件**: Lucide React 图标库
- **动画**: Framer Motion
- **图表**: Recharts
- **测试**: Vitest + jsdom
- **代码质量**: ESLint + TypeScript ESLint

### 后端
- **框架**: FastAPI + Uvicorn
- **数据验证**: Pydantic v2
- **向量存储**: Milvus Lite + Qdrant + Weaviate
- **LLM 集成**: OpenAI + Anthropic + Ollama
- **工具协议**: MCP (Model Context Protocol)
- **数据库**: SQLite + SQLAlchemy
- **日志**: Python logging
- **测试**: pytest + pytest-asyncio + FastAPI TestClient

## 许可证

MIT License

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request
