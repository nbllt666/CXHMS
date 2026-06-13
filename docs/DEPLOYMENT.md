# CXHMS 部署指南

> **文档版本**: v2.1.0 | **最后更新**: 2026-06-13

## 目录

1. [环境要求](#环境要求)
2. [安装步骤](#安装步骤)
3. [配置说明](#配置说明)
4. [启动服务](#启动服务)
5. [Docker部署](#docker部署)
6. [生产环境配置](#生产环境配置)
7. [故障排除](#故障排除)

---

## 环境要求

### 系统要求

- **操作系统**: Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+
- **Python**: 3.10 或更高版本
- **内存**: 最少 4GB RAM，推荐 8GB+
- **磁盘**: 最少 10GB 可用空间

### 依赖服务

- **LLM服务**（可选）:
  - Ollama: http://localhost:11434
  - 或其他兼容OpenAI API的服务

- **向量存储**（可选）:
  - Chroma: 嵌入式，无需额外服务
  - Milvus Lite: 嵌入式，无需额外服务
  - Qdrant: 需要独立部署
  - Weaviate: 需要独立部署（默认后端）
  - Weaviate Embedded: 嵌入式，无需额外服务

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

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 创建数据目录

```bash
mkdir -p data
mkdir -p logs
```

---

## 配置说明

### 配置文件位置

主配置文件: `config/default.yaml`

### 核心配置项

#### 服务器配置

```yaml
server:
  host: "0.0.0.0"      # 监听地址，0.0.0.0表示所有接口
  port: 8000           # API服务端口
  debug: false         # 调试模式（生产环境设为false）
```

#### LLM配置

```yaml
llm:
  provider: "ollama"   # LLM提供商: ollama, vllm, openai, anthropic, deepseek, local
  host: "http://localhost:11434"  # LLM服务地址
  model: "qwen3-vl:8b" # 模型名称
  temperature: 1.3     # 温度参数
  max_tokens: 0        # 最大token数（0表示不限制）
  top_p: 0.9           # Top-P采样参数
```

#### 模型配置

```yaml
models:
  main:
    provider: ollama
    host: "http://localhost:11434"
    model: qwen3-vl:8b
    apiKey: ""
    enabled: true
    port: 0
    temperature: 0.0
    max_tokens: 0
    timeout: 0
  embedding:
    provider: ""
    host: ""
    model: ""
    apiKey: ""
    enabled: false
  summary:
    provider: ollama
    model: qwen3-vl:8b
    enabled: false
  memory:
    provider: ollama
    model: qwen3-vl:8b
    enabled: false

model_defaults:
  summary_fallback: main
  memory_fallback: main
```

#### 记忆配置

```yaml
memory:
  enabled: true                    # 启用记忆功能
  max_memories: 0                  # 最大记忆数（0不限制）
  default_importance: 3            # 默认重要性
  decay_enabled: true              # 启用衰减
  decay_rate: 0.01                 # 衰减率
  decay_interval_days: 1           # 衰减间隔（天）
  reactivation_boost: 0.3          # 重激活加分
  emotion_enabled: true            # 启用情感分析
  vector_enabled: true             # 启用向量搜索
  vector_backend: "weaviate"       # 向量后端: chroma / milvus_lite / qdrant / weaviate / weaviate_embedded
  decay_model: "exponential"       # 衰减模型: exponential / ebbinghaus
  ebbinghaus_params: {}            # 艾宾浩斯参数
  chroma:
    collection_name: "cxhms_memories"  # Chroma集合名称
  milvus_lite:
    db_path: "data/milvus_lite.db" # Milvus Lite数据库路径
    vector_size: 768               # 向量维度
  qdrant:
    host: "localhost"              # Qdrant主机
    port: 6333                     # Qdrant端口
    vector_size: 768
  weaviate:
    host: "localhost"              # Weaviate主机
    port: 8090                     # Weaviate端口（HTTP）
    grpc_port: 50051               # Weaviate gRPC端口
    embedded: false                # 是否使用嵌入式模式
  hybrid_search_enabled: true      # 启用混合搜索
  archive_enabled: true            # 启用归档
  dedup_threshold: 0.95            # 去重阈值
  archive_compression_enabled: false  # 启用归档压缩
```

#### ACP配置

```yaml
acp:
  enabled: true                    # 启用ACP功能
  local_agent_id: "cxhms_agent_001"  # 本机Agent ID
  local_agent_name: "CXHMS Agent"  # 本机Agent名称
  discovery_enabled: true          # 启用局域网发现
  discovery_port: 9999             # 发现服务端口
  broadcast_port: 9998             # 广播端口
  broadcast_address: ""            # 广播地址
  discovery_interval: 30           # 发现间隔（秒）
```

#### WebUI配置

```yaml
webui:
  enabled: true                    # 启用WebUI
  host: "0.0.0.0"
  port: 7860                       # WebUI端口
  share: false                     # 是否生成公开链接
```

#### 安全配置

```yaml
security:
  api_key_enabled: false           # 启用API密钥认证
  api_key: ""                      # API密钥
  rate_limit_enabled: false        # 启用速率限制
  rate_limit_requests: 100         # 每分钟请求数限制
  rate_limit_period: 60
```

#### CORS配置

```yaml
cors:
  enabled: true
  origins:                         # 允许的源（生产环境应限制）
    - "*"
  allow_credentials: true
```

#### 工具配置

```yaml
tools:
  enabled: true                    # 启用工具系统
  auto_discovery: true             # 自动发现工具
  mcp_enabled: false               # 启用MCP工具
  builtin_tools:                   # 内置工具列表
    - calculator
    - datetime
    - random
    - json_format
```

#### 监控配置

```yaml
monitoring:
  enabled: true                    # 启用监控
  metrics_enabled: false           # 启用指标收集
  health_check_enabled: true       # 启用健康检查
  performance_logging: false       # 启用性能日志
```

### 环境变量

系统支持通过环境变量覆盖配置，所有环境变量使用 `CXHMS_` 前缀。环境变量分为8大类：

| 类别 | 环境变量示例 | 说明 |
|------|-------------|------|
| 服务器 | `CXHMS_SERVER_HOST`, `CXHMS_SERVER_PORT`, `CXHMS_SERVER_DEBUG` | 服务基础配置 |
| 模型 | `CXHMS_MODELS_MAIN_PROVIDER`, `CXHMS_MODELS_MAIN_MODEL` | LLM模型配置 |
| 记忆 | `CXHMS_MEMORY_ENABLED`, `CXHMS_MEMORY_VECTOR_BACKEND` | 记忆系统配置 |
| 上下文 | `CXHMS_CONTEXT_ENABLED`, `CXHMS_CONTEXT_MAX_CONTEXT_LENGTH` | 上下文管理配置 |
| ACP | `CXHMS_ACP_ENABLED`, `CXHMS_ACP_LOCAL_AGENT_ID` | ACP协议配置 |
| 安全 | `CXHMS_SECURITY_API_KEY_ENABLED`, `CXHMS_SECURITY_API_KEY` | 安全配置 |
| 监控 | `CXHMS_MONITORING_ENABLED`, `CXHMS_MONITORING_HEALTH_CHECK_ENABLED` | 监控配置 |
| 工具 | `CXHMS_TOOLS_ENABLED`, `CXHMS_TOOLS_MCP_ENABLED` | 工具系统配置 |

环境变量命名规则：`CXHMS_` + 配置节名（大写）+ `_` + 配置键名（大写），层级用下划线分隔。

---

## 启动服务

### 开发环境

```bash
python main.py
```

服务启动后访问:
- API文档: http://localhost:8000/docs
- WebUI: http://localhost:7860
- 控制服务: http://localhost:8765
- 健康检查: http://localhost:8000/health

### 生产环境

使用Gunicorn + Uvicorn:

```bash
gunicorn backend.api.app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

参数说明:
- `-w 4`: 4个工作进程
- `-k uvicorn.workers.UvicornWorker`: 使用Uvicorn worker

---

## Docker部署

### 使用Docker Compose

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

### Dockerfile说明

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建数据目录
RUN mkdir -p data logs

# 暴露端口
EXPOSE 8000 7860

# 启动命令
CMD ["python", "main.py"]
```

### Docker Compose配置

```yaml
version: '3.8'

services:
  cxhms:
    build: .
    ports:
      - "8000:8000"
      - "7860:7860"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    environment:
      - CXHMS_CONFIG_PATH=/app/config/default.yaml
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

  weaviate:
    image: semitechnologies/weaviate:1.35.3
    ports:
      - "8090:8090"
      - "50051:50051"
    environment:
      - QUERY_DEFAULTS_LIMIT=20
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
    volumes:
      - weaviate_storage:/var/lib/weaviate
    restart: unless-stopped
    profiles:
      - weaviate

volumes:
  qdrant_storage:
  weaviate_storage:
```

### Weaviate Docker Compose（含向量化模块）

项目提供 `docker-compose.weaviate.yml`，包含 Weaviate 服务和文本向量化模块：

```yaml
version: '3.8'

services:
  weaviate:
    image: semitechnologies/weaviate:1.35.3
    ports:
      - "8090:8090"
      - "50051:50051"
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

---

## 生产环境配置

### 1. 安全配置

#### 启用API密钥

```yaml
security:
  api_key_enabled: true
  api_key: "your-secure-api-key-here"
```

#### 限制CORS

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

### 2. 日志配置

```yaml
logging:
  level: "INFO"
  file: "logs/app.log"
  max_bytes: 10485760    # 10MB
  backup_count: 5        # 保留5个备份
```

### 3. 数据库配置

生产环境建议使用PostgreSQL替代SQLite:

```yaml
database:
  type: "postgresql"
  host: "localhost"
  port: 5432
  name: "cxhms"
  user: "cxhms_user"
  password: "your-password"
```

### 4. 反向代理配置

#### Nginx配置示例

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    
    # API服务（主后端）
    location /api {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 控制服务
    location /control {
        proxy_pass http://localhost:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebUI
    location /webui/ {
        proxy_pass http://localhost:7860/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

> **前端代理配置**: 前端开发服务器默认将 `/api` 代理到 `localhost:8001`，`/control` 代理到 `localhost:8765`。

### 5. 系统服务配置

#### systemd服务文件

创建 `/etc/systemd/system/cxhms.service`:

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
Environment="CXHMS_SERVER_PORT=8000"
Environment="CXHMS_MEMORY_VECTOR_BACKEND=weaviate"
ExecStart=/opt/cxhms/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务:

```bash
sudo systemctl enable cxhms
sudo systemctl start cxhms
sudo systemctl status cxhms
```

---

## 故障排除

### 常见问题

#### 1. 端口被占用

**错误信息**:
```
OSError: [Errno 98] Address already in use
```

**解决方案**:
```bash
# 查找占用端口的进程
lsof -i :8000

# 或修改配置文件使用其他端口
# config/default.yaml
server:
  port: 8001  # 修改为其他端口
```

#### 2. 数据库权限错误

**错误信息**:
```
sqlite3.OperationalError: unable to open database file
```

**解决方案**:
```bash
# 确保数据目录存在且有写权限
mkdir -p data
chmod 755 data
```

#### 3. LLM连接失败

**错误信息**:
```
无法连接到Ollama服务器
```

**解决方案**:
1. 检查Ollama是否运行:
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. 检查配置中的host是否正确

3. 检查防火墙设置

#### 4. 向量搜索不可用

**错误信息**:
```
向量存储不可用
```

**解决方案**:
1. 检查向量存储依赖是否安装:
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

3. 如果使用Qdrant，确保Qdrant服务已启动:
   ```bash
   docker-compose --profile qdrant up -d
   ```

4. 如果使用Weaviate，确保Weaviate服务已启动:
   ```bash
   docker-compose --profile weaviate up -d
   ```
   Weaviate 默认端口：8090（HTTP）、50051（gRPC）

5. 如果使用Chroma或Milvus Lite，无需额外服务，检查数据目录权限

#### 5. MCP服务器启动失败

**错误信息**:
```
启动MCP服务器失败
```

**解决方案**:
1. 检查MCP服务器命令是否正确
2. 确保所需的npm包或Python包已安装
3. 检查端口是否被占用
4. 查看详细错误日志

### 日志分析

#### 查看应用日志

```bash
# 实时查看日志
tail -f logs/app.log

# 查看错误日志
grep ERROR logs/app.log

# 查看特定模块日志
grep "MCPManager" logs/app.log
```

#### 日志级别调整

开发环境:
```yaml
logging:
  level: "DEBUG"
```

生产环境:
```yaml
logging:
  level: "INFO"
```

### 性能优化

#### 1. 数据库优化

```sql
-- 为常用查询添加索引
CREATE INDEX IF NOT EXISTS idx_memories_type_created ON memories(type, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_workspace ON memories(workspace_id);
```

#### 2. 内存优化

```yaml
memory:
  max_memories: 10000  # 限制最大记忆数
  
context:
  max_messages: 50     # 限制上下文消息数
```

#### 3. 连接池配置

```yaml
database:
  pool_size: 10
  max_overflow: 20
```

### 备份与恢复

#### 备份数据

```bash
# 备份SQLite数据库
cp data/memories.db backups/memories_$(date +%Y%m%d).db

# 备份向量存储
cp -r data/milvus_lite.db backups/

# 备份配置
cp config/default.yaml backups/config_$(date +%Y%m%d).yaml
```

#### 恢复数据

```bash
# 停止服务
sudo systemctl stop cxhms

# 恢复数据库
cp backups/memories_20240206.db data/memories.db

# 恢复配置
cp backups/config_20240206.yaml config/default.yaml

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

- v2.1.0: 当前版本
- 升级前请查看CHANGELOG.md了解破坏性变更

---

## 获取帮助

### 文档资源

- [API文档](API.md)
- [架构文档](ARCHITECTURE.md)

### 社区支持

- GitHub Issues: 报告问题
- GitHub Discussions: 讨论功能

### 调试模式

启用详细日志:

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

*文档版本: v2.1.0*
*最后更新: 2026-06-13*
