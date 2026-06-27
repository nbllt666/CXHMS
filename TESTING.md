# CXHMS 测试文档

## 测试架构概览

本项目包含完整的测试套件，覆盖前端和后端的所有主要功能，并包含 LLM 端到端质量评判框架。

## 前端测试

### 测试框架
- **Vitest**: 单元测试框架
- **jsdom**: DOM 测试环境
- **@testing-library/jest-dom**: DOM 断言库

### 测试文件

| 文件 | 描述 |
|------|------|
| `frontend/src/api/client.test.ts` | API 客户端测试 |
| `frontend/src/store/chatStore.test.ts` | 聊天状态管理测试 |
| `frontend/src/store/themeStore.test.ts` | 主题状态管理测试 |
| `frontend/src/components/Header.test.tsx` | Header 组件测试 |
| `frontend/src/components/ErrorBoundary.test.tsx` | ErrorBoundary 组件测试 |
| `frontend/src/components/AppLayout.test.tsx` | AppLayout 组件测试 |

### 运行前端测试

```bash
cd frontend

# 安装依赖
npm install

# 运行测试
npm test

# 监视模式
npm run test:watch

# 生成覆盖率报告
npm run test:coverage
```

## 后端测试

### 测试框架
- **pytest**: Python 测试框架
- **pytest-asyncio**: 异步测试支持（asyncio_mode = auto）
- **FastAPI TestClient**: API 测试客户端
- **httpx**: 异步 HTTP 客户端（性能测试 & LLM E2E）

### 测试结构

```
backend/tests/
├── conftest.py              # 测试配置和fixtures（client, async_client, mock_settings）
├── performance_test.py      # 性能测试（httpx异步基准，非pytest标准格式）
├── test_memory_manager.py   # 记忆管理器基础测试
├── test_thread_safety.py    # 线程安全测试
├── test_tool_calling.py     # 工具调用测试
├── test_api/                # API端点测试（8个文件）
│   ├── test_agents.py       # Agent API测试
│   ├── test_archive.py      # 归档API测试
│   ├── test_backup.py       # 备份API测试
│   ├── test_chat.py         # 聊天API测试
│   ├── test_context.py      # 上下文API测试
│   ├── test_health.py       # 健康检查测试
│   ├── test_memory.py       # 记忆API测试
│   └── test_tools.py        # 工具API测试
├── test_core/               # 核心模块测试（6个文件）
│   ├── test_chroma_store.py # Chroma向量存储测试
│   ├── test_hybrid_search.py# 混合搜索测试
│   ├── test_llm_client.py   # LLM客户端测试
│   ├── test_memory_manager.py# 记忆管理器测试
│   ├── test_utils.py        # 工具函数测试
│   └── test_vector_sync.py  # 向量同步测试
├── test_integration/        # 集成测试
│   └── test_chat_flow.py    # 聊天流程测试
└── llm_e2e/                 # LLM端到端测试框架（8个文件）
    ├── config.py            # 测试配置（TestConfig, CXHMS_TEST_前缀环境变量）
    ├── client.py            # CXHMS API客户端（httpx异步，支持流式）
    ├── judge.py             # LLM评判代理（vLLM + gemma4）
    ├── judge_tools.py       # 评判工具定义（OpenAI function calling格式）
    ├── scenarios.py         # 内置测试场景
    ├── runner.py            # 测试运行器（TestRunner, StepResult, ScenarioResult）
    ├── metrics.py           # 性能指标收集器
    ├── report.py            # 报告生成器（控制台+JSON）
    └── main.py              # 主入口脚本
```

### conftest.py 配置

**Fixtures:**
- `client` — 基于 session 的 `TestClient`，用于同步 API 测试
- `async_client` — 基于 session 的 `AsyncClient`，用于异步 API 测试
- `mock_settings` — 函数级 fixture，用于模拟应用设置

**atexit 清理:**
- `_restore_agents()` — 恢复 `agents.json` 备份
- `_cleanup_alarm_manager()` — 重置闹钟管理器

### 运行后端测试

```bash
# 运行所有测试
python -m pytest backend/tests -v

# 运行特定模块
python -m pytest backend/tests/test_api -v
python -m pytest backend/tests/test_core -v
python -m pytest backend/tests/test_integration -v

# 按标记运行
python -m pytest -m unit          # 只运行单元测试
python -m pytest -m api           # 只运行API测试
python -m pytest -m integration   # 只运行集成测试
python -m pytest -m "not slow"    # 跳过慢速测试

# 生成覆盖率报告
python -m pytest backend/tests --cov=backend --cov-report=html

# 使用 pytest.ini 配置
python -m pytest
```

## LLM 端到端测试

### 概述

LLM E2E 测试框架独立于 pytest 运行，用于自动化评估 CXHMS 的对话质量。它使用 vLLM + gemma4 作为评判代理，通过 OpenAI function calling 格式定义评判工具，自动对聊天响应进行质量评判。

### 特性

- 独立于 pytest 运行，不依赖 pytest 框架
- 使用 vLLM + gemma4 作为评判代理
- 支持自动化质量评判（基于预定义场景）
- 包含性能指标收集（响应时间、首 token 时间等）
- 生成控制台摘要 + JSON 详细报告
- 通过 `CXHMS_TEST_` 前缀环境变量配置

### 运行 LLM E2E 测试

```bash
cd backend/tests/llm_e2e
python main.py
```

### 框架组件

| 文件 | 描述 |
|------|------|
| `config.py` | 测试配置（`TestConfig` 类，`CXHMS_TEST_` 前缀环境变量） |
| `client.py` | CXHMS API 客户端（httpx 异步，支持流式响应） |
| `judge.py` | LLM 评判代理（vLLM + gemma4） |
| `judge_tools.py` | 评判工具定义（OpenAI function calling 格式） |
| `scenarios.py` | 内置测试场景定义 |
| `runner.py` | 测试运行器（`TestRunner`, `StepResult`, `ScenarioResult`） |
| `metrics.py` | 性能指标收集器 |
| `report.py` | 报告生成器（控制台摘要 + JSON 详细报告） |

## 模拟化端到端测试

### 概述

模拟化 E2E 测试系统补齐了"单元测试之上、真实端到端之下"的集成测试死区：用确定性的假实现替换所有外部依赖（LLM、向量库、嵌入模型、图数据库、前端），驱动**真实 FastAPI 应用**执行完整用户操作流程，在 CI 中零外部依赖运行。

与 `llm_e2e/`（依赖真实 vLLM + 真实模型，CI 无法运行）互补：本套件验证**业务逻辑集成**（路由、状态管理、上下文持久化、工具调用循环、记忆写入检索等），`llm_e2e/` 验证**对话质量**。

### 特性

- **零外部依赖**：不连接 vLLM/Ollama/Chroma/Milvus/SQLite 图数据库，CI 可直接运行
- **真实业务路径**：所有请求命中真实 FastAPI 路由与业务逻辑，仅在 `lifespan` 通过 `CXHMS_SIMULATION=1` 装配假实现
- **确定性**：FakeLLMClient 基于关键词规则，FakeEmbeddingModel 基于 n-gram 哈希，相同输入永远产生相同输出
- **语义性**：FakeEmbeddingModel 的 n-gram 词袋使"我喜欢猫"与"我喜爱猫咪"余弦相似度高于无关文本，让向量检索在测试中真实有效
- **隔离性**：每个测试函数通过 `sim_app` fixture 重置 `MemoryManager` 单例与图注册表，互不污染
- **双轨前端覆盖**：Python 无头用户演员（`SimUserActor`）覆盖后端集成；Playwright 覆盖真实 React UI 渲染

### 模拟依赖包

位于 `backend/tests/simulation/fakes/`：

| 文件 | 描述 |
|------|------|
| `fake_embedding.py` | `FakeEmbeddingModel`（实现 `EmbeddingModel` ABC），256 维字符 n-gram + sha1 哈希分桶 + L2 归一化 |
| `fake_vector_store.py` | `InMemoryVectorStore`（实现 `VectorStoreBase` ABC），内存 list + 真实余弦相似度 + 线程安全 |
| `fake_llm.py` | `FakeLLMClient`（实现 `LLMClient` ABC）+ `FakeModelRouter`，支持脚本化回复/流式/工具调用/上下文感知 |
| `fake_graph.py` | `InMemoryGraphStore`（实现 `GraphStoreBase` ABC）+ `InMemoryGraphDatabase` + `make_in_memory_graph_store()` |

### 无头用户演员

`backend/tests/simulation/actor.py` 提供 `SimUserActor(client)`，以业务语义封装真实前端对后端的调用：

- `send_message(message, agent_id)` — 非流式 POST /api/chat
- `send_streaming_message(message, agent_id)` — 流式 POST /api/chat/stream，聚合 SSE 为 `{session_id, content, thinking, tool_calls, tool_results, events, raw, error}`
- `memory_agent_chat(message)` — POST /api/memory-agent/chat/stream
- `search_memory(query, ...)` — POST /api/memories/search
- `list_agents()` / `create_agent(payload)` / `list_tools()` / `get_history(session_id)`

### 端到端场景套件

位于 `backend/tests/simulation/scenarios/`（8 个文件，30 个测试用例，约 5 秒运行完毕）：

| 文件 | 覆盖死区 |
|------|----------|
| `test_basic_chat.py` | 基础聊天响应内容（非仅状态码）、流式聚合、thinking chunk、session_id |
| `test_multi_turn_context.py` | 多轮上下文保持（"我叫X"→"我叫什么"返回"你叫X"）、上一条消息回显 |
| `test_memory_write_search.py` | POST /api/memories 写入 → /api/memories/search 命中、memory_type 过滤 |
| `test_tool_calling.py` | 工具触发（calculator/datetime）、参数正确性、结果整合、无工具时不触发 |
| `test_memory_agent_chat.py` | /api/memory-agent/chat/stream 流程、thinking、session 稳定性 |
| `test_concurrent_chat.py` | 多 agent_id 并发不串扰、顺序会话隔离 |
| `test_long_conversation.py` | 50+ 轮混合交互稳定性、上下文不丢失、响应不退化、流式长对话 |
| `test_semantic_search.py` | FakeEmbedding 语义性、向量库 ranking、min_score 过滤、API 语义搜索 |

### Playwright 前端测试

位于 `frontend/e2e/`（2 个文件，5 个测试用例 + 1 个 skip，约 15 秒运行完毕）：

| 文件 | 覆盖死区 |
|------|----------|
| `chat.spec.ts` | 流式聊天 UI 渲染、多轮上下文保持、新会话清空上下文 |
| `memory_agent.spec.ts` | 记忆 agent 页面加载、聊天响应（agent 切换因 UI 无该组件而 skip） |

`frontend/playwright.config.ts` 配置了两个 `webServer`，测试启动时自动串起：
1. 模拟后端：`python -m backend.tests.simulation.server --host 127.0.0.1 --port 8001`
2. Vite 前端：`npm run dev`（端口 3000，已配置 `/api`、`/health`、`/ws` 代理到 8001）

### 运行模拟测试

```bash
# 后端模拟套件（零外部依赖，约 5 秒）
cd c:\CXHMS
python -m pytest backend/tests/simulation/ -v

# 仅运行场景套件
python -m pytest backend/tests/simulation/scenarios/ -v

# 启动模拟后端服务器（手动测试或供 Playwright 连接）
python -m backend.tests.simulation.server --host 127.0.0.1 --port 8001

# Playwright 前端测试（自动启动模拟后端 + Vite 前端，约 15 秒）
cd frontend
npx playwright test --project=chromium

# Playwright 有头模式（可视化调试）
npm run e2e:headed

# 安装 Playwright 浏览器（首次运行前）
npx playwright install chromium
```

### conftest.py 模拟 fixtures

| Fixture | 作用域 | 描述 |
|---------|--------|------|
| `sim_app` | function | 设置 `CXHMS_SIMULATION=1`、重置 `MemoryManager` 单例与图注册表、yield `TestClient(app)`、teardown 清理 |
| `sim_client` | function | 依赖 `sim_app`，返回 `TestClient` |
| `sim_actor` | function | 依赖 `sim_client`，返回 `SimUserActor(sim_client)` |

### 环境变量

| 变量 | 取值 | 作用 |
|------|------|------|
| `CXHMS_SIMULATION` | `1` | 触发 `lifespan` 模拟分支，装配假实现而非真实外部客户端 |

## 统一测试运行器

使用 `run_tests.py` 运行所有测试：

```bash
# 运行所有测试
python run_tests.py

# 只运行前端测试
python run_tests.py --frontend-only

# 只运行后端测试
python run_tests.py --backend-only

# 带覆盖率报告
python run_tests.py --coverage

# 运行特定测试
python run_tests.py --test backend/tests/test_api/test_health.py
```

### 数据保护

`run_tests.py` 在运行测试前自动备份关键数据文件，测试完成后恢复：

- **备份目录**: `.test_backup/`
- **备份文件**:
  - `cxhms.db`
  - `memories.db`
  - `sessions.db`
  - `milvus_lite.db`
  - `agents.json`
  - `acp/`

## 测试覆盖范围

### 前端测试覆盖

1. **API 客户端** (`client.test.ts`)
   - 健康检查
   - 聊天 API
   - Agent API
   - 记忆 API
   - 错误处理

2. **状态管理** (`chatStore.test.ts`, `themeStore.test.ts`)
   - 初始状态验证
   - 状态更新操作
   - 异步操作
   - 错误处理
   - 本地存储持久化

3. **组件测试** (`Header.test.tsx`, `ErrorBoundary.test.tsx`, `AppLayout.test.tsx`)
   - Header 组件渲染与交互
   - ErrorBoundary 错误边界捕获
   - AppLayout 布局组件渲染

### 后端测试覆盖

1. **API 测试** (`test_api/` - 8个文件)
   - 健康检查端点 (`test_health.py`)
   - 聊天端点 (`test_chat.py`) - 发送消息、流式响应、历史记录
   - Agent 端点 (`test_agents.py`) - CRUD 操作
   - 归档端点 (`test_archive.py`) - 归档操作
   - 备份端点 (`test_backup.py`) - 备份操作
   - 上下文端点 (`test_context.py`) - 上下文管理
   - 记忆端点 (`test_memory.py`) - CRUD、搜索、统计
   - 工具端点 (`test_tools.py`) - 工具调用
   - 参数验证
   - 错误处理

2. **核心模块测试** (`test_core/` - 6个文件)
   - Chroma 向量存储 (`test_chroma_store.py`) - 向量存储操作
   - 混合搜索 (`test_hybrid_search.py`) - 混合搜索功能
   - LLM 客户端 (`test_llm_client.py`) - LLM 调用与响应
   - 记忆管理器 (`test_memory_manager.py`) - 添加、获取、更新、删除
   - 工具函数 (`test_utils.py`) - 通用工具函数
   - 向量同步 (`test_vector_sync.py`) - 向量同步操作

3. **根级测试** (3个文件)
   - 记忆管理器测试 (`test_memory_manager.py`) - 记忆管理器基础测试
   - 线程安全测试 (`test_thread_safety.py`) - 并发安全验证
   - 工具调用测试 (`test_tool_calling.py`) - 工具调用流程

4. **性能测试** (1个文件)
   - 性能测试 (`performance_test.py`) - httpx 异步基准测试（非 pytest 标准格式）

5. **集成测试** (`test_integration/` - 1个文件)
   - 端到端聊天流程 (`test_chat_flow.py`)
   - 多端点协调
   - API 文档访问

## 测试配置

### 前端配置 (`vitest.config.ts`)

```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: ['node_modules/', 'src/test/', '**/*.d.ts', '**/*.config.*', '**/mockData.ts'],
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
});
```

### 后端配置 (`pytest.ini`)

```ini
[pytest]
asyncio_mode = auto
testpaths = backend/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short --strict-markers -ra
markers =
    asyncio: asyncio tests
    unit: Unit tests
    integration: Integration tests
    api: API tests
    slow: Slow tests
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

## 编写新测试

### 前端测试示例

```typescript
import { describe, it, expect } from 'vitest'
import { myFunction } from './myModule'

describe('MyModule', () => {
  it('should do something', () => {
    const result = myFunction()
    expect(result).toBe('expected')
  })
})
```

### 后端测试示例

```python
import pytest
from fastapi.testclient import TestClient

def test_my_endpoint(client: TestClient):
    """Test my endpoint."""
    response = client.get("/api/my-endpoint")
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

## 持续集成建议

在 CI/CD 管道中运行测试：

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Run all tests
        run: python run_tests.py
```

## 测试状态

- ✅ 前端测试: 6 个测试文件
- ✅ 后端 API 测试: 8 个测试文件
- ✅ 后端核心测试: 6 个测试文件
- ✅ 后端根级测试: 3 个测试文件（test_tool_calling, test_thread_safety, test_memory_manager）
- ✅ 性能测试: 1 个文件
- ✅ 集成测试: 1 个文件
- ✅ LLM E2E 测试: 8 个文件（依赖真实栈，CI 不可运行）
- ✅ 模拟化 E2E 测试: 8 个场景文件（30 个测试用例，零外部依赖，约 5 秒）+ 2 个 Playwright 前端测试文件（5 个用例 + 1 skip，约 15 秒）

总计: **19 个后端测试文件 + 6 个前端测试文件 + LLM E2E 框架 + 模拟化 E2E 套件（8 后端场景 + 2 Playwright）** 覆盖所有主要功能模块
