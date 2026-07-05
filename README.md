# CXHMS (晨曦人格化记忆系统)

CXHMS (CX-O History & Memory Service) 是一个智能记忆管理平台，提供长期记忆存储、语义搜索、自动归档、多模型对话、ACP协议通信、图数据库、CXFC插件协议和工具调用功能。

## 核心特性

- **智能记忆系统**: 多向量存储后端（Milvus Lite/Chroma/Qdrant/Weaviate/Weaviate Embedded）、双阶段指数衰减+艾宾浩斯遗忘曲线、三维评分、混合搜索、情感分析、去重检测、副模型路由
- **图数据库**: 知识图谱、语义搜索、路径分析、社区检测、PageRank、GraphML/DOT导出
- **ACP 协议**: 局域网自动发现、点对点通信、群组协同
- **CXFC 插件协议**: 插件发现、技能注册、心跳管理、事件推送
- **工具生态**: MCP 协议支持、内置工具（calculator/datetime/random/json_format）、主模型工具（write_long_term_memory/search_all_memories/call_assistant/set_alarm/mono/write_permanent_memory/ACP工具）、摘要工具、记忆管理工具（16个）、图工具
- **对话系统**: 流式响应、RAG 检索增强、多 Agent 支持、多模态视觉、WebSocket实时通信
- **双通信模式**: WebSocket + SSE fallback，自动降级保障连接可靠性
- **连接检测与动态配置**: ConnectionCheck 组件实时检测后端连接状态，支持动态配置切换
- **视觉/多模态支持**: 图片上传与识别，支持视觉模型多模态对话
- **提醒系统**: 定时提醒、闹钟管理
- **备份恢复**: 选择性备份、导入导出
- **控制服务**: 独立端口8765，管理后端启停
- **配置系统**: YAML配置 + 环境变量 + 自动修复 + 验证
- **国际化**: i18next 多语言支持（zh-CN/en-US）
- **LLM E2E 测试**: 自动化质量评判框架

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- vLLM（默认主模型/Embedding 服务）或 Ollama（副模型，可选）

### 安装启动

```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 准备模型服务（默认使用 vLLM）
#    主模型 gemma4-e4b 由 vLLM 提供：http://localhost:8002
#    Embedding 模型 Qwen3-Embedding-0.6B 由 vLLM 提供：http://localhost:8101
#    摘要/记忆副模型（可选）使用 Ollama: ollama pull qwen3-vl:8b

# 3. 启动后端
python main.py

# 4. 安装并启动前端
cd frontend && npm install && npm run dev
```

**Windows 启动脚本**（位于项目根目录）：

| 脚本 | 用途 |
|------|------|
| `2-1.重建环境.bat` | 重建 Conda 环境 |
| `2-2.安装依赖.bat` | 安装后端/前端依赖 |
| `2.启动后端(Conda环境).bat` | 在 Conda 环境中启动后端 |
| `3.启动后端(系统环境).bat` | 在系统 Python 环境中启动后端 |
| `7.激活conda环境.bat` | 激活 Conda 环境 |

### 服务地址

| 服务 | 地址 |
|------|------|
| API 服务 | http://localhost:8001 |
| API 文档 (Swagger) | http://localhost:8001/docs |
| API 文档 (ReDoc) | http://localhost:8001/redoc |
| 前端界面 | http://localhost:3000 |
| 控制服务 | http://localhost:8765 |
| vLLM 主模型 | http://localhost:8002 |
| vLLM Embedding | http://localhost:8101 |
| Weaviate 向量库 | http://localhost:8090 |

> **注意**: API 默认端口为 8001、前端开发服务器为 3000、控制服务为 8765、vLLM 主模型为 8002（见 `config/default.yaml`）。前端开发服务器通过代理转发请求至 8001 端口，Swagger/ReDoc 文档可通过前端代理访问。

## 主要 API

| 端点 | 描述 |
|------|------|
| `POST /api/chat/stream` | 流式聊天 |
| `POST /api/chat` | 同步聊天 |
| `POST /api/memory-agent/chat/stream` | 记忆管理Agent对话 |
| `GET/POST /api/memories` | 记忆管理 |
| `POST /api/memories/search` | 记忆搜索 |
| `POST /api/memories/semantic-search` | 语义搜索 |
| `POST /api/memories/rag` | RAG检索 |
| `POST /api/memories/3d` | 3D评分搜索 |
| `POST /api/memories/batch/*` | 批量操作（write/update/delete/tags/archive/restore/tag-by-query/delete-by-query/archive-by-query） |
| `POST /api/memories/batch/write` | 批量写入记忆 |
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
| `GET/POST /api/backups` | 备份恢复 |
| `WS /ws/{agent_id}` | WebSocket |
| `GET /api/service/*` | 服务管理 |
| `GET /api/admin/*` | 管理员 |

完整 API 文档: http://localhost:8001/docs

## 项目结构

```
CXHMS/
├── backend/                # Python 后端 (FastAPI)
│   ├── api/routers/        # API 路由 (17个路由模块：acp/admin/agents/archive/backup/chat/config/context/cxfc/graph/memory/memory_chat/service/stats/tools/vector/websocket)
│   ├── core/               # 核心模块 (12个子模块：acp/alarm/backup/context/cxfc/graph/llm/memory/plugins/session/tools/websocket)
│   ├── models/             # 数据模型 (acp.py, context.py, memory.py)
│   ├── tests/              # 后端测试用例
│   ├── cache.py            # 缓存
│   ├── exceptions.py       # 异常定义
│   ├── logging_config.py   # 日志配置
│   ├── model_router.py     # 模型路由
│   ├── utils.py            # 工具函数
│   └── control_service.py  # 控制服务 (端口8765)
├── frontend/               # React 前端
│   └── src/
│       ├── pages/          # 页面组件 (9个页面)
│       ├── components/     # UI组件库 + 布局组件 + 功能组件(GraphManager/ConnectionCheck/VirtualList/SummaryModal/ErrorBoundary/LanguageSwitcher)
│       ├── store/          # 状态管理 (chatStore + themeStore)
│       ├── hooks/          # 自定义Hooks (useWebSocket + useHotkey)
│       ├── i18n/           # 国际化 (zh-CN + en-US)
│       ├── api/            # API 客户端
│       └── styles/         # 样式文件 (animations.css, variables.css)
├── config/                 # 配置文件
│   ├── default.yaml        # 默认配置（真相源）
│   ├── env.py              # 环境变量
│   ├── validation.py       # 配置验证
│   ├── repair.py           # 配置修复
│   └── settings.py         # 设置加载
├── modules/                # 业务模块区（AC 范式：按「模块N_中文名」组织，当前为空骨架）
├── interfaces/             # 入口层（AC 范式：app.py / main.py / start.bat，当前为空骨架）
├── workspace/              # 用户数据区（AC 范式）
├── public/                 # 全局公共资源区（只读契约载体，AC 范式真相源）
│   ├── schema/             # 数据契约 (JSON Schema)
│   ├── interface_stub/     # 接口契约 (.pyi 存根)
│   ├── config_template/    # 配置契约模板
│   ├── pre_generated_mock/ # 预生成 Mock（并行开发支点）
│   ├── global_mock/        # 全局可自定义 Mock
│   ├── test_cases/         # 通用测试用例
│   └── dependencies/       # 依赖锁定
├── scripts/                # 脚本目录
├── data/                   # 运行时数据 (SQLite/向量库等)
├── logs/                   # 运行日志
└── docs/                   # 文档
    ├── API.md              # API 文档
    ├── ARCHITECTURE.md     # 架构文档
    ├── DEPLOYMENT.md       # 部署指南
    ├── TECHNICAL.md        # 技术文档
    ├── PROJECT_OVERVIEW.md # 项目概述
    └── MODULES.md          # 模块详解
```

## 配置

主配置文件: `config/default.yaml`（端口、模型等以该文件为真相源）

```yaml
server:
  host: 0.0.0.0
  port: 8001          # API 服务端口

models:
  main:               # 默认主模型
    provider: vllm
    host: http://localhost:8002
    model: gemma4-e4b
    enabled: true
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
  vector_backend: weaviate
  decay_model: exponential
  emotion_enabled: true
  hybrid_search_enabled: false   # 默认关闭
  archive_enabled: true
  dedup_threshold: 0.85

llm:
  max_tool_rounds: 10            # 流式与非流式统一
```

## 技术栈

**后端**: FastAPI, Pydantic v2, SQLite, Milvus Lite/Chroma/Qdrant/Weaviate, Ollama/vLLM/OpenAI/Anthropic/DeepSeek, httpx, psutil
**前端**: React 18.3.1, TypeScript 5.7.2, Vite 6.0.6, Tailwind CSS 3.4.17, Zustand 5.0.2, React Query 5.62.11, i18next 25.8.4, Framer Motion 11.15.0, Recharts 2.15.0, Lucide React 0.469.0, Axios 1.7.9, React Markdown 9.0.1, date-fns 4.1.0

## 开发

### 后端开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行测试
cd backend && pytest tests/ -v

# 运行测试覆盖率
pytest tests/ --cov=backend --cov-report=term-missing

# LLM E2E 测试
cd backend/tests/llm_e2e && python main.py

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

# 类型检查
npm run typecheck

# 代码格式化
npm run format

# 运行测试
npm run test

# 测试覆盖率
npm run test:coverage
```

## 文档

- [项目概述](docs/PROJECT_OVERVIEW.md)
- [架构文档](docs/ARCHITECTURE.md)
- [模块详解](docs/MODULES.md)
- [API 文档](docs/API.md)
- [部署指南](docs/DEPLOYMENT.md)
- [技术文档](docs/TECHNICAL.md)

## 许可证

MIT License
