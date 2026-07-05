# AGENTS.md — 模块4_图数据库

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容。

> ⚠️ 【占位状态】本文件为 H6 任务占位骨架，基于 backend 现有业务边界人工建立。**待 s0203 拓扑化拆分 Skill 触发后由 s0301 重生成**，届时将以正式模块拆分结果替换本占位内容。

---

## 一、模块定位

**模块编号**：模块4_图数据库
**模块职责**：知识图谱节点/边管理、最短路径查询、级联删除
**对应 backend 文件**：
- `backend/core/graph/` — 图数据库核心逻辑
- `backend/api/routers/graph.py` — 图路由

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束，特别是：

- **public/ 保护指令**：`public/` 目录是契约物理载体，任何删除/修改/覆盖/移动操作必须先经人类显式授权。
- **禁止模块间直接导入**：模块间仅允许依赖 `public/` 下的契约。
- **D1 ServiceState + Depends 模式**：通过 `Depends(get_service_state)` 获取 GraphStore。

---

## 三、模块专属约束

### 3.1 可修改文件范围

- `backend/core/graph/*.py`
- `backend/api/routers/graph.py`

### 3.2 依赖契约

- 数据契约：`public/schema/graph_node.json`、`public/schema/graph_edge.json`
- 接口契约：`public/interface_stub/graph_service.pyi`（含 delete_node cascade、shortest_path agent_id 等签名）

### 3.3 关键修复点

- D6 修复点：`delete_node` 补 `cascade: bool = True`；`shortest_path` 补 `agent_id: str = "default"`（已对齐契约）

### 3.4 测试要求

- 单元测试：契约测试在 `tests/contracts/test_interface_stub.py`（验证 graph_service.pyi 签名匹配）
- 集成测试：通过 sim_app fixture 验证图 CRUD

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 契约变更记录：`public/schema/CHANGELOG.md`（1.0.1 新增 graph_node/graph_edge.json）
