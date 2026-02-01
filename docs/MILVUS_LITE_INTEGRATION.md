# Milvus Lite 集成说明

## 概述

CXHMS 现在支持使用 Milvus Lite 作为内置向量存储后端。Milvus Lite 是一个轻量级的向量数据库，无需额外的服务器进程，非常适合本地开发和生产环境。

## 特性

- **零配置**: 无需单独的服务器进程，直接嵌入到应用中
- **高性能**: 基于 Milvus 的强大向量搜索能力
- **易用**: 简单的文件存储，无需复杂的部署
- **兼容**: 完全兼容现有的向量搜索接口

## 安装

### 1. 安装依赖

```bash
pip install pymilvus>=2.3.0
```

### 2. 配置向量存储

在 `config/default.yaml` 中配置：

```yaml
memory:
  enabled: true
  vector_enabled: true
  vector_backend: "milvus_lite"  # 使用 Milvus Lite
  milvus_lite:
    db_path: "data/milvus_lite.db"  # 数据库文件路径
    vector_size: 768  # 向量维度
```

## 使用方法

### 基本使用

向量搜索会在应用启动时自动启用（如果配置正确）：

```python
# 应用会自动初始化 Milvus Lite
# 无需额外代码
```

### 切换向量存储后端

你可以在配置中切换不同的向量存储后端：

```yaml
memory:
  vector_backend: "milvus_lite"  # 使用 Milvus Lite (默认)
  # vector_backend: "qdrant"  # 或使用 Qdrant
```

### 程序化使用

```python
from backend.core.memory.vector_store import create_vector_store

# 创建 Milvus Lite 向量存储
vector_store = create_vector_store(
    backend="milvus_lite",
    db_path="data/milvus_lite.db",
    vector_size=768
)

# 添加向量
await vector_store.add_memory_vector(
    memory_id=1,
    content="这是一条记忆",
    embedding=[0.1, 0.2, ...],  # 768维向量
    metadata={"type": "long_term"}
)

# 搜索相似向量
results = await vector_store.search_similar(
    query_embedding=[0.1, 0.2, ...],
    limit=10,
    min_score=0.5
)
```

## API 接口

### 向量搜索

使用语义搜索功能：

```bash
POST /api/memories/semantic-search
{
  "query": "搜索关键词",
  "memory_type": "long_term",
  "limit": 10
}
```

### 混合搜索

结合向量搜索和关键词搜索：

```bash
POST /api/memories/hybrid-search
{
  "query": "搜索关键词",
  "memory_type": "long_term",
  "tags": ["重要"],
  "limit": 10
}
```

## 性能优化

### 向量维度

根据你的嵌入模型选择合适的向量维度：

- `sentence-transformers/all-MiniLM-L6-v2`: 384 维
- `sentence-transformers/all-mpnet-base-v2`: 768 维
- `text-embedding-ada-002`: 1536 维

### 索引类型

Milvus Lite 支持多种索引类型，默认使用 COSINE 距离：

```python
# 在 milvus_lite_store.py 中修改
metric_type="COSINE"  # 或 "L2", "IP"
```

## 故障排除

### 问题: 导入错误

```
ImportError: No module named 'pymilvus'
```

**解决方案**: 安装 pymilvus

```bash
pip install pymilvus>=2.3.0
```

### 问题: 向量搜索不可用

**解决方案**: 检查配置

1. 确保 `vector_enabled: true`
2. 确保 `vector_backend: "milvus_lite"`
3. 检查日志中的错误信息

### 问题: 数据库文件权限错误

**解决方案**: 确保数据目录有写权限

```bash
# Linux/Mac
chmod 755 data/

# Windows
# 确保应用有 data/ 目录的写权限
```

## 与 Qdrant 对比

| 特性 | Milvus Lite | Qdrant |
|------|-------------|---------|
| 部署 | 嵌入式，无需服务器 | 需要独立服务器 |
| 配置 | 简单，只需文件路径 | 需要主机和端口 |
| 性能 | 适合中小规模 | 适合大规模 |
| 资源占用 | 低 | 中等 |
| 适用场景 | 本地开发、小型应用 | 生产环境、大型应用 |

## 数据迁移

### 从 Qdrant 迁移到 Milvus Lite

1. 配置使用 Milvus Lite
2. 重启应用
3. 系统会自动同步数据

```bash
# 应用启动时会自动同步
# 查看日志确认同步状态
```

### 手动同步

```python
from backend.core.memory.manager import MemoryManager

manager = MemoryManager()
# ... 初始化向量存储 ...

# 手动触发同步
result = await manager._vector_store.sync_with_sqlite(manager)
print(f"同步完成: {result}")
```

## 监控和调试

### 查看向量存储状态

```bash
GET /api/memories/vector-info
```

响应示例：

```json
{
  "row_count": 1000,
  "status": "active",
  "collection_name": "memory_vectors",
  "dimension": 768
}
```

### 日志

查看向量搜索相关的日志：

```bash
# 应用日志会显示向量搜索的详细信息
tail -f logs/app.log | grep "向量"
```

## 最佳实践

1. **定期备份**: 备份 `data/milvus_lite.db` 文件
2. **监控性能**: 定期检查向量搜索性能
3. **清理数据**: 定期清理过期的向量数据
4. **测试迁移**: 在生产环境迁移前先测试

## 更多资源

- [Milvus 官方文档](https://milvus.io/docs/zh/quickstart.md)
- [Milvus Lite 文档](https://milvus.io/docs/zh/milvus_lite.md)
- [PyMilvus API 参考](https://milvus.io/api-reference/pymilvus/v2.3.x/About.md)

## 贡献

如果你发现任何问题或有改进建议，欢迎提交 Issue 或 Pull Request。
