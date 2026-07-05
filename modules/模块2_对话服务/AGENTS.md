# AGENTS.md — 模块2_对话服务

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容。

> ⚠️ 【占位状态】本文件为 H6 任务占位骨架，基于 backend 现有业务边界人工建立。**待 s0203 拓扑化拆分 Skill 触发后由 s0301 重生成**，届时将以正式模块拆分结果替换本占位内容。

---

## 一、模块定位

**模块编号**：模块2_对话服务
**模块职责**：流式/非流式对话、SSE/WS 推送、ThinkTagStreamParser、上下文回溯、max_tool_rounds 统一
**对应 backend 文件**：
- `backend/api/routers/chat.py` — 非流式对话路由（含 D4 死代码移除、D5 max_tool_rounds 统一）
- `backend/api/routers/stream.py` — 流式对话路由（含 C4 流式取消传播）
- `backend/api/routers/websocket.py` — WebSocket 路由
- `backend/core/chat/` — 对话核心逻辑
- `backend/core/websocket/manager.py` — WebSocketManager（B7 字典并发修改修复）

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束，特别是：

- **public/ 保护指令**：`public/` 目录是契约物理载体，任何删除/修改/覆盖/移动操作必须先经人类显式授权。
- **禁止模块间直接导入**：模块间仅允许依赖 `public/` 下的契约。
- **D1 ServiceState + Depends 模式**：通过 `Depends(get_service_state)` 获取服务实例。
- **D4 移除 ThinkTagStreamParser 重复**：grep `ThinkTagStreamParser` 仅 stream.py 定义 + import。
- **D5 统一 max_tool_rounds**：流式与非流式一致（10 或 `settings.config.llm.max_tool_rounds`）。

---

## 三、模块专属约束

### 3.1 可修改文件范围

- `backend/api/routers/{chat,stream,websocket}.py`
- `backend/core/chat/*.py`
- `backend/core/websocket/manager.py`

### 3.2 依赖契约

- 数据契约：`public/schema/message.json`
- 接口契约：`public/interface_stub/chat_service.pyi`
- 配置契约：`public/config_template/llm_config.json`（含 max_tool_rounds）

### 3.3 关键修复点（B6/B7/B9/C1/C4/D4/D5）

- B6: VLLMClient 移除 _http_lock，仅用 _semaphore（max_concurrent=4）
- B7: WebSocketManager.broadcast 迭代前 snapshot：`list(self.connections.items())`
- B9: 前端 API 客户端写操作禁用自动重试（前端任务，由 G6 覆盖）
- C1: VLLMClient 统一 httpx.AsyncClient，移除 requests + asyncio.to_thread
- C4: 流式响应取消传播，客户端断开时主动 aclose() 上游 vLLM 流
- D4: 移除 chat.py 中 ThinkTagStreamParser 死代码副本，统一用 stream.py 版本
- D5: max_tool_rounds 流式与非流式统一

### 3.4 测试要求

- 单元测试：`tests/units/test_llm_client.py`、`test_websocket_manager.py`
- 集成测试：`tests/simulation/scenarios/test_stream_cancel.py`、`test_long_conversation_100.py`、`test_concurrent_chat.py`、`test_basic_chat.py`、`test_multi_turn_context.py`

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 修复记录：`.trae/documents/20260702_模块1_*.md`
