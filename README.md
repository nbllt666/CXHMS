# CXHMS (晨曦人格化记忆系统)

CXHMS 是一个智能记忆管理平台，支持长期记忆存储、语义搜索、自动归档等功能。

## 功能特性

- **多向量存储后端**：支持 Weaviate Embedded、普通 Weaviate、Milvus Lite、Qdrant
- **高级归档功能**：智能去重、自动合并、层级归档
- **记忆管理对话**：通过自然语言与记忆管理模型交互
- **现代化前端**：React + TypeScript + Tailwind CSS，支持深色/浅色模式

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动后端服务

```bash
python main.py
```

后端服务将在 http://localhost:8000 启动

### 启动前端开发服务器

```bash
cd frontend
npm install
npm run dev
```

前端将在 http://localhost:3000 启动

## 配置说明

编辑 `config/default.yaml` 配置文件：

```yaml
memory:
  vector_backend: "weaviate_embedded"  # 或 weaviate, milvus_lite, qdrant
  weaviate:
    host: "localhost"
    port: 8080
    embedded: true  # true 使用 Embedded Weaviate
    vector_size: 768
```

## 项目结构

```
CXHMS/
├── backend/           # 后端代码
│   ├── api/          # FastAPI 路由
│   ├── core/         # 核心业务逻辑
│   └── models/       # 数据模型
├── frontend/         # React 前端
│   ├── src/         # 源代码
│   └── package.json
├── config/          # 配置文件
└── data/            # 数据存储
```

## API 文档

启动服务后访问 http://localhost:8000/docs 查看完整的 API 文档。

## 许可证

MIT License
