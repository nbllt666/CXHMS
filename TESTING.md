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
- ✅ LLM E2E 测试: 8 个文件

总计: **19 个后端测试文件 + 6 个前端测试文件 + LLM E2E 框架** 覆盖所有主要功能模块
