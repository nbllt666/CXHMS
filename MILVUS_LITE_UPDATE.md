# Milvus Lite 集成完成

## 更新内容

已成功集成 Milvus Lite 作为内置向量存储后端。

## 主要变更

### 1. 新增文件

- `backend/core/memory/milvus_lite_store.py` - Milvus Lite 向量存储实现
- `test_vector_store.py` - 向量存储测试脚本
- `docs/MILVUS_LITE_INTEGRATION.md` - Milvus Lite 集成文档

### 2. 修改文件

- `backend/core/memory/vector_store.py` - 添加向量存储基类和工厂函数
- `config/default.yaml` - 添加向量存储配置
- `config/settings.py` - 添加 Milvus Lite 和 Qdrant 配置类
- `backend/core/memory/manager.py` - 支持多种向量存储后端
- `backend/api/app.py` - 根据配置初始化向量存储
- `requirements.txt` - 添加 pymilvus 依赖

## 快速开始

### 1. 安装依赖

```bash
pip install pymilvus>=2.3.0
```

### 2. 配置

编辑 `config/default.yaml`：

```yaml
memory:
  vector_enabled: true
  vector_backend: "milvus_lite"  # 或 "qdrant"
  milvus_lite:
    db_path: "data/milvus_lite.db"
    vector_size: 768
```

### 3. 启动应用

```bash
python -m backend.api.app
```

应用会自动初始化 Milvus Lite 向量存储。

## 测试

运行测试脚本：

```bash
python test_vector_store.py
```

选择要测试的向量存储后端：
- 选项 1: Milvus Lite (推荐)
- 选项 2: Qdrant
- 选项 3: 全部测试

## 特性

### Milvus Lite

✓ 零配置 - 无需额外服务器
✓ 高性能 - 基于 Milvus 引擎
✓ 易用 - 文件存储，简单部署
✓ 兼容 - 完全兼容现有接口

### 向量存储切换

支持在配置中轻松切换向量存储后端：

```yaml
# 使用 Milvus Lite (默认)
vector_backend: "milvus_lite"

# 或使用 Qdrant
vector_backend: "qdrant"
```

## API 端点

### 语义搜索

```bash
POST /api/memories/semantic-search
Content-Type: application/json

{
  "query": "搜索关键词",
  "memory_type": "long_term",
  "limit": 10
}
```

### 混合搜索

```bash
POST /api/memories/hybrid-search
Content-Type: application/json

{
  "query": "搜索关键词",
  "memory_type": "long_term",
  "tags": ["重要"],
  "limit": 10
}
```

### 向量存储信息

```bash
GET /api/memories/vector-info
```

## 文档

详细文档请查看：[docs/MILVUS_LITE_INTEGRATION.md](docs/MILVUS_LITE_INTEGRATION.md)

## 故障排除

### 问题: 导入错误

```
ImportError: No module named 'pymilvus'
```

**解决方案**:

```bash
pip install pymilvus>=2.3.0
```

### 问题: 向量搜索不可用

**解决方案**:

1. 检查配置文件中的 `vector_enabled: true`
2. 检查 `vector_backend: "milvus_lite"`
3. 查看应用日志中的错误信息

### 问题: 数据库文件权限错误

**解决方案**:

确保 `data/` 目录有写权限。

## 下一步

- [ ] 添加向量存储性能监控
- [ ] 支持更多向量数据库 (如 Weaviate, Chroma)
- [ ] 添加向量存储迁移工具
- [ ] 优化向量搜索性能

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
