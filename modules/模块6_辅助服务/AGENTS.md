# AGENTS.md — 模块6_辅助服务

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容。

> ⚠️ 【占位状态】本文件为 H6 任务占位骨架，基于 backend 现有业务边界人工建立。**待 s0203 拓扑化拆分 Skill 触发后由 s0301 重生成**，届时将以正式模块拆分结果替换本占位内容。

---

## 一、模块定位

**模块编号**：模块6_辅助服务
**模块职责**：LLM 客户端、CXFC 插件协议、告警、备份、会话存储、配置管理、统计、归档、Agent 管理
**对应 backend 文件**：
- `backend/core/llm/client.py` — VLLMClient（B6+C1 锁竞态修复 + httpx 统一）
- `backend/core/cxfc/` — CXFC 插件协议
- `backend/core/alarm/` — 告警
- `backend/core/backup/` — 备份
- `backend/core/session/` — 会话存储（D3 移除死代码）
- `backend/core/plugins/` — 插件
- `backend/core/tasks/` — 任务
- `backend/api/routers/{cxfc,alarm,backup,admin,archive,stats,service,config,agents}.py` — 辅助路由

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束，特别是：

- **public/ 保护指令**：`public/` 目录是契约物理载体，任何删除/修改/覆盖/移动操作必须先经人类显式授权。
- **禁止模块间直接导入**：模块间仅允许依赖 `public/` 下的契约。
- **D1 ServiceState + Depends 模式**：通过 `Depends(get_service_state)` 获取服务实例。
- **D3 移除 SessionStore 死代码**：grep 无 `SessionStore` 引用。

---

## 三、模块专属约束

### 3.1 可修改文件范围

- `backend/core/llm/*.py`
- `backend/core/cxfc/*.py`、`alarm/*.py`、`backup/*.py`、`session/*.py`、`plugins/*.py`、`tasks/*.py`
- `backend/api/routers/{cxfc,alarm,backup,admin,archive,stats,service,config,agents}.py`

### 3.2 依赖契约

- 数据契约：`public/schema/agent.json`、`public/schema/error.json`
- 接口契约：`public/interface_stub/agent_service.pyi`
- 配置契约：`public/config_template/{llm,vector,system}_config.json`

### 3.3 关键修复点（B6+C1/D3）

- B6+C1: VLLMClient 移除 _http_lock，仅用 _semaphore（max_concurrent=4）；统一 httpx.AsyncClient，移除 requests + asyncio.to_thread；LLMFactory._clients 加线程安全保护
- D3: 移除 SessionStore 死代码（删除整个 `backend/core/session/store.py`，移除所有引用）

### 3.4 测试要求

- 单元测试：`tests/units/test_llm_client.py`（B6+C1 回归）
- 集成测试：通过 sim_app fixture 验证 LLM 调用

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 修复记录：`.trae/documents/20260702_模块1_*.md`
