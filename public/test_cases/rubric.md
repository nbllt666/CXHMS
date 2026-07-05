# 三层契约合规 Rubric

> 遵循 AC 范式 v6 rules-3 §五 契约可验证性要求。本 rubric 为通过/失败判据清单，覆盖 5 份数据契约、5 份接口存根、3 份配置契约的全部关键字段。GN-004 交付前审查时逐项核对测试套件是否覆盖并通过；全部通过方视为契约有效。

## 一、数据契约判据（public/schema/*.json）

### 1.1 memory.json（required: id, type, content, importance, created_at, workspace_id）

- [x] memory.required.id: integer, minimum 0 — 验证 test_data_schema.py::test_memory_schema_exists
- [x] memory.required.type: enum [permanent, long_term, short_term] — 验证 test_data_schema.py::test_memory_invalid_type_rejected
- [x] memory.required.content: string, minLength 1, 非空 — 验证 test_data_schema.py::test_memory_missing_content_rejected
- [x] memory.required.importance: integer, range 1-5 — 验证 test_data_schema.py::test_memory_invalid_importance_rejected
- [x] memory.required.created_at: string, format date-time — 验证 test_data_schema.py::test_memory_valid_instance
- [x] memory.required.workspace_id: string — 验证 test_data_schema.py::test_memory_valid_instance
- [x] memory.valid_instance: Mock 生成的记忆符合全部字段约束 — 验证 test_data_schema.py::test_memory_valid_instance

### 1.2 agent.json（required: id, name, model, system_prompt）

- [x] agent.required.id: string, minLength 1 — 验证 test_data_schema.py::test_agent_schema_exists
- [x] agent.required.name: string, minLength 1 — 验证 test_data_schema.py::test_agent_schema_exists
- [x] agent.required.model: enum [main, summary, memory] — 验证 test_data_schema.py::test_agent_schema_exists
- [x] agent.required.system_prompt: string, minLength 1 — 验证 test_data_schema.py::test_agent_schema_exists
- [x] agent.valid_instance: Mock 生成的 Agent 符合全部字段约束 — 验证 test_data_schema.py::test_agent_valid_instance

### 1.3 message.json（required: id, session_id, role, content）

- [x] message.required.id: string, minLength 1 — 验证 test_data_schema.py::test_message_schema_exists
- [x] message.required.session_id: string, minLength 1 — 验证 test_data_schema.py::test_message_schema_exists
- [x] message.required.role: enum [user, assistant, system, tool] — 验证 test_data_schema.py::test_message_schema_exists
- [x] message.required.content: string — 验证 test_data_schema.py::test_message_schema_exists
- [x] message.valid_instance: 符合 message.json 全部字段约束 — 验证 test_data_schema.py::test_message_valid_instance

### 1.4 tool.json（required: name, description, parameters）

- [x] tool.required.name: string, 合法 Python 标识符 pattern — 验证 test_data_schema.py::test_tool_schema_exists
- [x] tool.required.description: string, minLength 1 — 验证 test_data_schema.py::test_tool_schema_exists
- [x] tool.required.parameters: object (JSON Schema) — 验证 test_data_schema.py::test_tool_schema_exists
- [x] tool.required.category: enum [builtin, custom, mcp, native, general] — 验证 test_data_schema.py::test_tool_schema_exists
- [x] tool.valid_instance: Mock 生成的工具符合全部字段约束 — 验证 test_data_schema.py::test_tool_valid_instance

### 1.5 error.json（required: error, error_code）

- [x] error.required.error: string, minLength 1 — 验证 test_data_schema.py::test_error_schema_exists
- [x] error.required.error_code: enum 含 MEMORY_NOT_FOUND/VALIDATION_ERROR/LLM_ERROR 等 15 项 — 验证 test_data_schema.py::test_error_schema_exists
- [x] error.valid_instance: 合法 ErrorResponse 通过校验 — 验证 test_data_schema.py::test_error_response_structure
- [x] error.invalid_missing_error_code: 缺 error_code 被拒绝 — 验证 test_data_schema.py::test_error_response_structure

## 二、接口契约判据（public/interface_stub/*.pyi）

### 2.1 memory_service.pyi（14 方法）

- [x] memory.write_memory(content, memory_type, importance, tags, metadata, permanent, emotion_score, workspace_id, agent_id) -> int — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.get_memory(memory_id, include_deleted, agent_id) -> Optional[Dict] — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.update_memory(memory_id, new_content, new_importance, new_tags, new_metadata, agent_id) -> bool — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.delete_memory(memory_id, soft_delete, agent_id) -> bool — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.search_memories(query, memory_type, tags, time_range, limit, offset, include_deleted, workspace_id, agent_id) -> List[Dict] — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.recall_memory(memory_id, emotion_intensity, agent_id) -> Optional[Dict] — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.get_statistics(workspace_id) -> Dict — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.is_vector_search_enabled() -> bool — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.hybrid_search(query, memory_type, tags, limit, workspace_id, agent_id) async -> List[Dict] — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.semantic_search(query, memory_type, limit, agent_id) async -> List[Dict] — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.batch_write_memories(memories, raise_on_error) -> Dict — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.batch_update_memories(updates, raise_on_error, agent_id) -> Dict — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.batch_delete_memories(memory_ids, soft_delete, raise_on_error, agent_id) -> Dict — 验证 test_interface_stub.py::test_memory_service_signature
- [x] memory.sync_decay_values(workspace_id) -> Dict — 验证 test_interface_stub.py::test_memory_service_signature

### 2.2 chat_service.pyi（5 方法）

- [x] chat.chat(message, agent_id, stream, images) async -> Dict — 验证 test_interface_stub.py::test_chat_service_signature
- [x] chat.stream_chat(message, agent_id, images) async -> AsyncIterator[str] — 验证 test_interface_stub.py::test_chat_service_signature
- [x] chat.get_chat_history(session_id, limit) async -> List[Dict] — 验证 test_interface_stub.py::test_chat_service_signature
- [x] chat.memory_agent_stream_chat(message, agent_id, images) async -> AsyncIterator[str] — 验证 test_interface_stub.py::test_chat_service_signature
- [x] chat.summary_agent_stream_chat(message, agent_id, images) async -> AsyncIterator[str] — 验证 test_interface_stub.py::test_chat_service_signature

### 2.3 agent_service.pyi（6 方法）

- [x] agent.list_agents() async -> List[Dict] — 验证 test_interface_stub.py::test_agent_service_signature
- [x] agent.get_agent(agent_id) async -> Dict — 验证 test_interface_stub.py::test_agent_service_signature
- [x] agent.create_agent(request) async -> Dict — 验证 test_interface_stub.py::test_agent_service_signature
- [x] agent.update_agent(agent_id, request) async -> Dict — 验证 test_interface_stub.py::test_agent_service_signature
- [x] agent.delete_agent(agent_id) async -> Dict — 验证 test_interface_stub.py::test_agent_service_signature
- [x] agent.get_default_agent() async -> Dict — 验证 test_interface_stub.py::test_agent_service_signature

### 2.4 tool_service.pyi（6 方法）

- [x] tool.list_tools(enabled_only, include_builtin, category) async -> Dict — 验证 test_interface_stub.py::test_tool_service_signature
- [x] tool.register_tool(request) async -> Dict — 验证 test_interface_stub.py::test_tool_service_signature
- [x] tool.execute_tool(name, arguments) async -> Dict — 验证 test_interface_stub.py::test_tool_service_signature
- [x] tool.update_tool(name, request) async -> Dict — 验证 test_interface_stub.py::test_tool_service_signature
- [x] tool.delete_tool(name) async -> Dict — 验证 test_interface_stub.py::test_tool_service_signature
- [x] tool.get_tool_stats() async -> Dict — 验证 test_interface_stub.py::test_tool_service_signature

### 2.5 graph_service.pyi（12 方法）

- [x] graph.create_node(request, agent_id) async -> Dict — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.get_node(node_id, agent_id) async -> Optional[Dict] — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.update_node(node_id, request, agent_id) async -> Optional[Dict] — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.delete_node(node_id, agent_id) async -> bool — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.create_edge(request, agent_id) async -> Dict — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.get_edge(edge_id, agent_id) async -> Optional[Dict] — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.update_edge(edge_id, request, agent_id) async -> Optional[Dict] — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.delete_edge(edge_id, agent_id) async -> bool — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.traverse_bfs(start_id, max_depth, node_type_filter, agent_id) async -> Dict — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.traverse_dfs(start_id, max_depth, node_type_filter, agent_id) async -> Dict — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.shortest_path(start_id, end_id, max_length) async -> Optional[Dict] — 验证 test_interface_stub.py::test_graph_service_signature
- [x] graph.semantic_search(query, node_type, limit, agent_id) async -> List[Dict] — 验证 test_interface_stub.py::test_graph_service_signature

### 2.6 存根纯签名约束

- [x] 所有 .pyi 存根仅含签名（无实现逻辑，仅 .../pass/docstring） — 验证 test_interface_stub.py::test_all_stubs_are_signature_only

## 三、配置契约判据（public/config_template/*.json）

### 3.1 system_config.json（required: server, logging, database）

- [x] system.required.server: object — 验证 test_config_template.py::test_system_config_exists
- [x] system.required.logging: object — 验证 test_config_template.py::test_system_config_exists
- [x] system.required.database: object — 验证 test_config_template.py::test_system_config_exists
- [x] system.default.server.port: 8001 — 验证 test_config_template.py::test_system_config_has_defaults
- [x] system.default.logging.level: INFO — 验证 test_config_template.py::test_system_config_has_defaults
- [x] system.default.database.type: sqlite — 验证 test_config_template.py::test_system_config_has_defaults
- [x] system.auto_fill: 空实例经 auto_fill 后 server.port=8001, logging.level=INFO, database.type=sqlite — 验证 test_config_template.py::test_system_config_auto_fill

### 3.2 llm_config.json（required: models）

- [x] llm.required.models: object, required main — 验证 test_config_template.py::test_llm_config_exists
- [x] llm.default.max_tool_rounds: 10 — 验证 test_config_template.py::test_llm_config_has_defaults
- [x] llm.default.max_concurrent: 4 — 验证 test_config_template.py::test_llm_config_has_defaults
- [x] llm.auto_fill_top_level: 缺 max_tool_rounds 时补充为 10, max_concurrent 为 4 — 验证 test_config_template.py::test_llm_config_auto_fill_top_level
- [x] llm.$defs.modelSlot: 模型槽位统一引用，无内联冗余定义 — 验证 test_config_template.py::test_config_validates_against_schema

### 3.3 vector_config.json（required: memory）

- [x] vector.required.memory: object, required vector_enabled/vector_backend — 验证 test_config_template.py::test_vector_config_exists
- [x] vector.default.memory.vector_backend: weaviate — 验证 test_config_template.py::test_vector_config_has_defaults
- [x] vector.default.memory.weaviate.port: 8090 — 验证 test_config_template.py::test_vector_config_has_defaults
- [x] vector.auto_fill: auto_fill 后实例通过 schema 校验 — 验证 test_config_template.py::test_config_validates_against_schema

## 四、测试套件自主执行判据

- [x] 项目根调用 `python -m pytest public/test_cases/ -v` 全部通过 — 34/34（含真实实现对比、valid instance、契约约束拒绝三类测试）
- [x] 子目录调用 `cd public/test_cases && python -m pytest . -v --rootdir=.` 全部通过 — 兼容性
- [x] conftest.py 提供标准 pytest fixture（schema_dir/stub_dir/config_dir/mock_dir/backend_dir/load_json_func/jsonschema_mod） — 验证 conftest.py
- [x] test_*.py 使用标准相对 import `from .conftest import ...` — 验证 test_*.py
- [x] pytest.ini testpaths 含 `public/test_cases` — 验证 pytest.ini

## 五、闭合判据

- [x] 5 份数据契约存在且符合 draft-07+
- [x] 5 份接口存根存在且仅含签名
- [x] 3 份配置契约存在且含默认值
- [x] 测试套件可自主执行（jsonschema 校验 + 签名匹配 + 默认值填充 + 真实实现对比）
- [x] rubric 覆盖全部契约字段（本文件）

> GN-004 审查时逐项核对：判据对应的测试必须存在且通过，方视为契约有效。任一判据失败即阻断合流。
