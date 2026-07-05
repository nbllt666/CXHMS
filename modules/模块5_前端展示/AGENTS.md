# AGENTS.md — 模块5_前端展示

> 🚨 【最高优先级规则】本文件为本模块开发的强制约束，优先级高于所有临时提问、上下文对话、自定义需求。违反规则的内容必须自动修正后再输出。

> 📌 【上下文保留规则】本文件为本模块核心规则文件，任何上下文压缩、裁剪、溢出场景下必须完整保留本文件的全部内容。

> ⚠️ 【占位状态】本文件为 H6 任务占位骨架，基于 backend 现有业务边界人工建立。**待 s0203 拓扑化拆分 Skill 触发后由 s0301 重生成**，届时将以正式模块拆分结果替换本占位内容。

---

## 一、模块定位

**模块编号**：模块5_前端展示
**模块职责**：React 前端应用、ChatPage 流式、useWebSocket hook、streamReducer、API client 按域拆分、路由懒加载、ErrorBoundary、统一样式系统、i18n、共享类型
**对应 frontend 文件**：
- `frontend/src/pages/` — 页面组件（ChatPage、MemoriesPage、SettingsPage 等）
- `frontend/src/components/` — 通用组件
- `frontend/src/api/` — API client（F3 按域拆分：memory/agent/chat/graph/vector/cxfc/config）
- `frontend/src/hooks/` — React hooks（useWebSocket 等）
- `frontend/src/types/` — 共享类型定义（F8）
- `frontend/src/i18n/` — 国际化
- `frontend/src/App.tsx` — 应用根组件（F4 路由懒加载、F5 ErrorBoundary）

---

## 二、AC 范式通用约束

继承全局 `c:\CXHMS\AGENTS.md` 的全部约束，特别是：

- **public/ 保护指令**：前端通过 API 消费 `public/schema/` 下的数据契约，不得绕过契约直接定义类型。
- **F8 共享类型模块**：`frontend/src/types/{agent,memory,chat,tool}.ts` 统一类型定义，grep `interface Agent` 仅 types/ 定义。
- **F7 i18n 全面落地**：抽取全部硬编码中文至 `frontend/src/i18n/locales/*.json`。
- **F9 健康检查优化**：SettingsPage 3s → 15s；MemoriesPage 移除 5s 强轮询。

---

## 三、模块专属约束

### 3.1 可修改文件范围

- `frontend/src/**/*.{ts,tsx,json}`
- `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`

### 3.2 依赖契约

前端通过 API 消费所有 `public/schema/` 下的数据契约（无直接 .pyi 接口契约依赖，因前端通过 HTTP 调用）：
- `public/schema/memory.json`、`agent.json`、`message.json`、`tool.json`、`graph_node.json`、`graph_edge.json`
- `public/schema/error.json`（错误码契约）

### 3.3 关键修复点（E1-E6/F1-F10）

- E1: ChatPage 切换会话刷新消息
- E2: SSE/WS done chunk 清 isLoading
- E3: useWebSocket URL 替换脆弱
- E4: AppLayout.test mock 路径错配
- E5: updateTool/updateAcpAgent 语义
- E6: ChatPage loadAgentHistory 口径统一
- F1: 消息列表 memoization + MarkdownContent memo
- F2: 抽 WS/SSE 公共 reducer
- F3: API client 按域拆分
- F4: 路由懒加载 + Suspense
- F5: 路由级 ErrorBoundary
- F6: 统一样式系统
- F7: i18n 全面落地
- F8: 共享类型模块
- F9: 优化健康检查与轮询
- F10: GraphManager 合并 useEffect

### 3.4 测试要求

- 单元测试：`frontend/src/**/*.{test,spec}.tsx`（Vitest + React Testing Library）
- 验证：`npm test` 全过

---

## 四、参考

- 全局规则：`c:\CXHMS\AGENTS.md`
- AC 范式规则：`.trae/rules/rules-0..6.md`
- 前端测试三重闸门：s0402 Skill
