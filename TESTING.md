# CXHMS 测试文档

## 测试架构概览

本项目包含完整的测试套件，覆盖前端和后端的所有主要功能。测试结构按 AC范式v6 规范组织：
后端测试位于 `tests/`，契约测试位于 `public/test_cases/`，前端测试位于 `frontend/src/`，Playwright E2E 位于 `frontend/e2e/`。

## 前端测试

### 测试框架
- **Vitest**: 单元测试框架
- **jsdom**: DOM 测试环境
- **@testing-library/jest-dom**: DOM 断言库

### 测试文件

API 域测试（按域拆分，覆盖 client.ts 基础设施 + 各业务域）：

| 文件 | 描述 |
|------|------|
| `frontend/src/api/client.test.ts` | client.ts 基础设施测试（health / control / admin / Base URL / B9 写操作不重试） |
| `frontend/src/api/memory.test.ts` | 记忆 CRUD / 搜索 / 归档 / 批量 / 记忆聊天 |
| `frontend/src/api/chat.test.ts` | 聊天 / Session / History / B9 写方法契约 |
| `frontend/src/api/chatStream.test.ts` | 流式聊天 SSE 解析 |
| `frontend/src/api/agent.test.ts` | Agent / Tools / ACP（含 G4 updateTool 对齐 PUT 端点） |

组件与状态测试：

| 文件 | 描述 |
|------|------|
| `frontend/src/store/chatStore.test.ts` | 聊天状态管理 |
| `frontend/src/store/themeStore.test.ts` | 主题状态管理 |
| `frontend/src/components/Header.test.tsx` | Header 组件 |
| `frontend/src/components/ErrorBoundary.test.tsx` | ErrorBoundary 错误边界 |
| `frontend/src/components/AppLayout.test.tsx` | AppLayout 布局 |
| `frontend/src/components/RouteErrorBoundary.test.tsx` | 路由错误边界 |
| `frontend/src/App.test.tsx` | 路由懒加载与错误边界 |
| `frontend/src/pages/ChatPage.test.tsx` | 聊天页面集成 |
| `frontend/src/hooks/useWebSocket.test.ts` | WebSocket hook |

### 运行前端测试

```bash
cd frontend

# 安装依赖
npm install

# 运行测试（一次性）
npm test -- --run

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

### 测试结构

```
tests/
├── conftest.py                  # 全局 fixtures（10 个：fakes / sim_app / sim_client / sim_actor / vllm_available / real_app / real_actor 等）
├── fakes/                       # 确定性假实现（零外部依赖）
│   ├── __init__.py
│   ├── fake_embedding.py        # FakeEmbeddingModel（256 维 n-gram + sha1 哈希 + L2 归一化）
│   ├── fake_vector_store.py     # InMemoryVectorStore（真实余弦相似度 + 线程安全）
│   ├── fake_llm.py              # FakeLLMClient + FakeModelRouter（脚本化回复 / 流式 / 工具调用）
│   └── fake_graph.py            # InMemoryGraphStore + InMemoryGraphDatabase
├── units/                       # 后端单元测试（87 项，覆盖 B1-B8 回归 + C1-C5 性能优化）
│   ├── test_fakes_smoke.py
│   ├── test_fixtures_smoke.py
│   ├── test_memory_manager.py   # B2/B3/B4 回归
│   ├── test_async_manager.py    # B1 初始化
│   ├── test_context_manager.py  # C3 增量持久化
│   ├── test_llm_client.py       # B6 锁竞态 + C1 并发
│   ├── test_hybrid_search.py    # B5 agent 隔离
│   ├── test_router.py           # B8 上界 + D5 max_tool_rounds
│   └── test_websocket_manager.py # B7 字典并发
├── simulation/scenarios/        # 行为测试（47 项，覆盖 C4 流式取消 / B4 并发隔离 / C3 长对话 / B5 HybridSearch / C5 3D 排序 + C6 FTS5 中文分词）
│   ├── test_basic_chat.py
│   ├── test_multi_turn_context.py
│   ├── test_memory_write_search.py  # C6 FTS5 trigram 中文分词（3 个原 xfail 已转 passed）
│   ├── test_tool_calling.py
│   ├── test_memory_agent_chat.py
│   ├── test_concurrent_chat.py
│   ├── test_long_conversation.py
│   ├── test_semantic_search.py
│   ├── test_stream_cancel.py              # C4 流式取消
│   ├── test_concurrent_isolation.py       # B4 并发隔离
│   ├── test_long_conversation_100.py      # C3 长对话
│   ├── test_hybrid_search_agent_isolation.py # B5 HybridSearch 隔离
│   └── test_3d_search_ranking.py          # C5 3D 搜索排序
├── contracts/                   # 契约测试（三层契约校验，416 项）
│   ├── test_data_schema.py      # 数据契约校验（jsonschema）
│   ├── test_interface_stub.py   # 接口契约签名匹配（.pyi 存根）
│   └── test_config_template.py  # 配置契约默认值填充
└── e2e/                         # 端到端测试（12 项，标记 slow，依赖真实 vLLM）
    ├── test_chat_flow.py        # 非流式 / 流式 / 多轮上下文 / 历史回溯
    ├── test_memory_lifecycle.py # 写入搜索 / 标签 / 时间范围 / decay_score / 删除404
    └── test_agent_isolation.py # 记忆隔离 / 上下文隔离 / memory-agent 流式
```

### conftest.py 全局 fixtures

| Fixture | 作用域 | 描述 |
|---------|--------|------|
| `sim_app` | function | 设置 CXHMS_SIMULATION=1、重置单例、yield TestClient(app) |
| `sim_client` | function | 依赖 sim_app，返回 TestClient |
| `sim_actor` | function | 依赖 sim_client，返回 SimUserActor |
| `vllm_available` | session | 探测真实 vLLM 服务可用性，不可用则 skip slow 测试 |
| `real_app` | session | 不设 CXHMS_SIMULATION 的真实 app（依赖真实 vLLM） |
| `real_actor` | session | SimUserActor 包裹 real_app |

### 运行后端测试

```bash
# 运行默认测试套件（不含 slow）
python -m pytest

# 运行特定目录
python -m pytest tests/units/ -v
python -m pytest tests/simulation/scenarios/ -v
python -m pytest tests/contracts/ -v

# 运行契约测试（public/test_cases/）
python -m pytest public/test_cases/ -v

# 按标记运行
python -m pytest -m "not slow"    # 默认，跳过慢速 E2E
python -m pytest -m slow           # 仅运行 slow E2E（依赖真实 vLLM）
python -m pytest -m unit           # 仅单元测试
python -m pytest -m integration    # 仅集成测试

# 运行全量（含 slow）
python -m pytest tests/

# 生成覆盖率报告
python -m pytest --cov=backend --cov-report=html
```

## 契约测试

### 概述

契约测试位于 `public/test_cases/`，校验三层契约（数据 / 接口 / 配置）的符合性。GN-004 交付前审查依赖此套件验证 D6.5 闭合信号。

### 测试文件

| 文件 | 描述 |
|------|------|
| `public/test_cases/test_data_schema.py` | 数据契约校验（jsonschema，14 项） |
| `public/test_cases/test_interface_stub.py` | 接口契约签名匹配（.pyi 存根，11 项） |
| `public/test_cases/test_config_template.py` | 配置契约默认值填充（9 项） |
| `public/test_cases/rubric.md` | 合规 rubric（通过 / 失败判据清单） |

### 运行契约测试

```bash
python -m pytest public/test_cases/ -v
```

## Playwright 前端 E2E 测试

### 概述

Playwright E2E 测试位于 `frontend/e2e/`，覆盖真实 React UI 渲染与流式聊天交互。测试启动时自动串起两个 webServer：模拟后端（FastAPI + FakeLLMClient）+ Vite 前端。

### 测试文件

| 文件 | 描述 |
|------|------|
| `frontend/e2e/chat.spec.ts` | 流式聊天 UI 渲染、多轮上下文保持、新会话清空上下文 |
| `frontend/e2e/memory_agent.spec.ts` | 记忆 agent 页面加载、聊天响应 |

### 运行 Playwright 测试

```bash
cd frontend

# 安装 Playwright 浏览器（首次运行前）
npx playwright install chromium

# 运行 E2E（自动启动模拟后端 + Vite 前端）
npx playwright test --project=chromium

# 有头模式（可视化调试）
npm run e2e:headed
```

### 配置

`frontend/playwright.config.ts` 配置了两个 webServer：
1. 模拟后端：`CXHMS_SIMULATION=1` 环境变量启动 `uvicorn backend.api.app:app`
2. Vite 前端：`npm run dev`（端口 3000，已配置 `/api`、`/health`、`/ws` 代理到 8001）

由于模拟后端是单例（内存状态），强制 `workers: 1` 与 `fullyParallel: false` 避免并发请求互相污染上下文。

## 模拟化端到端测试

### 概述

模拟化 E2E 测试系统补齐了"单元测试之上、真实端到端之下"的集成测试死区：用确定性的假实现替换所有外部依赖（LLM、向量库、嵌入模型、图数据库），驱动真实 FastAPI 应用执行完整用户操作流程，在 CI 中零外部依赖运行。

### 特性

- **零外部依赖**：不连接 vLLM/Ollama/Chroma/Milvus/SQLite 图数据库，CI 可直接运行
- **真实业务路径**：所有请求命中真实 FastAPI 路由与业务逻辑，仅在 `lifespan` 通过 `CXHMS_SIMULATION=1` 装配假实现
- **确定性**：FakeLLMClient 基于关键词规则，FakeEmbeddingModel 基于 n-gram 哈希，相同输入永远产生相同输出
- **语义性**：FakeEmbeddingModel 的 n-gram 词袋使"我喜欢猫"与"我喜爱猫咪"余弦相似度高于无关文本，让向量检索在测试中真实有效
- **隔离性**：每个测试函数通过 `sim_app` fixture 重置 `MemoryManager` 单例与图注册表，互不污染

### 模拟依赖包

位于 `tests/fakes/`（详见上表）。

### 无头用户演员

`SimUserActor(client)` 以业务语义封装真实前端对后端的调用：

- `send_message(message, agent_id)` — 非流式 POST /api/chat
- `send_streaming_message(message, agent_id)` — 流式 POST /api/chat/stream，聚合 SSE
- `memory_agent_chat(message)` — POST /api/memory-agent/chat/stream
- `search_memory(query, ...)` — POST /api/memories/search
- `list_agents()` / `create_agent(payload)` / `list_tools()` / `get_history(session_id)`

### 端到端冒烟脚本

`scripts/smoke_e2e.py`：模拟前端完成 10 步骤全链路冒烟（I2 闭合产物），用于验证前后端集成无回归。

```bash
python scripts/smoke_e2e.py
```

### 环境变量

| 变量 | 取值 | 作用 |
|------|------|------|
| `CXHMS_SIMULATION` | `1` | 触发 `lifespan` 模拟分支，装配假实现而非真实外部客户端 |

## 测试配置

### 前端配置 (`frontend/vitest.config.ts`)

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
testpaths = tests public/test_cases
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    -ra
markers =
    asyncio: Async test marker
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

### 后端单元测试示例

```python
import pytest
from fastapi.testclient import TestClient

def test_my_endpoint(sim_client: TestClient):
    """Test my endpoint using sim_client fixture."""
    response = sim_client.get("/api/my-endpoint")
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

### 后端契约测试示例

```python
def test_my_interface_matches_stub():
    """校验 backend 实现匹配 public/interface_stub/ 下的 .pyi 存根。"""
    from public.interface_stub.my_service import MyService
    from backend.api.routers.my_router import my_endpoint
    # 签名匹配校验...
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

      - name: Install backend deps
        run: pip install -r requirements.txt

      - name: Install frontend deps
        run: cd frontend && npm install

      - name: Run backend tests
        run: python -m pytest -m "not slow"

      - name: Run contract tests
        run: python -m pytest public/test_cases/

      - name: Run frontend tests
        run: cd frontend && npm test -- --run
```

## 测试状态

- ✅ 后端单元测试：8 个文件（87 项，覆盖 B1-B8 回归 + C1-C5 性能优化）
- ✅ 后端行为测试：13 个场景文件（47 项，覆盖 C4/B4/C3/B5/C5 + C6 FTS5 中文分词）
- ✅ 后端契约测试：3 个文件（416 项，三层契约校验）
- ✅ 后端 E2E 测试：3 个文件（12 项，标记 slow，依赖真实 vLLM）
- ✅ 前端单元测试：19 个文件（299 项）
- ✅ Playwright E2E：2 个文件（5 项 + 1 skip）
- ✅ 端到端冒烟脚本：scripts/smoke_e2e.py（10 步骤全绿）

### 默认测试套件

```bash
# 后端默认（不含 slow）
python -m pytest -m "not slow"
# 预期：587 passed, 1 skipped, 0 failed

# 前端默认
cd frontend && npm test -- --run
# 预期：19 files, 299 passed, 0 failed

# 契约测试
python -m pytest public/test_cases/
# 预期：34 passed
```
