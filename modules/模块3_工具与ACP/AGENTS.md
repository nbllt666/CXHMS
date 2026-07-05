# AGENTS.md — 模块3_工具与ACP

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容。

> ⚠️ 【占位状态】本文件为 H6 任务占位骨架，基于 backend 现有业务边界人工建立。**待 s0203 拓扑化拆分 Skill 触发后由 s0301 重生成**，届时将以正式模块拆分结果替换本占位内容。

---

## 一、模块定位

**模块编号**：模块3_工具与ACP
**模块职责**：工具调用循环、ACP 协议（UDP 9999/9998）、Agent 管理、工具集成
**对应 backend 文件**：
- `backend/core/acp/` — ACP 协议实现（UDP 9999/9998）
- `backend/core/tools/` — 工具系统核心
- `backend/api/routers/acp.py` — ACP 路由
- `backend/api/routers/tools.py` — 工具路由
- `backend/api/routers/agents.py` — Agent 路由（含 B4 空模型回退修复）

---

## 二、AC �式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束，特别是：

- **public/ 保护指令**：`public/` 目录是契约物理载体，任何删除/修改/覆盖/移动操作必须先经人类显式授权。
- **禁止模块间直接导入**：模块间仅允许依赖 `public/` 下的契约。
- **D1 ServiceState + Depends 模式**：通过 `Depends(get_service_state)` 获取服务实例。
- **B4 修复点**：`agents.py:update_agent` 修正空模型回退逻辑（`if key == "model" and not value.strip()`）。

---

## 三、模块专属约束

### 3.1 可修改文件范围

- `backend/core/acp/*.py`
- `backend/core/tools/*.py`
- `backend/api/routers/{acp,tools,agents}.py`

### 3.2 依赖契约

- 数据契约：`public/schema/tool.json`、`public/schema/agent.json`
- 接口契约：`public/interface_stub/tool_service.pyi`、`public/interface_stub/agent_service.pyi`
- 配置契约：`public/config_template/llm_config.json`

### 3.3 关键修复点（B4）

- B4: `recall_memory` 透传 agent_id；`agents.py:update_agent` 修正空模型回退逻辑

### 3.4 测试要求

- 单元测试：`tests/units/test_router.py`（含 agents 路由）
- 集成测试：`tests/simulation/scenarios/test_tool_calling.py`、`test_tool_integration.py`、`test_memory_agent_chat.py`

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 修复记录：`.trae/documents/20260702_模块1_*.md`
