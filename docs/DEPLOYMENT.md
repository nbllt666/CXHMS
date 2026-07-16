# CXHMS 部署指南

> **文档版本**: v3.0.0 | **最后更新**: 2026-07-17

本指南覆盖 CXHMS（晨曦人格化记忆系统）在 v1.2.0 / RADIX-Lite 闭合后的完整部署流程，包括主服务、依赖服务、RADIX-Lite 4 子系统（蒸馏服务 / 多模态管线 / 模板引擎 / 决策核心）的部署与配置。所有配置项均以 `config/default.yaml` 为真相源。

## 目录

1. [环境要求](#环境要求)
2. [安装步骤](#安装步骤)
3. [配置说明](#配置说明)
4. [环境变量](#环境变量)
5. [启动服务](#启动服务)
6. [RADIX-Lite 子系统部署](#radix-lite-子系统部署)
7. [Docker 部署](#docker-部署)
8. [生产环境配置](#生产环境配置)
9. [故障排除](#故障排除)
10. [升级指南](#升级指南)
11. [契约版本](#契约版本)

---

## 环境要求

### 系统要求

- **操作系统**: Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+
- **Python**: 3.10 或更高版本
- **Node.js**: 18+（前端开发）
- **内存**: 最少 4GB RAM，推荐 8GB+
- **磁盘**: 最少 10GB 可用空间

### 依赖服务

| 服务 | 默认地址 | 用途 | 是否必选 |
|------|---------|------|---------|
| vLLM 主模型 | http://localhost:8002 | 主模型 `gemma4-e4b` 推理 | 必选 |
| vLLM Embedding | http://localhost:8101 | Embedding 模型 `Qwen3-Embedding-0.6B` | 必选 |
| Weaviate 向量库 | http://localhost:8090 | 默认向量后端（gRPC 端口 50061） | 必选 |
| Ollama | http://localhost:11434 | 摘要/记忆副模型 `qwen3-vl:8b`（默认禁用，回退到 main） | 可选 |
| RADIX-Lite 蒸馏服务 | http://localhost:8011 | 多轮蒸馏独立 FastAPI 服务 | 启用 RADIX-Lite 时必选 |

### 向量存储后端（可选切换）

- **Weaviate**（默认）: 独立部署，HTTP 8090 / gRPC 50061
- **Weaviate Embedded**: 嵌入式，无需额外服务
- **Chroma**: 嵌入式，无需额外服务
- **Milvus Lite**: 嵌入式，无需额外服务
- **Qdrant**: 需要独立部署（端口 6333）

---

## 安装步骤

### 1. 克隆仓库

```bash
git clone <repository-url>
cd CXHMS
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. 安装后端依赖

```bash
pip install -r requirements.txt
```

> RADIX-Lite 子系统依赖（Jinja2、PaddleOCR 等）已包含在 `requirements.txt` 中。

### 4. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 5. 创建数据目录

```bash
mkdir -p data logs
mkdir -p data/distillation_sessions
mkdir -p data/distillation_logs
mkdir -p data/templates/presets
mkdir -p data/templates/custom
```

### 6. 准备模型服务

```bash
# 主模型 gemma4-e4b 由 vLLM 提供（端口 8002）
# Embedding 模型 Qwen3-Embedding-0.6B 由 vLLM 提供（端口 8101）

# 摘要/记忆副模型（可选，默认禁用回退到 main）
ollama pull qwen3-vl:8b
```

---

## 配置说明

### 配置文件位置

| 配置文件 | 用途 | 优先级 |
|---------|------|-------|
| `config/default.yaml` | 主配置（真相源） | 默认 |
| `config/production.yaml` | 生产环境覆盖配置（可选） | 高于 default |
| `public/config_template/radix_config.json` | RADIX-Lite 子系统配置契约 | RADIX-Lite 独立加载 |
| 环境变量 `CXHMS_*` | 运行时覆盖 | 最高 |

### 核心配置项

以下配置项均与 `config/default.yaml` 实际值对齐。

#### 服务器配置

```yaml
server:
  host: "0.0.0.0"      # 监听地址
  port: 8001           # API 服务端口
  debug: true          # 调试模式（生产环境建议设为 false）
```

#### LLM 配置

```yaml
llm:
  max_tool_rounds: 10   # 流式与非流式统一工具调用最大轮次
  temperature: 1.5      # 全局温度参数
  max_tokens: 4096      # 全局最大 token 数
```

> ⚠️ **温度参数说明**：`llm.temperature` 为 1.5（全局默认），主模型 `models.main.temperature` 为 0.7。模型级温度优先于全局温度。

#### 模型配置

```yaml
models:
  main:                 # 主模型（默认启用）
    provider: vllm
    host: "http://localhost:8002"
    model: gemma4-e4b
    apiKey: ""
    enabled: true
    port: 8002
    temperature: 0.7    # 主模型温度
    max_tokens: 0       # 0 表示不限制
    timeout: 60         # 调用超时（秒）
    api_key: ""
    supports_tools: true
  embedding:            # Embedding 模型（默认启用）
    provider: vllm
    host: "http://localhost:8101"
    model: "/models/Qwen3-Embedding-0.6B"
    apiKey: ""
    enabled: true
    port: 8101
    temperature: 0
    max_tokens: 512
    timeout: 60
    api_key: ""
    supports_tools: true
  summary:              # 摘要副模型（默认禁用，回退到 main）
    provider: ollama
    host: "http://localhost:11434"
    model: qwen3-vl:8b
    apiKey: ""
    enabled: false
    port: 8000
    temperature: 0.7
    max_tokens: 131072
    timeout: 60
    api_key: ""
    supports_tools: true
  memory:               # 记忆副模型（默认禁用，回退到 main）
    provider: ollama
    host: "http://localhost:11434"
    model: qwen3-vl:8b
    apiKey: ""
    enabled: false
    port: 8000
    temperature: 0.7
    max_tokens: 131072
    timeout: 60
    api_key: ""
    supports_tools: true

model_defaults:
  summary: main         # 摘要副模型禁用时回退到 main
  memory: main          # 记忆副模型禁用时回退到 main
```

#### 记忆配置

```yaml
memory:
  enabled: true
  max_memories: 10000                 # 最大记忆数
  default_importance: 3               # 默认重要性
  decay_enabled: true                 # 启用衰减
  decay_rate: 0.1                     # 衰减率
  decay_interval_days: 7              # 衰减间隔（天）
  reactivation_boost: 0.2             # 重激活加分
  emotion_enabled: true               # 启用情感分析
  vector_enabled: true                # 启用向量搜索
  vector_backend: "weaviate"          # 向量后端: chroma / milvus_lite / qdrant / weaviate / weaviate_embedded
  decay_model: "exponential"          # 衰减模型: exponential / ebbinghaus
  ebbinghaus_params:
    t50: 30.0
    k: 2.0
  chroma:
    db_path: "data/chroma_db"
    collection_name: "memory_vectors"
    vector_size: 768
  milvus_lite:
    db_path: "data/milvus_lite.db"
    vector_size: 768
  qdrant:
    host: "localhost"
    port: 6333
    vector_size: 768
  weaviate:
    host: "localhost"
    port: 8090                        # HTTP 端口
    grpc_port: 50061                  # gRPC 端口
    embedded: false
    vector_size: 768
    schema_class: "CXHMSMemory"
    api_key: null
  hybrid_search_enabled: false        # 混合搜索（默认关闭）
  archive_enabled: true               # 启用归档
  dedup_threshold: 0.85               # 去重阈值
  archive_compression_enabled: true   # 启用归档压缩
```

#### 上下文配置

```yaml
context:
  enabled: true
  max_context_length: 4000            # 上下文最大长度
  context_window: 10                  # 上下文窗口消息数
  include_memories: true
  max_memories_in_context: 5          # 上下文中最大记忆数
  max_summaries_in_context: 10        # 上下文中最大摘要数（v1.2.0 新增）
```

#### ACP 配置

```yaml
acp:
  enabled: true
  local_agent_id: "cxhms_agent_001"
  local_agent_name: "CXHMS Agent"
  discovery_enabled: true
  discovery_port: 9999                # 发现服务端口
  broadcast_port: 9998                # 广播端口
  broadcast_address: "255.255.255.255"
  discovery_interval: 10              # 发现间隔（秒）
```

#### CXFC 配置（插件协议，v1.2.0 启用）

```yaml
cxfc:
  enabled: true                       # 启用 CXFC 插件协议
  discovery_port: 19876               # 插件发现端口
  discovery_enabled: true
  heartbeat_timeout: 60               # 心跳超时（秒）
  auto_reconnect: true                # 自动重连
  storage_path: "data/cxfc_plugins.db"
```

#### 图数据库配置（v1.2.0 启用）

```yaml
graph:
  enabled: true                       # 启用图数据库
  db_path: "data/graph.db"
  auto_create_schema: true
  pool_size: 10
  timeout: 30
  vector_size: 768
  weaviate:
    url: "http://localhost:8090"
    api_key: null
    grpc_port: 50061                  # gRPC 端口
    vector_dim: 768
    batch_size: 100
    ef_construction: 128
    max_connections: 16
  embedding:
    model: "nomic-embed-text"
    batch_size: 32
    device: "cpu"
    cache_folder: null
```

#### 安全配置

```yaml
security:
  api_key_enabled: false              # 启用 API 密钥认证
  api_key: ""
  rate_limit_enabled: false           # 启用速率限制
  rate_limit_requests: 100            # 每分钟请求数限制
  rate_limit_period: 60
```

#### CORS 配置

```yaml
cors:
  enabled: true
  origins:                            # 允许的源（生产环境应限制）
    - "*"
  methods:
    - "*"
  headers:
    - "*"
  allow_credentials: true
```

#### 工具配置

```yaml
tools:
  enabled: true
  auto_discovery: true
  mcp_enabled: false                  # 启用 MCP 工具
  builtin_tools:
    - calculator
    - datetime
    - weather
```

#### 监控配置

```yaml
monitoring:
  enabled: true
  metrics_enabled: true               # 启用指标收集
  health_check_enabled: true          # 启用健康检查
  performance_logging: true           # 启用性能日志
```

#### 日志配置

```yaml
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/app.log"
  max_bytes: 10485760                 # 10MB
  backup_count: 5
```

#### 数据库配置

```yaml
database:
  type: "sqlite"
  path: "data/cxhms.db"
  memories_db: "data/memories.db"
  sessions_db: "data/sessions.db"
  acp_db: "data/acp"
  echo: false
```

#### WebUI 配置（已弃用）

> ⚠️ **已弃用**：WebUI（Gradio，端口 7860）在当前版本中已弃用，该端口不再有服务实际监听。前端通过开发服务器（端口 3000）或构建为静态文件方式运行。`config/default.yaml` 中已无 `webui` 配置段。

### 服务端口表

| 服务 | 地址 | 配置来源 |
|------|------|---------|
| API 服务 | http://localhost:8001 | `server.port` |
| 前端界面 | http://localhost:3000 | 前端开发服务器 |
| 控制服务 | http://localhost:8765 | `backend/control_service.py` |
| vLLM 主模型 | http://localhost:8002 | `models.main.host` |
| vLLM Embedding | http://localhost:8101 | `models.embedding.host` |
| Weaviate 向量库 | http://localhost:8090 | `memory.weaviate.port` |
| Weaviate gRPC | localhost:50061 | `memory.weaviate.grpc_port` |
| RADIX-Lite 蒸馏服务 | http://localhost:8011 | `radix_config.json` |
| Ollama（可选） | http://localhost:11434 | `models.summary.host` |

> **注意**：前端开发服务器（Vite，端口 3000）通过代理转发 `/api` 到 8001、`/control` 到 8765。生产环境构建为静态文件后由 Nginx 反向代理。

---

## 环境变量

系统支持通过环境变量覆盖配置，所有环境变量使用 `CXHMS_` 前缀。环境变量命名规则：`CXHMS_` + 配置节名（大写）+ `_` + 配置键名（大写），层级用下划线分隔。

### 主配置环境变量

| 类别 | 环境变量示例 | 说明 |
|------|-------------|------|
| 服务器 | `CXHMS_SERVER_HOST`, `CXHMS_SERVER_PORT`, `CXHMS_SERVER_DEBUG` | 服务基础配置 |
| LLM | `CXHMS_LLM_TEMPERATURE`, `CXHMS_LLM_MAX_TOOL_ROUNDS` | 全局 LLM 参数 |
| 模型 | `CXHMS_MODELS_MAIN_PROVIDER`, `CXHMS_MODELS_MAIN_MODEL`, `CXHMS_MODELS_MAIN_TEMPERATURE` | 主模型配置 |
| 嵌入模型 | `CXHMS_MODELS_EMBEDDING_PROVIDER`, `CXHMS_MODELS_EMBEDDING_MODEL` | Embedding 模型配置 |
| 记忆 | `CXHMS_MEMORY_ENABLED`, `CXHMS_MEMORY_VECTOR_BACKEND`, `CXHMS_MEMORY_MAX_MEMORIES` | 记忆系统配置 |
| 上下文 | `CXHMS_CONTEXT_ENABLED`, `CXHMS_CONTEXT_MAX_CONTEXT_LENGTH`, `CXHMS_CONTEXT_MAX_SUMMARIES_IN_CONTEXT` | 上下文管理配置 |
| ACP | `CXHMS_ACP_ENABLED`, `CXHMS_ACP_LOCAL_AGENT_ID`, `CXHMS_ACP_DISCOVERY_PORT` | ACP 协议配置 |
| Graph | `CXHMS_GRAPH_ENABLED`, `CXHMS_GRAPH_DB_PATH` | 知识图谱配置 |
| CXFC | `CXHMS_CXFC_ENABLED`, `CXHMS_CXFC_DISCOVERY_PORT`, `CXHMS_CXFC_HEARTBEAT_TIMEOUT` | CXFC 插件协议配置 |
| 安全 | `CXHMS_SECURITY_API_KEY_ENABLED`, `CXHMS_SECURITY_API_KEY` | 安全配置 |
| 监控 | `CXHMS_MONITORING_ENABLED`, `CXHMS_MONITORING_METRICS_ENABLED`, `CXHMS_MONITORING_PERFORMANCE_LOGGING` | 监控配置 |
| 工具 | `CXHMS_TOOLS_ENABLED`, `CXHMS_TOOLS_MCP_ENABLED` | 工具系统配置 |

### RADIX-Lite 环境变量

RADIX-Lite 子系统通过 `public/config_template/radix_config.json` 加载配置（自动补齐缺失字段）。可通过以下环境变量覆盖关键参数：

| 环境变量 | 默认值 | 说明 |
|---------|-------|------|
| `RADIX_DISTILLATION_HOST` | `127.0.0.1` | 蒸馏服务监听地址 |
| `RADIX_DISTILLATION_PORT` | `8011` | 蒸馏服务端口 |
| `RADIX_DISTILLATION_MAX_TURNS` | `4` | 默认最大蒸馏轮次 |
| `RADIX_DISTILLATION_SESSION_TIMEOUT` | `1800` | 会话超时（秒） |
| `RADIX_DISTILLATION_STORAGE_DIR` | `data/distillation_sessions` | 会话持久化目录 |
| `RADIX_MULTIMODAL_WORKER_POOL_SIZE` | `4` | 多模态 worker 池大小 |
| `RADIX_MULTIMODAL_TASK_TIMEOUT` | `120` | 单任务超时（秒） |
| `RADIX_MULTIMODAL_OCR_ENGINE` | `paddleocr` | OCR 引擎 |
| `RADIX_TEMPLATE_TEMPLATES_DIR` | `data/templates` | 模板根目录 |
| `RADIX_VLLM_BASE_URL` | `http://127.0.0.1:8002` | vLLM 主模型 URL |
| `RADIX_VLLM_EMBEDDING_URL` | `http://127.0.0.1:8101` | vLLM Embedding URL |
| `RADIX_VLLM_TIMEOUT` | `300` | LLM 调用超时（秒） |
| `RADIX_DECISION_IMPORTANCE_THRESHOLD` | `0.7` | 永久记忆重要性阈值 |
| `RADIX_DECISION_QUALITY_REJECT_THRESHOLD` | `0.3` | 质量拒绝阈值 |
| `RADIX_DECISION_MAX_REDISTILL_TURNS` | `2` | 最大再次蒸馏轮次 |
| `RADIX_LEGACY_PARSER_ENABLED` | `true` | parser.py 回退开关 |

> 配置加载为 best-effort：`radix_config.json` 不存在或解析失败时使用全默认值并记录警告，不阻断启动。

---

## 启动服务

### 开发环境

```bash
# 启动后端（端口 8001 + 控制服务 8765）
python main.py

# 启动前端（端口 3000）
cd frontend && npm run dev
```

服务启动后访问：

- 前端界面: http://localhost:3000
- API 文档 (Swagger): http://localhost:8001/docs
- API 文档 (ReDoc): http://localhost:8001/redoc
- 健康检查: http://localhost:8001/health
- 控制服务: http://localhost:8765

### 控制服务

控制服务（Control Service）作为独立服务运行在端口 **8765**，提供系统控制和管理接口。该服务随主服务自动启动，也可独立部署。

控制服务功能：
- 系统状态监控与管理
- 运行时配置调整
- 前端 `/control` 路径的请求由该服务处理

### Windows 启动脚本

项目根目录提供 Windows 启动脚本：

| 脚本 | 用途 |
|------|------|
| `2-1.重建环境.bat` | 重建 Conda 环境 |
| `2-2.安装依赖.bat` | 安装后端/前端依赖 |
| `2.启动后端(Conda环境).bat` | 在 Conda 环境中启动后端 |
| `3.启动后端(系统环境).bat` | 在系统 Python 环境中启动后端 |
| `7.激活conda环境.bat` | 激活 Conda 环境 |

### 生产环境

使用 Gunicorn + Uvicorn：

```bash
gunicorn backend.api.app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001
```

参数说明：
- `-w 4`: 4 个工作进程
- `-k uvicorn.workers.UvicornWorker`: 使用 Uvicorn worker

---

## RADIX-Lite 子系统部署

RADIX-Lite 是 v1.2.0 引入的管理 Agent 扩展，包含 4 个子系统。配置契约位于 `public/config_template/radix_config.json`（5 段：`distillation_service` / `multimodal_pipeline` / `template_engine` / `decision_core` / `vllm`）。

### 1. 蒸馏服务部署（端口 8011）

蒸馏服务（DistillationService）是独立 FastAPI 服务，实现 7 状态机多轮蒸馏（draft → collecting → distilling → refining → reviewing → finalizing → finalized）。

**配置（`radix_config.json` → `distillation_service`）**：

```json
{
  "distillation_service": {
    "host": "127.0.0.1",
    "port": 8011,
    "max_turns": 4,
    "session_timeout_seconds": 1800,
    "session_storage_dir": "data/distillation_sessions",
    "log_storage_dir": "data/distillation_logs",
    "main_backend_url": "http://127.0.0.1:8001"
  }
}
```

**部署要点**：
- 默认监听 `127.0.0.1:8011`（仅本地访问，主后端通过 HTTP 调用）
- 会话状态持久化到 `data/distillation_sessions/{session_id}.json`
- 决策审计日志持久化到 `data/distillation_logs/{session_id}.json`
- 通过 `main_backend_url` 调用主后端 API（如 `MemoryManager.write_with_decision`）
- 提供 4 个 API 端点：`POST /radix/distillation/start`、`POST /radix/distillation/advance`、`POST /radix/distillation/finalize`、`GET /radix/distillation/get`

**启动目录准备**：

```bash
mkdir -p data/distillation_sessions
mkdir -p data/distillation_logs
```

### 2. 多模态管线部署（3 worker）

多模态管线（MultimodalPipeline）负责 3 模态预处理（OCR / 视觉 / 文本），包含模态融合与降级开关。

**配置（`radix_config.json` → `multimodal_pipeline`）**：

```json
{
  "multimodal_pipeline": {
    "worker_pool_size": 4,
    "task_timeout_seconds": 120,
    "enabled_modalities": ["text", "character_card", "image"],
    "ocr_engine": "paddleocr",
    "ocr_language": "ch",
    "vision_degraded_fallback": true
  }
}
```

**部署要点**：
- 默认 3 模态启用（去音视频后的精简配置）
- worker 池大小 4（`ProcessPoolExecutor` 或 `ThreadPoolExecutor` 的 `max_workers`）
- OCR 默认使用 PaddleOCR（中英文 `ch`）
- vision 不可用时降级为仅 OCR（`vision_degraded_fallback: true`）
- 最小化模式可仅启用 `["text"]`

**依赖安装**：

```bash
# PaddleOCR（OCR 引擎）
pip install paddleocr paddlepaddle
```

### 3. 模板引擎部署（Jinja2）

模板引擎（TemplateEngine）是进程内引擎，基于 Jinja2 DSL 渲染 + YAML frontmatter 解析 + CRUD。

**配置（`radix_config.json` → `template_engine`）**：

```json
{
  "template_engine": {
    "templates_dir": "data/templates",
    "presets_dir": "data/templates/presets",
    "custom_dir": "data/templates/custom",
    "autoescape": false,
    "trim_blocks": true,
    "lstrip_blocks": true
  }
}
```

**部署要点**：
- 进程内引擎，无需独立服务
- 预设模板目录 `data/templates/presets`（系统预置，不可由 LLM 修改）
- 自定义模板目录 `data/templates/custom`（用户/agent 通过 `create_template` 创建）
- Jinja2 `autoescape` 默认 `false`（提示词模板不转义 HTML）

**启动目录准备**：

```bash
mkdir -p data/templates/presets
mkdir -p data/templates/custom
```

**依赖安装**：

```bash
pip install jinja2 pyyaml
```

### 4. 决策核心部署（rubric 驱动）

决策核心（DecisionCore）实现 6 决策点自主决策（`distill_start` / `distill_collect` / `distill_advance` / `distill_finalize` / `storage_decision` / `content_merge`），由 rubric 驱动。

**配置（`radix_config.json` → `decision_core`）**：

```json
{
  "decision_core": {
    "importance_threshold_permanent": 0.7,
    "quality_reject_threshold": 0.3,
    "max_redistill_turns": 2,
    "ask_user_confidence_threshold": 0.4,
    "cross_validate_sources": [],
    "rejected_content_retention_days": 30,
    "system_prompt_fallback_enabled": true
  }
}
```

**部署要点**：
- 6 决策点 rubric 阈值由 `decision_core` 段配置
- `importance >= 0.7` 存入 `permanent_memories`，否则存入 `memories`
- `quality_score < 0.3` 触发 `D6_REJECT`，内容存入 `rejected_content` 保留 30 天
- `max_redistill_turns` 限制回环次数（默认 2）
- LLM 置信度极低时回退 `system_prompt` 规则（`system_prompt_fallback_enabled: true`）

### 5. vLLM 推理配置

RADIX-Lite 子系统复用主后端的 vLLM 服务：

**配置（`radix_config.json` → `vllm`）**：

```json
{
  "vllm": {
    "base_url": "http://127.0.0.1:8002",
    "vision_model": "",
    "vision_base_url": "http://127.0.0.1:8002",
    "embedding_base_url": "http://127.0.0.1:8101",
    "timeout_seconds": 300,
    "max_tokens": 2048,
    "temperature": 0.3
  }
}
```

**部署要点**：
- `base_url` 与主后端 `models.main.host` 一致
- `vision_model` 留空表示不启用 vision（仅 OCR）；如需 vision 推理，填入模型名（如 `Qwen/Qwen2-VL-7B-Instruct`）
- 蒸馏决策建议低温（`temperature: 0.3`）以保证一致性
- LLM 调用超时 300 秒（蒸馏多轮调用可能较慢）

### 6. parser.py 回退开关

`backend/core/document/parser.py` 提供 `parse_attachments_v2` 双模式入口：

```json
{
  "legacy_parser_enabled": true
}
```

- `true`（默认）：走原有解析逻辑，向后兼容
- `false`：调用 `MultimodalPipeline.preprocess`，启用下沉路径

升级到 RADIX-Lite 多模态管线时设为 `false`。

---

## Docker 部署

### 使用 Docker Compose

#### 1. 构建镜像

```bash
docker-compose build
```

#### 2. 启动服务

```bash
docker-compose up -d
```

#### 3. 查看日志

```bash
docker-compose logs -f
```

#### 4. 停止服务

```bash
docker-compose down
```

### Dockerfile 说明

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建非 root 用户
RUN useradd -m appuser && mkdir -p data logs && chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 暴露端口（API 8001 / 前端 3000 / 控制服务 8765 / RADIX-Lite 蒸馏服务 8011）
EXPOSE 8001 3000 8765 8011

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# 启动命令
CMD ["python", "main.py"]
```

> **注意**：
> - Dockerfile 以非 root 用户 `appuser` 运行，增强安全性
> - 健康检查使用 `curl -f http://localhost:8001/health`，确保 API 服务正常运行
> - WebUI（端口 7860）已弃用，不再暴露

### Docker Compose 配置

```yaml
version: '3.8'

services:
  cxhms:
    build: .
    ports:
      - "8001:8001"        # API 服务
      - "8765:8765"        # 控制服务
      - "8011:8011"        # RADIX-Lite 蒸馏服务
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
      - ./public:/app/public
    environment:
      - CXHMS_CONFIG_PATH=/app/config/default.yaml
    depends_on:
      - weaviate
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - cxhms
    restart: unless-stopped

  weaviate:
    image: semitechnologies/weaviate:1.35.3
    ports:
      - "8090:8090"        # HTTP
      - "50061:50061"      # gRPC
    environment:
      - QUERY_DEFAULTS_LIMIT=20
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
    volumes:
      - weaviate_storage:/var/lib/weaviate
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_storage:/qdrant/storage
    restart: unless-stopped
    profiles:
      - qdrant

volumes:
  weaviate_storage:
  qdrant_storage:
```

### RADIX-Lite 子系统容器化说明

RADIX-Lite 4 子系统部署在同一 `cxhms` 容器内：

| 子系统 | 部署模式 | 端口 | 说明 |
|--------|---------|------|------|
| 蒸馏服务 | 独立 FastAPI 服务 | 8011 | 容器内独立进程，主后端通过 HTTP 调用 |
| 多模态管线 | 进程内 worker 池 | — | 主后端进程内，无独立端口 |
| 模板引擎 | 进程内引擎 | — | 主后端进程内，无独立端口 |
| 决策核心 | 进程内决策器 | — | 主后端进程内，无独立端口 |

**容器化注意事项**：
- 蒸馏服务的会话存储目录 `data/distillation_sessions` 和日志目录 `data/distillation_logs` 需挂载到宿主机持久化
- 模板引擎的 `data/templates` 目录需挂载到宿主机持久化（保留预设和自定义模板）
- 多模态管线的 PaddleOCR 依赖较大，建议使用支持 GPU 的基础镜像加速 OCR 推理
- `radix_config.json` 通过 `./public:/app/public` 挂载，容器内读取 `/app/public/config_template/radix_config.json`

### Weaviate Docker Compose（含向量化模块）

项目提供 `docker-compose.weaviate.yml`，包含 Weaviate 服务和文本向量化模块：

```yaml
version: '3.8'

services:
  weaviate:
    image: semitechnologies/weaviate:1.35.3
    ports:
      - "8090:8090"
      - "50061:50061"
    environment:
      - QUERY_DEFAULTS_LIMIT=20
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
      - ENABLE_MODULES=text2vec-transformers
      - TRANSFORMERS_INFERENCE_API=http://t2v-transformers:8080
    volumes:
      - weaviate_storage:/var/lib/weaviate
    depends_on:
      - t2v-transformers
    restart: unless-stopped

  t2v-transformers:
    image: semitechnologies/transformers-inference:paraphrase-multilingual-MiniLM-L12-v2
    environment:
      - ENABLE_CUDA=0
    restart: unless-stopped

volumes:
  weaviate_storage:
```

> **注意**：Weaviate gRPC 端口为 **50061**（与 `config/default.yaml` 中 `memory.weaviate.grpc_port` 和 `graph.weaviate.grpc_port` 一致）。

---

## 生产环境配置

### 1. 安全配置

#### 启用 API 密钥

```yaml
security:
  api_key_enabled: true
  api_key: "your-secure-api-key-here"
```

#### 限制 CORS

```yaml
cors:
  enabled: true
  origins:
    - "https://yourdomain.com"
    - "https://app.yourdomain.com"
  allow_credentials: true
```

#### 启用速率限制

```yaml
security:
  rate_limit_enabled: true
  rate_limit_requests: 100
  rate_limit_period: 60
```

### 2. 关闭调试模式

```yaml
server:
  debug: false

logging:
  level: "INFO"
```

### 3. 反向代理配置

#### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # 前端静态文件
    location / {
        root /opt/cxhms/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 服务（主后端，端口 8001）
    location /api {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 控制服务（端口 8765）
    location /control {
        proxy_pass http://localhost:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # RADIX-Lite 蒸馏服务（端口 8011，可选暴露）
    location /radix {
        proxy_pass http://localhost:8011;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> **注意**：
> - Nginx 中 `/api` 代理到端口 **8001**，与 `default.yaml` 中 `server.port` 保持一致
> - 前端开发服务器默认将 `/api` 代理到 `localhost:8001`，`/control` 代理到 `localhost:8765`
> - RADIX-Lite 蒸馏服务默认监听 `127.0.0.1:8011`，生产环境如需远程访问需修改 `radix_config.json` 中 `host` 为 `0.0.0.0` 并通过 Nginx 代理

### 4. 系统服务配置

#### systemd 服务文件

创建 `/etc/systemd/system/cxhms.service`：

```ini
[Unit]
Description=CXHMS AI Agent Service
After=network.target

[Service]
Type=simple
User=cxhms
Group=cxhms
WorkingDirectory=/opt/cxhms
Environment="PATH=/opt/cxhms/venv/bin"
Environment="CXHMS_CONFIG_PATH=/opt/cxhms/config/production.yaml"
Environment="CXHMS_SERVER_PORT=8001"
Environment="CXHMS_MEMORY_VECTOR_BACKEND=weaviate"
ExecStart=/opt/cxhms/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl enable cxhms
sudo systemctl start cxhms
sudo systemctl status cxhms
```

---

## 故障排除

### 常见问题

#### 1. 端口被占用

**错误信息**：
```
OSError: [Errno 98] Address already in use
```

**解决方案**：
```bash
# 查找占用端口的进程
lsof -i :8001

# 或修改配置文件使用其他端口
# config/default.yaml
server:
  port: 8001  # 修改为其他端口
```

#### 2. 数据库权限错误

**错误信息**：
```
sqlite3.OperationalError: unable to open database file
```

**解决方案**：
```bash
# 确保数据目录存在且有写权限
mkdir -p data
chmod 755 data
```

#### 3. LLM 连接失败

**错误信息**：
```
无法连接到 vLLM 服务
```

**解决方案**：
1. 检查 vLLM 主模型是否运行：
   ```bash
   curl http://localhost:8002/v1/models
   ```

2. 检查 vLLM Embedding 是否运行：
   ```bash
   curl http://localhost:8101/v1/models
   ```

3. 检查配置中的 `models.main.host` 和 `models.embedding.host` 是否正确

4. 检查防火墙设置

#### 4. 向量搜索不可用

**错误信息**：
```
向量存储不可用
```

**解决方案**：
1. 检查向量存储依赖是否安装：
   ```bash
   # Chroma
   pip install chromadb>=0.4.0
   # Milvus Lite
   pip install pymilvus>=2.3.0
   # Qdrant
   pip install qdrant-client>=1.7.0
   # Weaviate
   pip install weaviate-client>=4.0.0
   ```

2. 检查配置文件中的向量存储设置

3. 如果使用 Qdrant，确保 Qdrant 服务已启动：
   ```bash
   docker-compose --profile qdrant up -d
   ```

4. 如果使用 Weaviate，确保 Weaviate 服务已启动：
   ```bash
   docker-compose up -d weaviate
   ```
   Weaviate 默认端口：8090（HTTP）、50061（gRPC）

   如果使用 Weaviate Embedded 模式（`memory.weaviate.embedded: true`），无需启动独立服务，Weaviate 将在应用内自动启动。

#### 5. RADIX-Lite 蒸馏服务不可用

**错误信息**：
```
无法连接到 RADIX-Lite 蒸馏服务
```

**解决方案**：
1. 检查蒸馏服务是否运行：
   ```bash
   curl http://127.0.0.1:8011/health
   ```

2. 检查 `public/config_template/radix_config.json` 中 `distillation_service.port` 是否为 8011

3. 检查会话存储目录是否存在且有写权限：
   ```bash
   mkdir -p data/distillation_sessions
   mkdir -p data/distillation_logs
   chmod 755 data/distillation_sessions data/distillation_logs
   ```

4. 检查主后端 URL 是否可达（`main_backend_url: http://127.0.0.1:8001`）

5. 如果 `radix_config.json` 不存在，系统会使用全默认值并记录警告，不阻断启动

#### 6. 多模态管线 OCR 失败

**错误信息**：
```
OCR 引擎不可用 / paddleocr 初始化失败
```

**解决方案**：
1. 检查 PaddleOCR 依赖是否安装：
   ```bash
   pip install paddleocr paddlepaddle
   ```

2. 启用降级模式（`vision_degraded_fallback: true`）

3. 最小化模式仅启用文本模态：
   ```json
   {
     "multimodal_pipeline": {
       "enabled_modalities": ["text"]
     }
   }
   ```

#### 7. 模板引擎渲染失败

**错误信息**：
```
Jinja2 模板渲染失败
```

**解决方案**：
1. 检查模板目录是否存在：
   ```bash
   mkdir -p data/templates/presets data/templates/custom
   ```

2. 检查模板 frontmatter 是否符合 YAML 规范

3. 检查 Jinja2 依赖是否安装：
   ```bash
   pip install jinja2 pyyaml
   ```

### 日志分析

#### 查看应用日志

```bash
# 实时查看日志
tail -f logs/app.log

# 查看错误日志
grep ERROR logs/app.log

# 查看特定模块日志
grep "MemoryManager" logs/app.log
grep "DistillationService" logs/app.log
grep "MultimodalPipeline" logs/app.log
```

#### 日志级别调整

开发环境：
```yaml
logging:
  level: "DEBUG"
```

生产环境：
```yaml
logging:
  level: "INFO"
```

### 性能优化

#### 1. 记忆系统优化

```yaml
memory:
  max_memories: 10000              # 限制最大记忆数
  decay_interval_days: 7           # 衰减间隔
  archive_compression_enabled: true  # 启用归档压缩

context:
  max_context_length: 4000         # 上下文最大长度
  context_window: 10               # 上下文窗口
  max_memories_in_context: 5       # 上下文记忆数
  max_summaries_in_context: 10     # 上下文摘要数
```

#### 2. RADIX-Lite 性能优化

```json
{
  "multimodal_pipeline": {
    "worker_pool_size": 8
  },
  "vllm": {
    "timeout_seconds": 600,
    "max_tokens": 4096
  },
  "distillation_service": {
    "max_turns": 4,
    "session_timeout_seconds": 3600
  }
}
```

### 备份与恢复

#### 备份数据

```bash
# 备份 SQLite 数据库
cp data/cxhms.db backups/cxhms_$(date +%Y%m%d).db
cp data/memories.db backups/memories_$(date +%Y%m%d).db
cp data/sessions.db backups/sessions_$(date +%Y%m%d).db
cp data/graph.db backups/graph_$(date +%Y%m%d).db
cp data/cxfc_plugins.db backups/cxfc_plugins_$(date +%Y%m%d).db

# 备份向量存储
cp -r data/milvus_lite.db backups/

# 备份 RADIX-Lite 会话与日志
cp -r data/distillation_sessions backups/
cp -r data/distillation_logs backups/

# 备份模板
cp -r data/templates backups/

# 备份配置
cp config/default.yaml backups/config_$(date +%Y%m%d).yaml
cp public/config_template/radix_config.json backups/radix_config_$(date +%Y%m%d).json
```

#### 恢复数据

```bash
# 停止服务
sudo systemctl stop cxhms

# 恢复数据库
cp backups/cxhms_20260717.db data/cxhms.db
cp backups/memories_20260717.db data/memories.db

# 恢复配置
cp backups/config_20260717.yaml config/default.yaml

# 启动服务
sudo systemctl start cxhms
```

---

## 升级指南

### 升级步骤

1. **备份数据**
   ```bash
   ./scripts/backup.sh
   ```

2. **拉取最新代码**
   ```bash
   git pull origin main
   ```

3. **更新依赖**
   ```bash
   pip install -r requirements.txt --upgrade
   cd frontend && npm install && cd ..
   ```

4. **运行迁移脚本（如有）**
   ```bash
   python scripts/migrate.py
   ```

5. **重启服务**
   ```bash
   sudo systemctl restart cxhms
   ```

### 版本兼容性

- v3.0.0: 当前版本（RADIX-Lite v1.2.0 闭合）
- v2.3.0: 旧版本（2026-07-02）
- 升级前请查看 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md) 了解破坏性变更

### RADIX-Lite 升级路径

从 v2.3.0 升级到 v3.0.0（RADIX-Lite v1.2.0）：

1. RADIX-Lite 子系统契约为 MINOR 变更（新增可选接口），不影响现有模块
2. `backend/core/document/parser.py` 新增 `parse_attachments_v2` 双模式入口，`legacy_parser_enabled` 默认 `true` 向后兼容
3. `backend/core/memory/manager.py` 新增 `write_with_decision` + `rejected_content` 表（保留 30 天）
4. 模块间通过 try-except fallback 到 Mock，不硬依赖真实实现
5. 升级后可逐步将 `legacy_parser_enabled` 设为 `false` 启用多模态管线下沉路径

---

## 契约版本

当前三层契约版本：**v1.2.0**（2026-07-16）

### 契约清单

| 契约类型 | 数量 | 位置 |
|---------|------|------|
| 数据契约（JSON Schema draft-07+） | 13 份 | `public/schema/` |
| 接口契约（.pyi 存根） | 13 份 | `public/interface_stub/` |
| 配置契约（JSON Schema） | 5 份 | `public/config_template/` |
| 预生成 Mock | 12 份 | `public/pre_generated_mock/` |

> v1.2.0 在 v1.1.0 基础上新增 6 schema + 6 .pyi + 1 config（`radix_config.json`）+ 6 Mock。

### 版本历史

- **v1.2.0**（2026-07-16）：RADIX-Lite 4 新模块契约（6 schema + 6 .pyi + 1 config + 6 Mock）
- v1.1.0（2026-07-14）：AnythingLLM 兼容层
- v1.0.2（2026-07-04）：jsonschema 严格化
- v1.0.1（2026-07-04）：接口契约补全 + graph schema 新增
- v1.0.0（2026-07-02）：初始 5 schema + 5 .pyi + 3 config

详见 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md)。

---

## 获取帮助

### 文档资源

- [项目概述](PROJECT_OVERVIEW.md)
- [架构文档](ARCHITECTURE.md)
- [模块详解](MODULES.md)
- [API 文档](API.md)
- [技术文档](TECHNICAL.md)
- [契约变更日志](../public/schema/CHANGELOG.md)

### 社区支持

- GitHub Issues: 报告问题
- GitHub Discussions: 讨论功能

### 调试模式

启用详细日志：

```yaml
server:
  debug: true

logging:
  level: "DEBUG"
```

---

## 许可证

MIT License

---

*文档版本: v3.0.0*
*最后更新: 2026-07-17*
