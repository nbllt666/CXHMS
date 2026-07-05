# AGENTS.md — 模块0_全局调度面板

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容。

> ⚠️ 【占位状态】本文件为 H6 任务占位骨架，基于 backend 现有业务边界人工建立。**待 s0203 拓扑化拆分 Skill 触发后由 s0301 重生成**，届时将以正式模块拆分结果替换本占位内容。

---

## 一、模块定位

**模块编号**：模块0_全局调度面板
**模块职责**：FastAPI 应用入口、ServiceState 装配、全局依赖注入、lifespan 管理、路由聚合、全局异常 handler
**对应 backend 文件**：
- `backend/api/app.py` — FastAPI 应用主入口、lifespan、ServiceState 装配、全局 exception handler
- `backend/dependencies.py` — ServiceState 定义、get_service_state、get_memory_manager、get_async_memory_manager 等依赖工厂
- `backend/main.py` — Uvicorn 启动入口
- `backend/config.py` — CXHMSConfig 配置加载
- `backend/api/routers/__init__.py` — 路由聚合

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束，特别是：

- **public/ 保护指令**：`public/` 目录是契约物理载体，任何删除/修改/覆盖/移动操作必须先经人类显式授权（`ec7_action_gate` 强制执行）。
- **禁止模块间直接导入**：模块间仅允许依赖 `public/` 下的契约。
- **D1 ServiceState + Depends 模式**：所有 router 通过 `Depends(get_service_state)` 获取服务实例，禁止使用模块级全局实例。
- **D2 移除 MemoryManager 单例**：按 db_path 实例化，不触碰 `_instance` 类变量。
- **路径解析**：必须用 `os.path.dirname(os.path.abspath(__file__))`，禁止相对路径 `../`。

---

## 三、模块专属约束

### 3.1 可修改文件范围

- `backend/api/app.py`（lifespan、exception handler、路由注册）
- `backend/dependencies.py`（ServiceState、依赖工厂）
- `backend/main.py`、`backend/config.py`（仅启动相关）

### 3.2 依赖契约

本模块作为全局入口，聚合所有 `public/` 下契约：
- 数据契约：`public/schema/{memory,agent,message,tool,error,graph_node,graph_edge}.json`
- 接口契约：`public/interface_stub/{memory,chat,agent,tool,graph}_service.pyi`
- 配置契约：`public/config_template/{llm,vector,system}_config.json`

### 3.3 测试要求

- 单元测试：`tests/units/test_router.py`（max_tool_rounds 统一、_get_recent_memories 上界分页）
- 集成测试：`tests/simulation/scenarios/test_*.py`（通过 sim_app fixture 触发 lifespan 装配 ServiceState）

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 项目结构：`docs/ARCHITECTURE.md`、`docs/MODULES.md`
