# CXHMS 测试工具集

CXFC 插件系统与 ACP 协议的独立测试工具，基于 Python + Streamlit 实现。

## 目录结构

```
tests/test_tools/
├── __init__.py
├── launch.py              # 统一启动入口
├── README.md              # 本文件
├── common/
│   ├── __init__.py
│   └── api_client.py      # 主系统 HTTP 客户端封装（CXFC/ACP/MCP API）
├── cxfc/                  # CXFC 测试工具
│   ├── __init__.py
│   ├── app.py             # Streamlit UI（3个Tab）
│   ├── mock_plugin_server.py  # 模拟 CXFC 插件服务
│   └── preset_tools.py    # 预置工具与 skills 定义
├── acp/                   # ACP 聊天客户端
│   ├── __init__.py
│   ├── app.py             # Streamlit UI（4个Tab）
│   ├── acp_node.py        # 独立 ACP 节点
│   ├── message_server.py  # HTTP 消息接收服务器
│   ├── message_client.py  # HTTP 消息发送客户端
│   └── udp_discovery.py   # UDP 发现模块
└── mcp/                   # MCP 测试工具
    ├── __init__.py
    ├── app.py             # Streamlit UI（3个Tab）
    ├── mock_mcp_server.py # 模拟 MCP 服务器
    └── preset_tools.py    # 预置工具定义与执行逻辑
```

## 依赖

- Python 3.10+
- streamlit
- httpx
- fastapi
- uvicorn

安装依赖：

```bash
pip install streamlit httpx fastapi uvicorn
```

## 前置条件

主系统（CXHMS 后端）需运行，默认地址 `http://localhost:8001`。启动方式：

```bash
# 在项目根目录
python main.py
```

## 启动方式

### 方式一：统一启动入口

```bash
# 启动 CXFC 测试工具（端口 8501）
python tests/test_tools/launch.py cxfc

# 启动 ACP 聊天工具（端口 8502）
python tests/test_tools/launch.py acp

# 启动 MCP 测试工具（端口 8504）
python tests/test_tools/launch.py mcp

# 无参数打印使用说明
python tests/test_tools/launch.py
```

### 方式二：直接用 streamlit 命令

```bash
streamlit run tests/test_tools/cxfc/app.py --server.port=8501
streamlit run tests/test_tools/acp/app.py --server.port=8502
streamlit run tests/test_tools/mcp/app.py --server.port=8504
```

启动后浏览器自动打开对应页面。

## CXFC 测试工具

三个 Tab：

1. **模拟插件**：配置插件名称/端口/心跳间隔/能力 → 启动模拟 FastAPI 服务 → 自动注册到主系统并维持心跳 → 查看事件日志
2. **插件管理**：刷新插件列表、发现插件、手动连接、删除插件、刷新工具
3. **工具定义编辑器**：添加/删除工具定义（name/description/parameters JSON Schema），可应用到模拟插件

模拟插件服务暴露的端点：
- `GET /health` → 插件存活检查
- `GET /tools` → 返回工具列表
- `GET /skills` → 返回技能列表
- `POST /event` → 接收主系统推送的事件

## ACP 聊天客户端

四个 Tab：

1. **聊天**：选择已连接 agent 或群组作为对话方 → 发送/接收消息（轮询刷新，3秒默认间隔）→ 本地发送靠右、接收靠左
2. **发现与连接**：发现局域网 agent、建立/断开连接、查看连接列表
3. **群组**：创建群组、加入/退出、群聊
4. **统计**：展示 ACP 统计信息（消息数/连接数/群组数等）

ACP 测试工具作为独立 ACP Agent 运行，通过 UDP 发现其他 Agent，通过 HTTP 点对点通信。

## MCP 测试工具

三个 Tab：

1. **模拟 MCP 服务器**：配置端口 → 启动模拟 FastAPI 服务 → 显示运行状态与预置工具列表
2. **MCP 管理**：添加/删除/启动/停止 MCP 服务器、健康检查、查看工具、同步全部工具
3. **工具调用测试**：选择服务器与工具 → 输入参数 JSON → 调用并展示结果（含 echo/calculator/string_reverse 快捷测试）

模拟 MCP 服务器暴露的端点：
- `GET /health` → 服务器存活检查
- `GET /tools` → 返回工具列表
- `POST /call` → 执行指定工具并返回结果

## 配置

侧边栏可配置：
- 主系统地址（默认 `http://localhost:8001`）
- ACP 工具的轮询间隔（1-10秒，默认3秒）
- CXFC 工具的模拟插件端口（8000-9999，默认9000）
- CXFC 工具的心跳间隔（5-30秒，默认10秒）
- MCP 工具的模拟服务器端口（默认8600）

## 端口分配

| 工具 | Streamlit UI 端口 | 备注 |
|------|-------------------|------|
| CXFC | 8501 | 模拟插件 HTTP 服务默认 9000 |
| ACP  | 8502 | ACPNode 消息服务器默认 8505 |
| MCP  | 8504 | 模拟 MCP 服务器默认 8600 |

## 不影响现有系统

本工具集仅通过 HTTP API 调用主系统，不修改 `frontend/` 下任何现有代码。
后端 MCP 路由的方法名修正属于 bug 修复，不影响现有功能。
