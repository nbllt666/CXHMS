# CXHMS API 文档

> **文档版本**: v3.0.0 | **最后更新**: 2026-07-17

## 概述

CXHMS (CX-O History & Memory Service) 晨曦人格化记忆系统提供了一套完整的 RESTful API，覆盖记忆管理、上下文管理、ACP 协议通信、工具调用、图数据库、CXFC 插件协议、向量数据库、备份恢复，以及 RADIX-Lite 管理 Agent 扩展（模板引擎 / 多模态管线 / 蒸馏服务 / 决策核心）等功能。

**基础 URL**: `http://localhost:8001`

**认证**: 当前版本暂未实现认证机制（生产环境请配置 API 密钥）

**响应格式**: 所有 API 返回 JSON 格式，包含 `status` 字段表示请求状态

**契约版本**: v1.2.0（13 schema + 13 .pyi + 5 config + 12 mock，详见 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md)）

---

## 服务端口说明

CXHMS 采用多服务架构，各服务独立端口运行：

| 服务 | 地址 | 说明 |
|------|------|------|
| 主 API 服务 | http://localhost:8001 | FastAPI 主后端，承载全部 REST API |
| RADIX-Lite 蒸馏服务 | http://localhost:8011 | RADIX-Lite 蒸馏会话独立服务（v1.2.0 新增） |
| API 文档 (Swagger) | http://localhost:8001/docs | OpenAPI 交互式文档 |
| API 文档 (ReDoc) | http://localhost:8001/redoc | ReDoc 文档 |
| 前端界面 | http://localhost:3000 | React 前端开发服务器 |
| 控制服务 | http://localhost:8765 | 后端启停管理 |
| vLLM 主模型 | http://localhost:8002 | 主模型 gemma4-e4b |
| vLLM Embedding | http://localhost:8101 | Embedding 模型 Qwen3-Embedding-0.6B |
| Weaviate 向量库 | http://localhost:8090 | 向量存储后端 |

> 端口配置以 `config/default.yaml` 与 `public/config_template/radix_config.json` 为真相源。前端开发服务器通过代理转发请求至 8001 端口，Swagger/ReDoc 文档可通过前端代理访问。

---

## 聊天 API

### 1. 同步聊天

**端点**: `POST /api/chat`

**描述**: 同步方式发送消息并获取完整响应

**请求体**:
```json
{
  "message": "你好",
  "agent_id": "default",
  "stream": false,
  "images": null
}
```

**参数说明**:
- `message` (string, 必需): 用户消息
- `agent_id` (string, 可选): Agent ID，默认为 "default"
- `stream` (boolean, 可选): 是否流式响应，默认为 true
- `images` (array, 可选): base64 编码的图片列表（多模态支持）

**响应示例**:
```json
{
  "status": "success",
  "response": "你好！有什么我可以帮助你的吗？",
  "session_id": "agent-default",
  "tokens_used": 150
}
```

### 2. 流式聊天

**端点**: `POST /api/chat/stream`

**描述**: 以 SSE (Server-Sent Events) 流式方式返回响应

**请求体**: 同 `POST /api/chat`

**响应**: Server-Sent Events (SSE) 流

**事件类型**:
- `session`: 会话信息
- `thinking`: 思考过程（如模型支持）
- `content`: 内容片段
- `tool_call`: 工具调用
- `tool_start`: 工具开始执行
- `tool_result`: 工具执行结果
- `done`: 完成
- `cancelled`: 取消
- `error`: 错误

### 3. 获取聊天历史

**端点**: `GET /api/chat/history/{session_id}`

**描述**: 获取指定会话的聊天历史

**参数**:
- `limit` (integer, 可选): 返回消息数量限制，默认 50

**响应示例**:
```json
{
  "status": "success",
  "session_id": "agent-default",
  "session": {
    "id": "agent-default",
    "title": "默认助手的对话",
    "message_count": 10
  },
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么我可以帮助你的吗？"}
  ]
}
```

### 4. 记忆管理 Agent 流式对话

**端点**: `POST /api/memory-agent/chat/stream`

**描述**: 专门用于记忆管理的流式聊天接口，使用 memory-agent 配置，支持 16 个记忆管理工具。该端点定义在 chat.py 中（非 memory_chat.py）

**请求体**:
```json
{
  "message": "帮我搜索关于编程的记忆"
}
```

---

## 记忆管理 API

### 1. 获取 Agent 记忆表列表

**端点**: `GET /api/memories/agents`

**描述**: 列出所有 Agent 对应的记忆表

**响应示例**:
```json
{
  "status": "success",
  "agents": [
    {"agent_id": "default", "table_name": "memories", "created_at": null},
    {"agent_id": "agent-001", "table_name": "memories_agent_001", "created_at": "2026-02-16T10:00:00"}
  ],
  "total": 2
}
```

### 2. 查询记忆列表

**端点**: `GET /api/memories`

**描述**: 查询记忆列表，支持多维度过滤

**参数**:
- `workspace_id` (string, 可选): 工作区 ID，默认为 "default"
- `memory_type` (string, 可选): 记忆类型（long_term, short_term, permanent）
- `limit` (integer, 可选): 返回数量限制，默认为 20
- `offset` (integer, 可选): 偏移量，默认为 0

**响应示例**:
```json
{
  "status": "success",
  "memories": [
    {
      "id": 1,
      "type": "long_term",
      "content": "用户喜欢编程",
      "importance": 3,
      "importance_score": 0.6,
      "time_score": 0.8,
      "relevance_score": 0.7,
      "final_score": 0.7,
      "tags": ["编程", "爱好"],
      "created_at": "2026-02-06T10:00:00"
    }
  ],
  "total": 1
}
```

### 3. 创建记忆

**端点**: `POST /api/memories`

**描述**: 创建单条记忆

**请求体**:
```json
{
  "content": "用户喜欢编程",
  "type": "long_term",
  "importance": 3,
  "tags": ["编程", "爱好"],
  "metadata": {},
  "permanent": false,
  "workspace_id": "default"
}
```

**响应示例**:
```json
{
  "status": "success",
  "memory_id": 1,
  "message": "记忆已创建"
}
```

### 4. 决策化写入（v1.2.0 新增）

**端点**: `POST /api/memories/write-with-decision`

**描述**: 决策化写入接口，由 RADIX-Lite 决策核心驱动。当决策结果为拒绝写入时，原始内容会保留到 `rejected_content` 表（30 天保留期），便于后续审计与回溯

**请求体**:
```json
{
  "content": "待写入的记忆内容",
  "type": "long_term",
  "importance": 3,
  "tags": ["标签"],
  "metadata": {},
  "workspace_id": "default",
  "agent_id": "default",
  "rubric_snapshot": {
    "quality_threshold": 0.6,
    "dedup_threshold": 0.85
  }
}
```

**响应示例（接受写入）**:
```json
{
  "status": "success",
  "decision": "accept",
  "memory_id": 42,
  "quality_score": 0.78,
  "rubric_snapshot": {...},
  "message": "决策接受，记忆已写入"
}
```

**响应示例（拒绝写入，内容保留 30 天）**:
```json
{
  "status": "success",
  "decision": "reject",
  "memory_id": null,
  "quality_score": 0.32,
  "rejected_content_id": "rj-20260717-001",
  "retention_days": 30,
  "rubric_snapshot": {...},
  "message": "决策拒绝，内容已保留至 rejected_content 表"
}
```

### 5. 获取拒绝写入内容（v1.2.0 新增）

**端点**: `GET /api/memories/rejected-content`

**描述**: 获取被决策拒绝写入的内容列表（30 天保留期）

**参数**:
- `agent_id` (string, 可选): Agent ID 过滤
- `limit` (integer, 可选): 返回数量限制，默认 50
- `offset` (integer, 可选): 偏移量，默认 0

**响应示例**:
```json
{
  "status": "success",
  "rejected_contents": [
    {
      "id": "rj-20260717-001",
      "content": "被拒绝的内容",
      "quality_score": 0.32,
      "decision_reason": "质量分低于阈值",
      "rubric_snapshot": {...},
      "created_at": "2026-07-17T10:00:00",
      "expires_at": "2026-08-16T10:00:00"
    }
  ],
  "total": 1
}
```

### 6. 清理过期拒绝内容（v1.2.0 新增）

**端点**: `DELETE /api/memories/rejected-content/cleanup-expired`

**描述**: 清理超过 30 天保留期的拒绝写入内容

**响应示例**:
```json
{
  "status": "success",
  "cleaned_count": 12,
  "message": "已清理 12 条过期拒绝内容"
}
```

### 7. 记忆统计

**端点**: `GET /api/memories/stats`

### 8. 获取单条记忆

**端点**: `GET /api/memories/{memory_id}`

**响应示例**:
```json
{
  "status": "success",
  "memory": {
    "id": 1,
    "type": "long_term",
    "content": "用户喜欢编程",
    "importance": 3,
    "importance_score": 0.6,
    "tags": ["编程", "爱好"],
    "created_at": "2026-02-06T10:00:00"
  }
}
```

### 9. 更新记忆

**端点**: `PUT /api/memories/{memory_id}`

**请求体**:
```json
{
  "content": "用户喜欢Python编程",
  "importance": 4,
  "tags": ["Python", "编程"]
}
```

### 10. 删除记忆

**端点**: `DELETE /api/memories/{memory_id}`

### 11. 搜索记忆

**端点**: `POST /api/memories/search`

**请求体**:
```json
{
  "query": "编程",
  "memory_type": "long_term",
  "tags": ["Python"],
  "time_range": "last_week",
  "limit": 10,
  "include_deleted": false
}
```

### 12. RAG 检索

**端点**: `POST /api/memories/rag`

**描述**: 检索增强生成 (RAG) 检索

**请求体**:
```json
{
  "query": "用户的爱好是什么？",
  "workspace_id": "default",
  "limit": 5
}
```

### 13. 语义搜索

**端点**: `POST /api/memories/semantic-search`

**请求体**:
```json
{
  "query": "用户的爱好是什么？",
  "limit": 10,
  "threshold": 0.7,
  "workspace_id": "default"
}
```

### 14. 3D 评分搜索

**端点**: `POST /api/memories/3d`

**描述**: 基于重要性、时间、相关度三维评分的混合搜索

**请求体**:
```json
{
  "query": "编程",
  "memory_type": "long_term",
  "tags": [],
  "limit": 10,
  "weights": [0.35, 0.25, 0.4],
  "workspace_id": "default"
}
```

**响应示例**:
```json
{
  "status": "success",
  "memories": [...],
  "total": 5,
  "applied_weights": {
    "importance": 0.35,
    "time": 0.25,
    "relevance": 0.4
  }
}
```

### 15. 按类型查询

**端点**: `GET /api/memories/type/{memory_type}`

### 16. 按标签搜索

**端点**: `GET /api/memories/search-by-tag`

**参数**:
- `tag` (string, 必需): 标签名称

### 17. 永久记忆管理

- **创建永久记忆**: `POST /api/memories/permanent`
- **列出永久记忆**: `GET /api/memories/permanent`
- **获取永久记忆**: `GET /api/memories/permanent/{memory_id}`
- **更新永久记忆**: `PUT /api/memories/permanent/{memory_id}`
- **删除永久记忆**: `DELETE /api/memories/permanent/{memory_id}`

### 18. 重新激活记忆

**端点**: `POST /api/memories/recall/{memory_id}`

**描述**: 重新激活衰减的记忆，提升其评分

**请求体**:
```json
{
  "reactivation_strength": 0.2
}
```

### 19. 同步衰减

**端点**: `POST /api/memories/sync-decay`

**描述**: 触发记忆衰减同步（双阶段指数衰减 + 艾宾浩斯遗忘曲线）

### 20. 衰减统计

**端点**: `GET /api/memories/decay-stats`

### 21. 向量状态

**端点**: `GET /api/memories/vectors/status`

### 22. 批量操作

- **批量写入**: `POST /api/memories/batch/write`

```json
{
  "memories": [
    {"content": "记忆1", "type": "long_term", "importance": 3},
    {"content": "记忆2", "type": "long_term", "importance": 4}
  ]
}
```

- **批量更新**: `POST /api/memories/batch/update`

```json
{
  "ids": [1, 2, 3],
  "data": {"tags": ["新标签"], "importance": 4},
  "agent_id": "default"
}
```

- **批量删除**: `POST /api/memories/batch/delete`

```json
{
  "ids": [1, 2, 3],
  "agent_id": "default"
}
```

- **批量标签更新**: `POST /api/memories/batch/tags`

```json
{
  "ids": [1, 2, 3],
  "tags": ["标签1", "标签2"],
  "operation": "add",
  "agent_id": "default"
}
```

- **批量归档**: `POST /api/memories/batch/archive`
- **批量恢复**: `POST /api/memories/batch/restore`
- **按查询批量标签**: `POST /api/memories/batch/tag-by-query`
- **按查询批量删除**: `POST /api/memories/batch/delete-by-query`
- **按查询批量归档**: `POST /api/memories/batch/archive-by-query`

### 23. 副模型路由

**描述**: 支持 10 种副模型指令

- **执行副模型指令**: `POST /api/memories/secondary/execute`

```json
{
  "command": "SUMMARIZE_MEMORY",
  "params": {}
}
```

- **获取可用副模型指令**: `GET /api/memories/secondary/commands`
- **副模型执行历史**: `GET /api/memories/secondary/history`

**支持的 10 种指令**: SUMMARIZE_MEMORY, ARCHIVE_MEMORY, EXTRACT_KEYWORDS, GENERATE_TAGS, MERGE_MEMORIES, FIND_DUPLICATES, ENRICH_MEMORY, SCORE_MEMORY, CATEGORIZE_MEMORY, CLEANUP_MEMORY

---

## 上下文管理 API

### 1. 列出会话

**端点**: `GET /api/context/sessions`

### 2. 创建会话

**端点**: `POST /api/context/sessions`

**请求体**:
```json
{
  "workspace_id": "default",
  "title": "新对话",
  "user_id": "user123",
  "metadata": {}
}
```

**响应示例**:
```json
{
  "status": "success",
  "session_id": "uuid-string",
  "message": "会话已创建"
}
```

### 3. 获取会话详情

**端点**: `GET /api/context/sessions/{session_id}`

### 4. 删除会话消息

**端点**: `DELETE /api/context/sessions/{session_id}/messages`

### 5. 删除会话

**端点**: `DELETE /api/context/sessions/{session_id}`

### 6. 删除所有会话

**端点**: `DELETE /api/context/sessions/all`

### 7. 获取消息

**端点**: `GET /api/context/messages/{session_id}`

**参数**:
- `limit` (integer, 可选): 返回数量限制
- `offset` (integer, 可选): 偏移量

### 8. 创建消息

**端点**: `POST /api/context/messages`

**请求体**:
```json
{
  "session_id": "uuid-string",
  "role": "user",
  "content": "你好",
  "metadata": {}
}
```

### 9. 生成摘要

**端点**: `POST /api/context/summary`

**请求体**:
```json
{
  "session_id": "uuid-string"
}
```

### 10. 上下文统计

**端点**: `GET /api/context/stats`

---

## 记忆对话 API

### 1. 记忆管理对话

**端点**: `POST /api/memory-chat`

**请求体**:
```json
{
  "message": "帮我搜索关于编程的记忆",
  "session_id": "optional-session-id"
}
```

### 2. 对话会话

**端点**: `GET /api/memory-chat/sessions/{session_id}`

### 3. 删除对话会话

**端点**: `DELETE /api/memory-chat/sessions/{session_id}`

### 4. 可用命令列表

**端点**: `GET /api/memory-chat/commands`

---

## ACP 互联 API

### 1. 发现 Agent

**端点**: `POST /api/acp/discover`

**描述**: 局域网自动发现其他 ACP Agent

**请求体**:
```json
{
  "timeout": 5.0
}
```

**响应示例**:
```json
{
  "status": "success",
  "agents": [
    {
      "agent_id": "agent-1",
      "name": "Agent 1",
      "host": "192.168.1.100",
      "port": 8001,
      "status": "online"
    }
  ],
  "scanned_count": 1,
  "message": "发现 1 个 Agents"
}
```

### 2. Agent 列表

**端点**: `GET /api/acp/agents`

### 3. 连接 Agent

**端点**: `POST /api/acp/connect`

**请求体**:
```json
{
  "agent_id": "agent-1",
  "host": "192.168.1.100",
  "port": 8001
}
```

### 4. 断开连接

**端点**: `DELETE /api/acp/connect/{connection_id}`

### 5. 连接列表

**端点**: `GET /api/acp/connections`

### 6. 创建群组

**端点**: `POST /api/acp/groups`

**请求体**:
```json
{
  "name": "开发组",
  "description": "开发团队群组",
  "max_members": 50
}
```

### 7. 群组列表

**端点**: `GET /api/acp/groups`

### 8. 加入群组

**端点**: `POST /api/acp/groups/{group_id}/join`

### 9. 离开群组

**端点**: `POST /api/acp/groups/{group_id}/leave`

### 10. 发送消息

**端点**: `POST /api/acp/send`

**请求体**:
```json
{
  "to_agent_id": "agent-2",
  "content": {
    "text": "你好"
  },
  "msg_type": "chat"
}
```

### 11. 群组消息

**端点**: `POST /api/acp/send/group`

**请求体**:
```json
{
  "group_id": "group-1",
  "content": {
    "text": "大家好"
  },
  "msg_type": "chat"
}
```

### 12. 消息列表

**端点**: `GET /api/acp/messages`

### 13. ACP 统计

**端点**: `GET /api/acp/stats`

---

## 工具管理 API

### 1. 列出工具

**端点**: `GET /api/tools`

**参数**:
- `enabled_only` (boolean, 可选): 是否只返回启用的工具，默认为 true

**响应示例**:
```json
{
  "status": "success",
  "tools": [
    {
      "name": "search_web",
      "description": "搜索网络",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "搜索关键词"
          }
        }
      },
      "enabled": true,
      "category": "web",
      "tags": ["search"]
    }
  ],
  "statistics": {
    "total_tools": 10,
    "enabled_tools": 8,
    "disabled_tools": 2
  }
}
```

### 2. 注册工具

**端点**: `POST /api/tools`

**请求体**:
```json
{
  "name": "search_web",
  "description": "搜索网络",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "搜索关键词"
      }
    }
  },
  "enabled": true,
  "version": "1.0.0",
  "category": "web",
  "tags": ["search"],
  "examples": ["搜索Python教程"]
}
```

### 3. 工具统计

**端点**: `GET /api/tools/stats`

### 4. 调用工具

**端点**: `POST /api/tools/call`

**请求体**:
```json
{
  "name": "search_web",
  "arguments": {
    "query": "Python教程"
  }
}
```

**响应示例**:
```json
{
  "success": true,
  "result": {
    "results": [...]
  },
  "call_count": 5,
  "last_called": "2026-02-06T10:00:00"
}
```

### 5. 测试工具

**端点**: `POST /api/tools/{name}/test`

### 6. OpenAI 格式工具列表

**端点**: `GET /api/tools/openai`

**响应示例**:
```json
{
  "status": "success",
  "functions": [
    {
      "name": "search_web",
      "description": "搜索网络",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "搜索关键词"
          }
        }
      }
    }
  ]
}
```

### 7. 导出工具

**端点**: `POST /api/tools/export`

### 8. 导入工具

**端点**: `POST /api/tools/import`

### 9. 获取工具详情

**端点**: `GET /api/tools/{name}`

### 10. 删除工具

**端点**: `DELETE /api/tools/{name}`

### 11. 插件工具列表

**端点**: `GET /api/tools/plugins`

---

## MCP 工具管理 API

### 1. MCP 服务器列表

**端点**: `GET /api/tools/mcp/servers`

**响应示例**:
```json
{
  "status": "success",
  "servers": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"],
      "env": {},
      "status": "connected",
      "tools": [
        {
          "name": "read_file",
          "description": "读取文件"
        }
      ],
      "last_check": "2026-02-06T10:00:00"
    }
  ],
  "statistics": {
    "total_servers": 1,
    "connected_servers": 1,
    "disconnected_servers": 0,
    "error_servers": 0
  }
}
```

### 2. 添加 MCP 服务器

**端点**: `POST /api/tools/mcp/servers`

**请求体**:
```json
{
  "name": "filesystem",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"],
  "env": {}
}
```

### 3. 删除 MCP 服务器

**端点**: `DELETE /api/tools/mcp/servers/{name}`

### 4. 启动 MCP 服务器

**端点**: `POST /api/tools/mcp/servers/start`

**请求体**:
```json
{
  "name": "filesystem"
}
```

### 5. 停止 MCP 服务器

**端点**: `POST /api/tools/mcp/servers/stop`

**请求体**:
```json
{
  "name": "filesystem"
}
```

### 6. MCP 健康检查

**端点**: `GET /api/tools/mcp/servers/{name}/health`

**响应示例**:
```json
{
  "status": "success",
  "health": {
    "name": "filesystem",
    "status": "connected",
    "last_check": "2026-02-06T10:00:00",
    "error": null
  }
}
```

### 7. MCP 工具列表

**端点**: `GET /api/tools/mcp/servers/{name}/tools`

### 8. 调用 MCP 工具

**端点**: `POST /api/tools/mcp/call`

**请求体**:
```json
{
  "server_name": "filesystem",
  "tool_name": "read_file",
  "arguments": {
    "path": "/path/to/file.txt"
  }
}
```

### 9. 同步 MCP 工具

**端点**: `POST /api/tools/mcp/sync`

**参数**:
- `name` (string): 服务器名称

---

## Agent 管理 API

### 1. Agent 列表

**端点**: `GET /api/agents`

**描述**: 获取所有 Agent 配置列表。v1.2.0 起 AgentConfig 新增 3 个 RADIX-Lite 扩展字段（见下方字段说明）

**响应示例**:
```json
[
  {
    "id": "default",
    "name": "默认助手",
    "description": "通用 AI 助手",
    "system_prompt": "你是一个有帮助的 AI 助手...",
    "model": "main",
    "temperature": 0.7,
    "max_tokens": 131072,
    "use_memory": true,
    "use_tools": true,
    "memory_scene": "chat",
    "is_default": true,
    "tools_config": null,
    "decision_rubric": null,
    "distillation_enabled": false
  },
  {
    "id": "memory-agent",
    "name": "记忆管理助手",
    "description": "专业的记忆管理助手",
    "model": "memory",
    "temperature": 0.3,
    "max_tokens": 131072,
    "use_memory": false,
    "use_tools": true,
    "tools_config": null,
    "decision_rubric": null,
    "distillation_enabled": false
  }
]
```

**v1.2.0 新增字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `tools_config` | object \| null | 工具配置，声明该 Agent 启用的 RADIX-Lite 8 个工具方法子集 |
| `decision_rubric` | object \| null | 决策 rubric，包含 4 个阈值（quality_threshold / dedup_threshold / importance_threshold / archive_threshold） |
| `distillation_enabled` | boolean | 是否启用蒸馏功能，默认 false。启用后该 Agent 可调用 RADIX-Lite 蒸馏服务 |

### 2. 创建 Agent

**端点**: `POST /api/agents`

**请求体**:
```json
{
  "name": "自定义助手",
  "description": "我的自定义助手",
  "system_prompt": "你是一个专业的编程助手...",
  "model": "main",
  "temperature": 0.7,
  "max_tokens": 4096,
  "use_memory": true,
  "use_tools": true,
  "memory_scene": "chat",
  "vision_enabled": false,
  "tools_config": {
    "enabled_tools": ["distill_start", "distill_collect", "storage_decision"]
  },
  "decision_rubric": {
    "quality_threshold": 0.6,
    "dedup_threshold": 0.85,
    "importance_threshold": 3,
    "archive_threshold": 0.3
  },
  "distillation_enabled": true
}
```

### 3. 获取 Agent

**端点**: `GET /api/agents/{agent_id}`

### 4. 更新 Agent

**端点**: `PUT /api/agents/{agent_id}`

### 5. 删除 Agent

**端点**: `DELETE /api/agents/{agent_id}`

### 6. 克隆 Agent

**端点**: `POST /api/agents/{agent_id}/clone`

### 7. Agent 统计

**端点**: `GET /api/agents/{agent_id}/stats`

**响应示例**:
```json
{
  "agent_id": "default",
  "session_count": 5,
  "total_messages": 120
}
```

### 8. Agent 上下文

**端点**: `GET /api/agents/{agent_id}/context`

**参数**:
- `limit` (integer, 可选): 返回消息数量限制，默认 20

### 9. 清除 Agent 上下文

**端点**: `DELETE /api/agents/{agent_id}/context`

---

## 管理员 API

### 1. 管理面板

**端点**: `GET /api/admin/dashboard`

### 2. 管理统计

**端点**: `GET /api/admin/stats`

**响应示例**:
```json
{
  "status": "success",
  "stats": {
    "total_memories": 100,
    "total_sessions": 50,
    "total_agents": 5,
    "total_tools": 10,
    "uptime": 3600
  }
}
```

### 3. 健康检查

**端点**: `GET /api/admin/health`

**响应示例**:
```json
{
  "status": "success",
  "health": {
    "database": "ok",
    "vector_store": "ok",
    "llm": "ok",
    "acp": "ok"
  }
}
```

### 4. 获取配置

**端点**: `GET /api/admin/config`

### 5. 更新配置

**端点**: `PUT /api/admin/config`

### 6. 获取日志

**端点**: `GET /api/admin/logs`

**参数**:
- `level` (string, 可选): 日志级别（DEBUG, INFO, WARNING, ERROR）
- `limit` (integer, 可选): 返回数量限制

### 7. 创建备份

**端点**: `POST /api/admin/backup`

---

## 归档管理 API

### 1. 归档列表

**端点**: `GET /api/archive/list`

### 2. 归档记忆

**端点**: `POST /api/archive/memory`

**请求体**:
```json
{
  "memory_id": 1,
  "archive_level": 1
}
```

### 3. 合并记忆

**端点**: `POST /api/archive/merge`

**请求体**:
```json
{
  "memory_ids": [1, 2, 3],
  "merged_content": "合并后的内容"
}
```

### 4. 去重

**端点**: `POST /api/archive/deduplicate`

### 5. 重复列表

**端点**: `GET /api/archive/duplicates`

### 6. 归档的归档

**端点**: `POST /api/archive/of-archives`

### 7. 归档统计

**端点**: `GET /api/archive/stats`

### 8. 归档层级

**端点**: `GET /api/archive/levels`

### 9. 设置阈值

**端点**: `POST /api/archive/threshold`

**请求体**:
```json
{
  "level": 1,
  "threshold": 0.5
}
```

### 10. 获取阈值

**端点**: `GET /api/archive/threshold`

### 11. 自动处理

**端点**: `POST /api/archive/auto-process`

---

## 服务管理 API

### 1. 服务状态

**端点**: `GET /api/service/status`

### 2. 启动服务

**端点**: `POST /api/service/start`

### 3. 停止服务

**端点**: `POST /api/service/stop`

### 4. 重启服务

**端点**: `POST /api/service/restart`

### 5. 服务日志

**端点**: `GET /api/service/logs`

**参数**:
- `lines` (integer, 可选): 返回日志行数

### 6. 获取服务配置

**端点**: `GET /api/service/config`

### 7. 更新服务配置

**端点**: `POST /api/service/config`

### 8. 环境信息

**端点**: `GET /api/service/environment`

### 9. 启动命令

**端点**: `GET /api/service/startup-command`

### 10. 模型列表

**端点**: `GET /api/service/models`

---

## 备份恢复 API

### 1. 备份列表

**端点**: `GET /api/backups`

### 2. 创建备份

**端点**: `POST /api/backups`

**请求体**:
```json
{
  "include_memories": true,
  "include_sessions": true,
  "include_agents": true,
  "include_config": true
}
```

### 3. 备份详情

**端点**: `GET /api/backups/{backup_id}`

### 4. 恢复备份

**端点**: `POST /api/backups/{backup_id}/restore`

### 5. 删除备份

**端点**: `DELETE /api/backups/{backup_id}`

### 6. 备份统计

**端点**: `GET /api/backups/stats`

### 7. 导入备份

**端点**: `POST /api/backups/import`

### 8. 导出备份

**端点**: `GET /api/backups/{backup_id}/export`

---

## 统计 API

### 1. 系统统计

**端点**: `GET /api/stats`

**响应示例**:
```json
{
  "status": "success",
  "stats": {
    "total_memories": 100,
    "total_sessions": 50,
    "total_agents": 5,
    "total_tools": 10,
    "uptime": 3600
  }
}
```

---

## 配置管理 API

### 1. 获取配置

**端点**: `GET /api/config`

### 2. 更新配置

**端点**: `PUT /api/config`

**请求体**: 完整的 YAML 配置 JSON 表示

### 3. 重载配置

**端点**: `POST /api/config`

### 4. 向量配置

**端点**: `GET /api/config/vector`

### 5. LLM 配置

**端点**: `POST /api/config/llm`

### 6. 图数据库配置

**端点**: `GET /api/config/graph`

### 7. CXFC 配置

**端点**: `GET /api/config/cxfc`

---

## 向量数据库 API

### 1. 向量配置

**端点**: `GET /api/vector/config`

### 2. 向量状态

**端点**: `GET /api/vector/status`

### 3. 向量健康检查

**端点**: `GET /api/vector/health`

**响应示例**:
```json
{
  "status": "success",
  "health": {
    "backend": "weaviate",
    "connected": true,
    "vector_count": 1000
  }
}
```

### 4. 向量列表

**端点**: `GET /api/vector/vectors`

### 5. 获取向量

**端点**: `GET /api/vector/vectors/{memory_id}`

### 6. 删除向量

**端点**: `DELETE /api/vector/vectors/{memory_id}`

### 7. 同步向量

**端点**: `POST /api/vector/sync`

### 8. 重建向量

**端点**: `POST /api/vector/rebuild`

### 9. 向量搜索

**端点**: `POST /api/vector/search`

**请求体**:
```json
{
  "query": "搜索内容",
  "limit": 10,
  "threshold": 0.7
}
```

### 10. 向量统计

**端点**: `GET /api/vector/stats`

---

## 图数据库 API

### 1. 创建节点

**端点**: `POST /api/nodes`

**请求体**:
```json
{
  "type": "person",
  "name": "张三",
  "properties": {"age": 30, "occupation": "工程师"},
  "content": "张三是一名软件工程师"
}
```

### 2. 获取节点

**端点**: `GET /api/nodes/{node_id}`

### 3. 更新节点

**端点**: `PUT /api/nodes/{node_id}`

**请求体**:
```json
{
  "name": "张三",
  "properties": {"age": 31}
}
```

### 4. 删除节点

**端点**: `DELETE /api/nodes/{node_id}`

### 5. 批量创建节点

**端点**: `POST /api/nodes/batch`

**请求体**:
```json
{
  "nodes": [
    {"type": "person", "name": "张三", "properties": {}},
    {"type": "person", "name": "李四", "properties": {}}
  ]
}
```

### 6. 搜索节点

**端点**: `GET /api/nodes/search`

**参数**:
- `type` (string, 可选): 节点类型
- `query` (string, 可选): 搜索关键词
- `limit` (integer, 可选): 返回数量限制

### 7. 节点邻居

**端点**: `GET /api/nodes/{node_id}/neighbors`

**参数**:
- `edge_types` (string, 可选): 边类型过滤
- `limit` (integer, 可选): 返回数量限制

### 8. 创建边

**端点**: `POST /api/edges`

**请求体**:
```json
{
  "source_id": "node-1",
  "target_id": "node-2",
  "type": "knows",
  "properties": {"since": "2020"},
  "weight": 1.0
}
```

### 9. 获取边

**端点**: `GET /api/edges/{edge_id}`

### 10. 更新边

**端点**: `PUT /api/edges/{edge_id}`

### 11. 删除边

**端点**: `DELETE /api/edges/{edge_id}`

### 12. 搜索边

**端点**: `GET /api/edges/search`

**参数**:
- `source_id` (string, 可选): 源节点 ID
- `target_id` (string, 可选): 目标节点 ID
- `type` (string, 可选): 边类型

### 13. BFS 遍历

**端点**: `POST /api/traverse/bfs`

**请求体**:
```json
{
  "start_node_id": "node-1",
  "max_depth": 3,
  "edge_types": ["knows"],
  "limit": 50
}
```

### 14. DFS 遍历

**端点**: `POST /api/traverse/dfs`

**请求体**: 同 BFS

### 15. 最短路径

**端点**: `GET /api/paths/shortest`

**参数**:
- `source_id` (string, 必需): 源节点 ID
- `target_id` (string, 必需): 目标节点 ID
- `max_depth` (integer, 可选): 最大深度

### 16. 语义搜索

**端点**: `POST /api/semantic/search`

**请求体**:
```json
{
  "query": "软件工程师",
  "limit": 10,
  "min_score": 0.5
}
```

### 17. 混合查询

**端点**: `POST /api/semantic/hybrid`

**请求体**:
```json
{
  "query": "软件工程师",
  "limit": 10,
  "vector_weight": 0.7,
  "keyword_weight": 0.3
}
```

### 18. 语义邻居

**端点**: `GET /api/semantic/neighbors/{node_id}`

**参数**:
- `limit` (integer, 可选): 返回数量限制

### 19. 图健康检查

**端点**: `GET /api/health`

### 20. 图指标

**端点**: `GET /api/metrics`

### 21. 图统计

**端点**: `GET /api/stats`

### 22. PageRank

**端点**: `GET /api/algorithm/pagerank`

**参数**:
- `iterations` (integer, 可选): 迭代次数
- `damping` (float, 可选): 阻尼系数

### 23. 重要节点

**端点**: `GET /api/algorithm/important-nodes`

**参数**:
- `top_k` (integer, 可选): 返回前 K 个重要节点

### 24. 社区发现

**端点**: `GET /api/algorithm/communities`

**参数**:
- `algorithm` (string, 可选): 算法类型
- `resolution` (float, 可选): 分辨率参数

### 25. 社区统计

**端点**: `GET /api/algorithm/community-stats`

### 26. 多跳语义查询

**端点**: `POST /api/semantic/query-hops`

**请求体**:
```json
{
  "query": "软件工程师",
  "hops": 2,
  "limit": 10
}
```

### 27. 路径约束查询

**端点**: `POST /api/semantic/path-constrained`

**请求体**:
```json
{
  "query": "软件工程师",
  "edge_types": ["knows", "works_with"],
  "max_depth": 3,
  "limit": 10
}
```

### 28. JSON 导出

**端点**: `GET /api/export/json`

### 29. GraphML 导出

**端点**: `GET /api/export/graphml`

### 30. DOT 导出

**端点**: `GET /api/export/dot`

### 31. 图配置

**端点**: `GET /api/config`

---

## CXFC 插件协议 API

### 1. 注册插件

**端点**: `POST /api/cxfc/register`

**请求体**:
```json
{
  "plugin_id": "my-plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件描述",
  "skills": [
    {"name": "skill1", "description": "技能1", "parameters": {}}
  ]
}
```

### 2. 心跳

**端点**: `POST /api/cxfc/heartbeat`

**请求体**:
```json
{
  "plugin_id": "my-plugin"
}
```

### 3. 事件推送

**端点**: `POST /api/cxfc/event/push`

**请求体**:
```json
{
  "plugin_id": "my-plugin",
  "event_type": "status_change",
  "data": {}
}
```

### 4. 发现插件

**端点**: `GET /api/cxfc/discover`

**响应示例**:
```json
{
  "status": "success",
  "plugins": [
    {
      "plugin_id": "my-plugin",
      "name": "我的插件",
      "status": "online",
      "skills": [...]
    }
  ]
}
```

### 5. 技能列表

**端点**: `GET /api/cxfc/skills`

**参数**:
- `plugin_id` (string, 可选): 插件 ID

### 6. 连接插件

**端点**: `POST /api/cxfc/connect`

**请求体**:
```json
{
  "plugin_id": "my-plugin"
}
```

### 7. 删除插件

**端点**: `DELETE /api/cxfc/plugins/{plugin_id}`

### 8. 插件列表

**端点**: `GET /api/cxfc/plugins`

### 9. 刷新插件

**端点**: `POST /api/cxfc/plugins/{plugin_id}/refresh`

---

## WebSocket API

### 1. Agent 专用 WebSocket

**端点**: `WS /ws/{agent_id}`

**描述**: 为指定 Agent 建立的专用 WebSocket 连接，支持实时消息推送和状态更新

### 2. 通用 WebSocket

**端点**: `WS /ws`

**消息格式**:
```json
{
  "type": "chat|alarm|system",
  "data": {}
}
```

### 3. 聊天 WebSocket

**端点**: `WS /ws/chat`

**描述**: 专门用于聊天场景的 WebSocket 连接，支持流式消息传输

> **双通信模式**: ChatPage 同时支持 WebSocket 和 SSE 两种流式通信方式，自动降级保障连接可靠性

---

## RADIX-Lite API（v1.2.0 新增）

RADIX-Lite 是 CXHMS v1.2.0 引入的管理 Agent 扩展子系统，包含 4 个独立子系统：模板引擎、多模态管线、蒸馏服务、决策核心。蒸馏服务运行在独立端口 8011，其他 API 通过主 API 服务（8001）代理。

### 一、蒸馏服务 API（端口 8011）

**基础 URL**: `http://localhost:8011`

**描述**: 提供 7 状态机多轮蒸馏会话管理（draft → collecting → distilling → refining → reviewing → finalizing → finalized）

#### 1. 启动蒸馏会话

**端点**: `POST /api/radix/distillation/start`

**描述**: 创建新的蒸馏会话，初始状态为 `draft`

**请求体**:
```json
{
  "agent_id": "default",
  "topic": "用户偏好分析",
  "config": {
    "max_turns": 5,
    "quality_threshold": 0.6
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "session_id": "dist-20260717-001",
  "state": "draft",
  "created_at": "2026-07-17T10:00:00",
  "message": "蒸馏会话已启动"
}
```

#### 2. 推进蒸馏状态

**端点**: `POST /api/radix/distillation/advance`

**描述**: 推进蒸馏会话到下一状态，遵循 7 状态机单向流转

**请求体**:
```json
{
  "session_id": "dist-20260717-001",
  "input": {
    "collected_content": "收集到的原始内容...",
    "metadata": {}
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "session_id": "dist-20260717-001",
  "previous_state": "collecting",
  "current_state": "distilling",
  "turns_completed": 2,
  "message": "状态已推进"
}
```

#### 3. 完成蒸馏

**端点**: `POST /api/radix/distillation/finalize`

**描述**: 完成蒸馏会话，生成最终决策与蒸馏产物

**请求体**:
```json
{
  "session_id": "dist-20260717-001",
  "final_review": {
    "approved": true,
    "quality_score": 0.82
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "session_id": "dist-20260717-001",
  "state": "finalized",
  "final_decision": {
    "action": "write_long_term",
    "quality_score": 0.82,
    "rubric_snapshot": {...}
  },
  "distilled_content": "蒸馏后的精华内容...",
  "message": "蒸馏已完成"
}
```

#### 4. 获取蒸馏会话状态

**端点**: `GET /api/radix/distillation/{session_id}`

**描述**: 查询指定蒸馏会话的当前状态与历史 turns

**响应示例**:
```json
{
  "status": "success",
  "session": {
    "session_id": "dist-20260717-001",
    "state": "distilling",
    "agent_id": "default",
    "topic": "用户偏好分析",
    "turns": [
      {"turn_id": 1, "state": "draft", "timestamp": "..."},
      {"turn_id": 2, "state": "collecting", "timestamp": "..."}
    ],
    "created_at": "2026-07-17T10:00:00",
    "updated_at": "2026-07-17T10:15:00"
  }
}
```

### 二、模板引擎 API

**基础 URL**: `http://localhost:8001`

**描述**: Jinja2 DSL 模板渲染与 CRUD 管理，支持 frontmatter 解析

#### 1. 创建模板

**端点**: `POST /api/radix/templates`

**请求体**:
```json
{
  "template_id": "user-profile-summary",
  "name": "用户画像摘要模板",
  "description": "用于生成用户画像摘要",
  "frontmatter": {
    "version": "1.0.0",
    "author": "system",
    "tags": ["summary", "profile"]
  },
  "body": "用户 {{ name }} 偏好 {{ preferences | join(', ') }}，活跃度 {{ activity_score }}"
}
```

**响应示例**:
```json
{
  "status": "success",
  "template_id": "user-profile-summary",
  "message": "模板已创建"
}
```

#### 2. 获取模板

**端点**: `GET /api/radix/templates/{template_id}`

**响应示例**:
```json
{
  "status": "success",
  "template": {
    "template_id": "user-profile-summary",
    "name": "用户画像摘要模板",
    "frontmatter": {...},
    "body": "用户 {{ name }} 偏好 ...",
    "created_at": "2026-07-17T10:00:00",
    "updated_at": "2026-07-17T10:00:00"
  }
}
```

#### 3. 更新模板

**端点**: `PUT /api/radix/templates/{template_id}`

**请求体**: 同创建模板，字段可选

#### 4. 删除模板

**端点**: `DELETE /api/radix/templates/{template_id}`

#### 5. 渲染模板

**端点**: `POST /api/radix/templates/{template_id}/render`

**请求体**:
```json
{
  "variables": {
    "name": "张三",
    "preferences": ["编程", "阅读"],
    "activity_score": 0.85
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "rendered_content": "用户 张三 偏好 编程, 阅读，活跃度 0.85"
}
```

### 三、多模态管线 API

**基础 URL**: `http://localhost:8001`

**描述**: 3 worker（OCR / 视觉 / 文本）多模态预处理，支持模态融合与降级开关

#### 1. 多模态预处理

**端点**: `POST /api/radix/multimodal/preprocess`

**请求体**:
```json
{
  "inputs": [
    {"type": "image", "data": "base64-encoded-image-data"},
    {"type": "text", "data": "附带文本说明"}
  ],
  "config": {
    "ocr_worker_enabled": true,
    "vision_worker_enabled": true,
    "text_worker_enabled": true,
    "vision_degraded": false,
    "merge_strategy": "concat"
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "artifacts": [
    {
      "modality": "image",
      "type": "ocr",
      "content": "图片中识别的文本...",
      "confidence": 0.92,
      "vision_degraded": false
    },
    {
      "modality": "image",
      "type": "vision",
      "content": "视觉模型描述...",
      "confidence": 0.88,
      "vision_degraded": false
    },
    {
      "modality": "text",
      "type": "text",
      "content": "附带文本说明",
      "confidence": 1.0,
      "vision_degraded": false
    }
  ],
  "merged_content": "融合后的多模态内容..."
}
```

### 四、决策核心 API

**基础 URL**: `http://localhost:8001`

**描述**: 6 决策点自主决策，rubric 驱动，含审计日志写入

#### 1. 启动蒸馏决策

**端点**: `POST /api/radix/decision/distill-start`

**描述**: 决策是否启动一次新的蒸馏会话

**请求体**:
```json
{
  "agent_id": "default",
  "topic": "用户偏好分析",
  "trigger_reason": "scheduled",
  "context": {
    "recent_memories_count": 50
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "decision": "proceed",
  "llm_reasoning": "近期记忆数量充足，适合启动蒸馏",
  "session_id": "dist-20260717-001",
  "rubric_snapshot": {...}
}
```

#### 2. 收集蒸馏内容

**端点**: `POST /api/radix/decision/distill-collect`

**描述**: 决策收集哪些内容进入蒸馏流程

**请求体**:
```json
{
  "session_id": "dist-20260717-001",
  "candidate_memories": [1, 2, 3, 4, 5],
  "collection_strategy": "recent_and_important"
}
```

**响应示例**:
```json
{
  "status": "success",
  "decision": "accept",
  "selected_memories": [1, 2, 4],
  "llm_reasoning": "选择相关性最高的 3 条记忆",
  "rubric_snapshot": {...}
}
```

#### 3. 推进蒸馏

**端点**: `POST /api/radix/decision/distill-advance`

**描述**: 决策蒸馏状态是否可以推进到下一阶段

**请求体**:
```json
{
  "session_id": "dist-20260717-001",
  "current_state": "distilling",
  "intermediate_result": {
    "quality_score": 0.75
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "decision": "advance",
  "next_state": "refining",
  "llm_reasoning": "质量分达标，可推进至精炼阶段",
  "rubric_snapshot": {...}
}
```

#### 4. 完成蒸馏

**端点**: `POST /api/radix/decision/distill-finalize`

**描述**: 决策蒸馏会话是否可以最终完成

**请求体**:
```json
{
  "session_id": "dist-20260717-001",
  "final_quality_score": 0.82
}
```

**响应示例**:
```json
{
  "status": "success",
  "decision": "finalize",
  "llm_reasoning": "最终质量分超过阈值，可完成蒸馏",
  "rubric_snapshot": {...}
}
```

#### 5. 存储决策

**端点**: `POST /api/radix/decision/storage-decision`

**描述**: 决策蒸馏产物的存储位置（long_term / short_term / archive 三选一）

**请求体**:
```json
{
  "session_id": "dist-20260717-001",
  "distilled_content": "蒸馏后的精华内容...",
  "quality_score": 0.82,
  "agent_id": "default"
}
```

**响应示例**:
```json
{
  "status": "success",
  "decision": "write_long_term",
  "storage_location": "long_term",
  "memory_id": 42,
  "llm_reasoning": "质量分高，写入长期记忆",
  "rubric_snapshot": {
    "quality_threshold": 0.6,
    "dedup_threshold": 0.85
  }
}
```

#### 6. 内容合并

**端点**: `POST /api/radix/decision/content-merge`

**描述**: 决策是否将新蒸馏内容与已有记忆合并

**请求体**:
```json
{
  "new_content": "新蒸馏内容...",
  "existing_memory_ids": [10, 15],
  "merge_strategy": "semantic"
}
```

**响应示例**:
```json
{
  "status": "success",
  "decision": "merge",
  "target_memory_id": 10,
  "merged_content": "合并后的内容...",
  "llm_reasoning": "与记忆 10 语义高度重合，执行合并",
  "rubric_snapshot": {...}
}
```

---

## 根路由

### 1. 健康检查

**端点**: `GET /health`

**响应示例**:
```json
{
  "status": "ok",
  "service": "CXHMS"
}
```

### 2. 服务信息

**端点**: `GET /`

**响应示例**:
```json
{
  "service": "CXHMS",
  "version": "1.0.0",
  "description": "CX-O History & Memory Service"
}
```

---

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## 注意事项

1. **认证**: 当前版本未实现认证，生产环境请配置 API 密钥
2. **CORS**: 默认允许所有来源，生产环境请限制 CORS 来源
3. **速率限制**: 当前未实现速率限制，建议生产环境配置
4. **数据持久化**: 使用 SQLite 数据库
5. **向量搜索**: 支持 Milvus Lite / Chroma / Qdrant / Weaviate / Weaviate Embedded
6. **图数据库**: 基于SQLite + NetworkX，支持 Neo4j 迁移
7. **CXFC 插件协议**: 心跳机制维持在线状态，技能声明与路由
8. **控制服务**: 独立端口 8765，管理后端启停
9. **副模型路由**: 支持 10 种指令（SUMMARIZE_MEMORY, ARCHIVE_MEMORY, EXTRACT_KEYWORDS, GENERATE_TAGS, MERGE_MEMORIES, FIND_DUPLICATES, ENRICH_MEMORY, SCORE_MEMORY, CATEGORIZE_MEMORY, CLEANUP_MEMORY）
10. **默认端口**: API 默认端口为 8001（依据 `config/default.yaml` 配置）
11. **双通信模式**: ChatPage 同时支持 WebSocket 和 SSE 两种流式通信方式
12. **RADIX-Lite 蒸馏服务**: 独立端口 8011，7 状态机多轮蒸馏
13. **决策化写入**: v1.2.0 新增，rejected_content 保留 30 天
14. **Agent 扩展字段**: v1.2.0 新增 tools_config / decision_rubric / distillation_enabled

---

## 示例代码

### Python 示例

```python
import httpx

async def create_memory():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/api/memories",
            json={
                "content": "用户喜欢编程",
                "type": "long_term",
                "importance": 3,
                "tags": ["编程", "爱好"]
            }
        )
        return response.json()

result = await create_memory()
print(result)
```

### 决策化写入示例（v1.2.0）

```python
import httpx

async def write_with_decision():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/api/memories/write-with-decision",
            json={
                "content": "待决策的记忆内容",
                "type": "long_term",
                "importance": 3,
                "agent_id": "default",
                "rubric_snapshot": {
                    "quality_threshold": 0.6,
                    "dedup_threshold": 0.85
                }
            }
        )
        return response.json()

result = await write_with_decision()
print(result["decision"])  # "accept" 或 "reject"
```

### RADIX-Lite 蒸馏启动示例（v1.2.0）

```python
import httpx

async def start_distillation():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8011/api/radix/distillation/start",
            json={
                "agent_id": "default",
                "topic": "用户偏好分析",
                "config": {
                    "max_turns": 5,
                    "quality_threshold": 0.6
                }
            }
        )
        return response.json()

result = await start_distillation()
print(result["session_id"])  # "dist-20260717-001"
```

### JavaScript 示例

```javascript
async function createMemory() {
  const response = await fetch('http://localhost:8001/api/memories', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      content: '用户喜欢编程',
      type: 'long_term',
      importance: 3,
      tags: ['编程', '爱好']
    })
  });
  return await response.json();
}

createMemory().then(result => console.log(result));
```

---

## Control Service API

控制服务运行在独立端口 **8765**，用于管理主后端服务的启停和状态监控。

**基础 URL**: `http://localhost:8765`

### 1. 健康检查

**端点**: `GET /health`

**响应示例**:
```json
{
  "status": "ok"
}
```

### 2. 主后端状态

**端点**: `GET /control/status`

**响应示例**:
```json
{
  "status": "success",
  "running": true,
  "pid": 12345,
  "uptime": 3600
}
```

### 3. 启动主后端

**端点**: `POST /control/start`

**响应示例**:
```json
{
  "status": "success",
  "message": "主后端已启动"
}
```

### 4. 停止主后端

**端点**: `POST /control/stop`

**响应示例**:
```json
{
  "status": "success",
  "message": "主后端已停止"
}
```

### 5. 重启主后端

**端点**: `POST /control/restart`

**响应示例**:
```json
{
  "status": "success",
  "message": "主后端已重启"
}
```

---

## 契约版本信息

当前三层契约版本：**v1.2.0**（2026-07-16 闭合）

| 契约类型 | 数量 | 位置 |
|----------|------|------|
| 数据契约 (JSON Schema) | 13 份 | `public/schema/` |
| 接口契约 (.pyi 存根) | 13 份 | `public/interface_stub/` |
| 配置契约 | 5 份 | `public/config_template/` |
| 预生成 Mock | 12 份 | `public/pre_generated_mock/` |

**版本演进**:
- v1.0.0（2026-07-02）：初始 5 schema + 5 .pyi + 3 config
- v1.0.1（2026-07-04）：接口契约补全 + graph schema 新增
- v1.0.2（2026-07-04）：jsonschema 严格化
- v1.1.0（2026-07-14）：AnythingLLM 兼容层
- v1.2.0（2026-07-16）：RADIX-Lite 4 新模块契约（6 schema + 6 .pyi + 1 config + 6 Mock）

详见 [public/schema/CHANGELOG.md](../public/schema/CHANGELOG.md)。

---

*文档版本: v3.0.0*

*最后更新: 2026-07-17*
