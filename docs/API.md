# CXHMS API 文档

## 概述

CXHMS (CX-O History & Memory Service) 提供了一套完整的RESTful API，用于管理记忆、上下文、ACP互联、工具调用等功能。

**基础URL**: `http://localhost:8000`

**认证**: 当前版本暂未实现认证机制（生产环境请配置API密钥）

**响应格式**: 所有API返回JSON格式，包含`status`字段表示请求状态。

---

## 聊天 API

### 1. 同步聊天

**端点**: `POST /api/chat`

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
- `images` (array, 可选): base64编码的图片列表（多模态支持）

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

**请求体**: 同`POST /api/chat`

**响应**: Server-Sent Events (SSE) 流

**事件类型**:
- `session`: 会话信息
- `thinking`: 思考过程（如模型支持）
- `content`: 内容片段
- `tool_call`: 工具调用
- `tool_start`: 工具开始执行
- `tool_result`: 工具执行结果
- `done`: 完成
- `error`: 错误

### 3. 获取聊天历史

**端点**: `GET /api/chat/history/{session_id}`

**参数**:
- `limit` (integer, 可选): 返回消息数量限制，默认50

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

### 4. 记忆管理Agent流式对话

**端点**: `POST /api/memory-agent/chat/stream`

**请求体**:
```json
{
  "message": "帮我搜索关于编程的记忆"
}
```

**说明**: 专门用于记忆管理的流式聊天接口，使用 memory-agent 配置，支持16个记忆管理工具。

---

## 记忆管理 API

### 1. 获取Agent记忆表列表

**端点**: `GET /api/memories/agents`

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

**参数**:
- `workspace_id` (string, 可选): 工作区ID，默认为"default"
- `memory_type` (string, 可选): 记忆类型（long_term, short_term, permanent）
- `limit` (integer, 可选): 返回数量限制，默认为20
- `offset` (integer, 可选): 偏移量，默认为0

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

### 4. 记忆统计

**端点**: `GET /api/memories/stats`

### 5. 获取单条记忆

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

### 6. 更新记忆

**端点**: `PUT /api/memories/{memory_id}`

**请求体**:
```json
{
  "content": "用户喜欢Python编程",
  "importance": 4,
  "tags": ["Python", "编程"]
}
```

### 7. 删除记忆

**端点**: `DELETE /api/memories/{memory_id}`

### 8. 搜索记忆

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

### 9. RAG检索

**端点**: `POST /api/memories/rag`

**请求体**:
```json
{
  "query": "用户的爱好是什么？",
  "workspace_id": "default",
  "limit": 5
}
```

### 10. 语义搜索

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

### 11. 3D评分搜索

**端点**: `POST /api/memories/3d`

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

### 12. 按类型查询

**端点**: `GET /api/memories/type/{memory_type}`

### 13. 按标签搜索

**端点**: `GET /api/memories/search-by-tag`

**参数**:
- `tag` (string, 必需): 标签名称

### 14. 永久记忆管理

**创建永久记忆**: `POST /api/memories/permanent`

**列出永久记忆**: `GET /api/memories/permanent`

**获取永久记忆**: `GET /api/memories/permanent/{memory_id}`

**更新永久记忆**: `PUT /api/memories/permanent/{memory_id}`

**删除永久记忆**: `DELETE /api/memories/permanent/{memory_id}`

### 15. 重新激活记忆

**端点**: `POST /api/memories/recall/{memory_id}`

**请求体**:
```json
{
  "reactivation_strength": 0.2
}
```

### 16. 同步衰减

**端点**: `POST /api/memories/sync-decay`

### 17. 衰减统计

**端点**: `GET /api/memories/decay-stats`

### 18. 向量状态

**端点**: `GET /api/memories/vectors/status`

### 19. 批量操作

**批量写入**: `POST /api/memories/batch/write`

**请求体**:
```json
{
  "memories": [
    {"content": "记忆1", "type": "long_term", "importance": 3},
    {"content": "记忆2", "type": "long_term", "importance": 4}
  ]
}
```

**批量更新**: `POST /api/memories/batch/update`

**请求体**:
```json
{
  "ids": [1, 2, 3],
  "data": {"tags": ["新标签"], "importance": 4},
  "agent_id": "default"
}
```

**批量删除**: `POST /api/memories/batch/delete`

**请求体**:
```json
{
  "ids": [1, 2, 3],
  "agent_id": "default"
}
```

**批量标签更新**: `POST /api/memories/batch/tags`

**请求体**:
```json
{
  "ids": [1, 2, 3],
  "tags": ["标签1", "标签2"],
  "operation": "add",
  "agent_id": "default"
}
```

**批量归档**: `POST /api/memories/batch/archive`

**批量恢复**: `POST /api/memories/batch/restore`

**按查询批量标签**: `POST /api/memories/batch/tag-by-query`

**按查询批量删除**: `POST /api/memories/batch/delete-by-query`

**按查询批量归档**: `POST /api/memories/batch/archive-by-query`

### 20. 副模型路由

**执行副模型指令**: `POST /api/memories/secondary/execute`

**请求体**:
```json
{
  "command": "SUMMARIZE_MEMORY",
  "params": {}
}
```

**获取可用副模型指令**: `GET /api/memories/secondary/commands`

**副模型执行历史**: `GET /api/memories/secondary/history`

**支持的10种指令**: SUMMARIZE_MEMORY, ARCHIVE_MEMORY, EXTRACT_KEYWORDS, GENERATE_TAGS, MERGE_MEMORIES, FIND_DUPLICATES, ENRICH_MEMORY, SCORE_MEMORY, CATEGORIZE_MEMORY, CLEANUP_MEMORY

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

## ACP互联 API

### 1. 发现Agent

**端点**: `POST /api/acp/discover`

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
  "message": "发现 1 个Agents"
}
```

### 2. Agent列表

**端点**: `GET /api/acp/agents`

### 3. 连接Agent

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

### 13. ACP统计

**端点**: `GET /api/acp/stats`

---

## 工具管理 API

### 1. 列出工具

**端点**: `GET /api/tools`

**参数**:
- `enabled_only` (boolean, 可选): 是否只返回启用的工具，默认为true

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

### 6. OpenAI格式工具列表

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

## MCP工具管理 API

### 1. MCP服务器列表

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

### 2. 添加MCP服务器

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

### 3. 删除MCP服务器

**端点**: `DELETE /api/tools/mcp/servers/{name}`

### 4. 启动MCP服务器

**端点**: `POST /api/tools/mcp/servers/start`

**请求体**:
```json
{
  "name": "filesystem"
}
```

### 5. 停止MCP服务器

**端点**: `POST /api/tools/mcp/servers/stop`

**请求体**:
```json
{
  "name": "filesystem"
}
```

### 6. MCP健康检查

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

### 7. MCP工具列表

**端点**: `GET /api/tools/mcp/servers/{name}/tools`

### 8. 调用MCP工具

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

### 9. 同步MCP工具

**端点**: `POST /api/tools/mcp/sync`

**参数**:
- `name` (string): 服务器名称

---

## Agent管理 API

### 1. Agent列表

**端点**: `GET /api/agents`

**响应示例**:
```json
[
  {
    "id": "default",
    "name": "默认助手",
    "description": "通用AI助手",
    "system_prompt": "你是一个有帮助的AI助手...",
    "model": "main",
    "temperature": 0.7,
    "max_tokens": 131072,
    "use_memory": true,
    "use_tools": true,
    "memory_scene": "chat",
    "is_default": true
  },
  {
    "id": "memory-agent",
    "name": "记忆管理助手",
    "description": "专业的记忆管理助手",
    "model": "memory",
    "temperature": 0.3,
    "max_tokens": 131072,
    "use_memory": false,
    "use_tools": true
  }
]
```

### 2. 创建Agent

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
  "vision_enabled": false
}
```

### 3. 获取Agent

**端点**: `GET /api/agents/{agent_id}`

### 4. 更新Agent

**端点**: `PUT /api/agents/{agent_id}`

### 5. 删除Agent

**端点**: `DELETE /api/agents/{agent_id}`

### 6. 克隆Agent

**端点**: `POST /api/agents/{agent_id}/clone`

### 7. Agent统计

**端点**: `GET /api/agents/{agent_id}/stats`

**响应示例**:
```json
{
  "agent_id": "default",
  "session_count": 5,
  "total_messages": 120
}
```

### 8. Agent上下文

**端点**: `GET /api/agents/{agent_id}/context`

**参数**:
- `limit` (integer, 可选): 返回消息数量限制，默认20

### 9. 清除Agent上下文

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

### 5. LLM配置

**端点**: `POST /api/config/llm`

### 6. 图数据库配置

**端点**: `GET /api/config/graph`

### 7. CXFC配置

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
- `source_id` (string, 可选): 源节点ID
- `target_id` (string, 可选): 目标节点ID
- `type` (string, 可选): 边类型

### 13. BFS遍历

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

### 14. DFS遍历

**端点**: `POST /api/traverse/dfs`

**请求体**: 同 BFS

### 15. 最短路径

**端点**: `GET /api/paths/shortest`

**参数**:
- `source_id` (string, 必需): 源节点ID
- `target_id` (string, 必需): 目标节点ID
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
- `top_k` (integer, 可选): 返回前K个重要节点

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

### 28. JSON导出

**端点**: `GET /api/export/json`

### 29. GraphML导出

**端点**: `GET /api/export/graphml`

### 30. DOT导出

**端点**: `GET /api/export/dot`

### 31. 图配置

**端点**: `GET /api/config`

---

## CXFC插件协议 API

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
- `plugin_id` (string, 可选): 插件ID

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

### 1. Agent专用WebSocket

**端点**: `WS /ws/{agent_id}`

**说明**: 为指定Agent建立的专用WebSocket连接，支持实时消息推送和状态更新。

### 2. 通用WebSocket

**端点**: `WS /ws`

**消息格式**:
```json
{
  "type": "chat|alarm|system",
  "data": {}
}
```

### 3. 聊天WebSocket

**端点**: `WS /ws/chat`

**说明**: 专门用于聊天场景的WebSocket连接，支持流式消息传输。

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

1. **认证**: 当前版本未实现认证，生产环境请配置API密钥
2. **CORS**: 默认允许所有来源，生产环境请限制CORS来源
3. **速率限制**: 当前未实现速率限制，建议生产环境配置
4. **数据持久化**: 使用SQLite数据库
5. **向量搜索**: 支持Chroma/Milvus Lite/Qdrant/Weaviate/Weaviate Embedded
6. **图数据库**: 基于SQLite + NetworkX，支持Neo4j迁移
7. **CXFC插件协议**: 心跳机制维持在线状态，技能声明与路由
8. **控制服务**: 独立端口8765，管理后端启停
9. **副模型路由**: 支持10种指令（SUMMARIZE_MEMORY, ARCHIVE_MEMORY, EXTRACT_KEYWORDS, GENERATE_TAGS, MERGE_MEMORIES, FIND_DUPLICATES, ENRICH_MEMORY, SCORE_MEMORY, CATEGORIZE_MEMORY, CLEANUP_MEMORY）

---

## 示例代码

### Python示例

```python
import httpx

async def create_memory():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/memories",
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

### JavaScript示例

```javascript
async function createMemory() {
  const response = await fetch('http://localhost:8000/api/memories', {
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
