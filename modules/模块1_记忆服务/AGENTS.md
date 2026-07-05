# AGENTS.md — 模块1_记忆服务

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容。

> ⚠️ 【占位状态】本文件为 H6 任务占位骨架，基于 backend 现有业务边界人工建立。**待 s0203 拓扑化拆分 Skill 触发后由 s0301 重生成**，届时将以正式模块拆分结果替换本占位内容。

---

## 一、模块定位

**模块编号**：模块1_记忆服务
**模块职责**：记忆 CRUD、衰减、agent 隔离、向量搜索、HybridSearch、3d 搜索、上下文管理
**对应 backend 文件**：
- `backend/core/memory/manager.py` — 同步 MemoryManager（CRUD、衰减、agent 隔离、search_memories_3d）
- `backend/core/memory/async_manager.py` — AsyncMemoryManager（B1 初始化、B2 schema 一致性）
- `backend/core/memory/hybrid_search.py` — HybridSearch（B5 agent 隔离）
- `backend/core/memory/router.py` — _get_recent_memories（B8 上界分页）
- `backend/core/memory/secondary_router.py` — SecondaryInstruction
- `backend/core/memory/emotion.py` — 情感衰减
- `backend/core/context/manager.py` — ContextManager（C3 增量持久化）
- `backend/api/routers/memory.py` — 记忆路由
- `backend/api/routers/memory_chat.py` — 记忆对话路由
- `backend/api/routers/vector.py` — 向量路由

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束，特别是：

- **public/ 保护指令**：`public/` 目录是契约物理载体，任何删除/修改/覆盖/移动操作必须先经人类显式授权。
- **禁止模块间直接导入**：模块间仅允许依赖 `public/` 下的契约。
- **D1 ServiceState + Depends 模式**：通过 `Depends(get_service_state)` 获取 MemoryManager。
- **D2 移除 MemoryManager 单例**：按 db_path 实例化。
- **B1-B5/B8 修复点回归**：单元测试必须覆盖（详见 `tests/units/test_memory_manager.py` 等）。

---

## 三、模块专属约束

### 3.1 可修改文件范围

- `backend/core/memory/*.py`（所有记忆相关核心代码）
- `backend/core/context/manager.py`
- `backend/api/routers/{memory,memory_chat,vector}.py`

### 3.2 依赖契约

- 数据契约：`public/schema/memory.json`、`public/schema/graph_node.json`、`public/schema/graph_edge.json`
- 接口契约：`public/interface_stub/memory_service.pyi`（含 get_memory/hybrid_search/semantic_search/batch_update_memories/batch_delete_memories 等签名）
- 配置契约：`public/config_template/vector_config.json`

### 3.3 关键修复点（B1-B5/B8/C2/C5/C6）

- B1: AsyncMemoryManager 在 app.py lifespan 中 `await async_memory_manager.initialize()`
- B2: 同步/异步 schema 一致（memory_type 字段统一）
- B3: MemoryOperationError 异常经 handler 返回正确 error_code
- B4: recall_memory 透传 agent_id，跨 agent 记忆不串扰
- B5: HybridSearch 透传 workspace_id/agent_id，结果仅含当前 agent
- B8: _get_recent_memories 加 max_pages=10 上界
- C2: 复用 ThreadPoolExecutor 跑 embedding
- C5: search_memories_3d DB 端过滤（decay 计算下推 SQL）
- C6: search_memories content 列加索引

### 3.4 测试要求

- 单元测试：`tests/units/test_memory_manager.py`、`test_async_manager.py`、`test_context_manager.py`、`test_hybrid_search.py`、`test_router.py`
- 集成测试：`tests/simulation/scenarios/test_memory_write_search.py`、`test_hybrid_search_agent_isolation.py`、`test_3d_search_ranking.py`

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 契约变更记录：`public/schema/CHANGELOG.md`
- 修复记录：`.trae/documents/20260702_模块1_*.md`、`20260704_模块0_D6阻断复审2修复.md`
