# CXHMS (晨曦人格化记忆系统)

CXHMS (CX-O History & Memory Service) 是一个智能记忆管理平台，提供长期记忆存储、语义搜索、自动归档、多模型对话、ACP协议通信和工具调用功能。

## 核心特性

- **智能记忆系统**: 多向量存储后端、记忆衰减模型、三维评分、混合搜索
- **ACP 协议**: 局域网自动发现、点对点通信、群组协同
- **工具生态**: MCP 协议支持、内置工具、动态注册
- **对话系统**: 流式响应、RAG 检索增强、多 Agent 支持

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Ollama (推荐)

### 安装启动

```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 安装模型
ollama pull qwen3-vl:8b
ollama pull nomic-embed-text

# 3. 启动后端
python main.py

# 4. 启动前端
cd frontend && npm install && npm run dev
```

**Windows 一键启动**: `.\1.1.启动前端(含控制服务)(Conda).bat`

### 服务地址

| 服务 | 地址 |
|------|------|
| API 文档 | http://localhost:8000/docs |
| 前端界面 | http://localhost:3000 |
| Gradio WebUI | http://localhost:7860 |

## 主要 API

| 端点 | 描述 |
|------|------|
| `POST /api/chat/stream` | 流式聊天 |
| `GET/POST /api/memories` | 记忆管理 |
| `POST /api/memories/search` | 记忆搜索 |
| `GET/POST /api/agents` | Agent 管理 |
| `GET/POST /api/tools` | 工具管理 |
| `POST /api/acp/discover` | Agent 发现 |

完整 API 文档: http://localhost:8000/docs

## 项目结构

```
CXHMS/
├── backend/           # Python 后端 (FastAPI)
│   ├── api/routers/   # API 路由
│   └── core/          # 核心模块 (memory, llm, tools, acp)
├── frontend/          # React 前端
│   └── src/pages/     # 页面组件
├── config/            # 配置文件
└── docs/              # 文档
```

## 配置

主配置文件: `config/default.yaml`

```yaml
models:
  main:
    provider: ollama
    model: qwen3-vl:8b

memory:
  vector_backend: milvus_lite
  decay_model: exponential
```

## 技术栈

**后端**: FastAPI, Pydantic, Milvus Lite, Ollama  
**前端**: React, TypeScript, Vite, Tailwind CSS, Zustand

## 文档

- [API 文档](docs/API.md)
- [架构文档](docs/ARCHITECTURE.md)
- [部署指南](docs/DEPLOYMENT.md)
- [技术文档](docs/TECHNICAL.md)

## 许可证

MIT License
