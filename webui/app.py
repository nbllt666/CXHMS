import gradio as gr
import httpx
import asyncio
import json
from datetime import datetime

API_BASE = "http://localhost:8000"


async def call_api(endpoint: str, data: dict = None, method: str = "GET"):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(f"{API_BASE}{endpoint}")
            elif method == "POST":
                response = await client.post(f"{API_BASE}{endpoint}", json=data)
            elif method == "PUT":
                response = await client.put(f"{API_BASE}{endpoint}", json=data)
            elif method == "DELETE":
                response = await client.delete(f"{API_BASE}{endpoint}")
            else:
                return {"error": f"不支持的HTTP方法: {method}"}

            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"API错误: {response.status_code}", "status_code": response.status_code}
    except Exception as e:
        return {"error": str(e)}


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)
    except RuntimeError:
        return asyncio.run(coro)


def get_memory_stats():
    result = run_async(call_api("/api/memories/stats"))
    if result.get("status") == "success":
        stats = result.get("statistics", {})
        total = stats.get("total", 0)
        permanent = stats.get("permanent", 0)
        long_term = stats.get("by_type", {}).get("long_term", 0)
        short_term = stats.get("by_type", {}).get("short_term", 0)
        return f"总记忆: {total} | 永久: {permanent} | 长期: {long_term} | 短期: {short_term}"
    return "无法获取统计信息"


def search_memories(query: str, memory_type: str = "all"):
    data = {
        "query": query if query else None,
        "memory_type": memory_type if memory_type != "all" else None,
        "limit": 20
    }
    result = run_async(call_api("/api/memories/search", data, "POST"))
    if result.get("status") == "success":
        memories = result.get("memories", [])
        if not memories:
            return "未找到相关记忆"
        return "\n\n".join([
            f"【{m.get('type', 'unknown')}】{m.get('content', '')[:300]}\n重要性: ⭐{m.get('importance', 3)} | {m.get('created_at', '')[:10]} | 标签: {', '.join(m.get('tags', [])[:3])}"
            for m in memories
        ])
    return f"搜索失败: {result.get('error', '未知错误')}"


def add_memory(content: str, memory_type: str, importance: int, tags: str):
    data = {
        "content": content,
        "type": memory_type,
        "importance": importance,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "permanent": memory_type == "permanent"
    }
    result = run_async(call_api("/api/memories", data, "POST"))
    if result.get("status") == "success":
        return f"✓ 记忆已添加 (ID: {result.get('memory_id')})"
    return f"✗ 添加失败: {result.get('error', '未知错误')}"


def search_memories_3d(query: str, memory_type: str = "all", weights: str = "default"):
    weight_map = {
        "default": [0.35, 0.25, 0.4],
        "importance": [0.5, 0.2, 0.3],
        "time": [0.2, 0.5, 0.3],
        "relevance": [0.3, 0.2, 0.5]
    }
    
    data = {
        "query": query if query else None,
        "memory_type": memory_type if memory_type != "all" else None,
        "weights": weight_map.get(weights, weight_map["default"]),
        "limit": 20
    }
    result = run_async(call_api("/api/memories/3d", data, "POST"))
    if result.get("status") == "success":
        memories = result.get("memories", [])
        if not memories:
            return "未找到相关记忆"
        
        output = []
        for m in memories:
            final_score = m.get("final_score", 0)
            component_scores = m.get("component_scores", {})
            output.append(
                f"【{m.get('type', 'unknown')}】{m.get('content', '')[:200]}\n"
                f"最终评分: {final_score:.3f}\n"
                f"  - 重要性: {component_scores.get('importance', 0):.3f}\n"
                f"  - 时间: {component_scores.get('time', 0):.3f}\n"
                f"  - 相关性: {component_scores.get('relevance', 0):.3f}\n"
                f"创建时间: {m.get('created_at', '')[:10]}"
            )
        return "\n\n".join(output)
    return f"搜索失败: {result.get('error', '未知错误')}"


def recall_memory(memory_id: str, emotion_intensity: float = 0.5):
    try:
        mid = int(memory_id)
    except (ValueError, TypeError):
        return "✗ 无效的记忆ID"
    
    data = {"emotion_intensity": emotion_intensity}
    result = run_async(call_api(f"/api/memories/recall/{mid}", data, "POST"))
    if result.get("status") == "success":
        memory = result.get("memory", {})
        reactivation_details = memory.get("reactivation_details", {})
        return (
            f"✓ 记忆已召回\n"
            f"内容: {memory.get('content', '')[:200]}\n"
            f"重激活次数: {memory.get('reactivation_count', 0)}\n"
            f"情感分数: {memory.get('emotion_score', 0):.2f}\n"
            f"时间分变化: {reactivation_details.get('old_time_score', 0):.3f} → {reactivation_details.get('new_time_score', 0):.3f}"
        )
    return f"✗ 召回失败: {result.get('error', '未知错误')}"


def get_permanent_memories():
    result = run_async(call_api("/api/memories/permanent"))
    if result.get("status") == "success":
        memories = result.get("memories", [])
        if not memories:
            return "暂无永久记忆"
        return "\n\n".join([
            f"【永久记忆】ID: {m.get('id', 'N/A')} | {m.get('content', '')[:200]} | 重要性: {m.get('importance_score', 1.0):.2f} | 标签: {', '.join(m.get('tags', [])[:3])}"
            for m in memories
        ])
    return "获取失败"


def batch_add_memories(memories_text: str):
    try:
        import json
        memories = json.loads(memories_text)
    except:
        return "✗ JSON格式错误"
    
    result = run_async(call_api("/api/memories/batch/write", {"memories": memories}, "POST"))
    if result.get("status") == "success":
        stats = result.get("result", {})
        return f"✓ 批量添加完成\n成功: {stats.get('success', 0)} | 失败: {stats.get('failed', 0)}"
    return f"✗ 批量添加失败: {result.get('error', '未知错误')}"


def get_decay_stats():
    result = run_async(call_api("/api/memories/decay-stats"))
    if result.get("status") == "success":
        stats = result.get("statistics", {})
        return (
            f"## 衰减统计\n"
            f"总记忆: {stats.get('total_memories', 0)}\n"
            f"永久记忆: {stats.get('permanent_count', 0)}\n"
            f"非永久记忆: {stats.get('non_permanent_count', 0)}\n"
            f"平均时间分: {stats.get('avg_time_score', 0):.4f}\n"
            f"平均重要性分: {stats.get('avg_importance_score', 0):.4f}\n\n"
            f"重激活统计:\n"
            f"  已重激活: {stats.get('reactivation_stats', {}).get('reactivated_count', 0)}\n"
            f"  平均重激活次数: {stats.get('reactivation_stats', {}).get('avg_reactivation_count', 0):.2f}"
        )
    return "获取失败"


def get_secondary_commands():
    result = run_async(call_api("/api/memories/secondary/commands"))
    if result.get("status") == "success":
        commands = result.get("commands", {})
        output = []
        for cmd_name, cmd_info in commands.items():
            output.append(
                f"**{cmd_name}**\n"
                f"  描述: {cmd_info.get('description', 'N/A')}\n"
                f"  参数: {json.dumps(cmd_info.get('parameters', {}), ensure_ascii=False)}"
            )
        return "\n\n".join(output)
    return "获取失败"


def execute_secondary_command(command: str, parameters: str):
    try:
        params = json.loads(parameters) if parameters else {}
    except:
        params = {}
    
    data = {
        "command": command,
        "parameters": params
    }
    result = run_async(call_api("/api/memories/secondary/execute", data, "POST"))
    if result.get("status") == "success":
        cmd_result = result.get("result", {})
        return (
            f"✓ 命令执行成功\n"
            f"命令: {cmd_result.get('command', 'N/A')}\n"
            f"状态: {cmd_result.get('status', 'N/A')}\n"
            f"执行时间: {cmd_result.get('execution_time_ms', 0):.2f}ms\n"
            f"输出: {json.dumps(cmd_result.get('output', {}), ensure_ascii=False)}"
        )
    return f"✗ 命令执行失败: {result.get('error', '未知错误')}"


def get_memory_list(memory_type: str = "all"):
    params = ""
    if memory_type != "all":
        params = f"?memory_type={memory_type}"
    result = run_async(call_api(f"/api/memories{params}"))
    if result.get("status") == "success":
        memories = result.get("memories", [])
        if not memories:
            return "暂无记忆"
        return "\n\n".join([
            f"【{m.get('type', 'unknown')}】{m.get('content', '')[:200]}...\nID: {m.get('id', 'N/A')} | 重要性: ⭐{m.get('importance', 3)}"
            for m in memories
        ])
    return "获取失败"


def delete_memory(memory_id: str):
    try:
        mid = int(memory_id)
    except (ValueError, TypeError):
        return "✗ 无效的ID"
    result = run_async(call_api(f"/api/memories/{mid}", method="DELETE"))
    if result.get("status") == "success":
        return "✓ 记忆已删除"
    return f"✗ 删除失败: {result.get('error', '未知错误')}"


def chat_with_ai(message: str, history: list):
    if not message.strip():
        return history

    data = {"message": message, "stream": False}
    result = run_async(call_api("/chat", data, "POST"))

    if result.get("status") == "success":
        response = result.get("response", "")
        session_id = result.get("session_id", "")

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})

        return history
    else:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": f"错误: {result.get('error', '未知错误')}"})
        return history


def clear_chat():
    return []


def create_chat_tab():
    with gr.TabItem("💬 聊天"):
        gr.Markdown("## 💬 AI对话")
        gr.Markdown("与AI助手进行对话，支持记忆检索和工具调用")

        chat_history = gr.Chatbot(
            label="对话历史",
            height=450
        )

        with gr.Row():
            msg_input = gr.Textbox(
                label="输入消息",
                placeholder="输入您的问题...",
                scale=5,
                lines=2
            )
            with gr.Column(scale=1):
                send_btn = gr.Button("发送")
                clear_btn = gr.Button("清空对话")

        gr.Markdown("*提示: AI会基于您的记忆库进行回答*")

        send_btn.click(chat_with_ai, [msg_input, chat_history], chat_history)
        msg_input.submit(chat_with_ai, [msg_input, chat_history], chat_history)
        clear_btn.click(clear_chat, None, chat_history)


def create_memory_tab():
    with gr.TabItem("🧠 记忆管理"):
        gr.Markdown("## 🧠 记忆管理系统")
        gr.Markdown("管理长期/短期/永久记忆，支持三维评分搜索、记忆召回和批量操作")

        with gr.Tabs():
            with gr.TabItem("📋 记忆列表"):
                mem_type_filter = gr.Dropdown(
                    ["all", "long_term", "short_term", "permanent"],
                    label="筛选类型",
                    value="all"
                )
                refresh_list_btn = gr.Button("刷新列表")
                memory_list = gr.Textbox(label="记忆列表", lines=12, interactive=False)
                gr.Markdown("### ➕ 添加记忆")
                mem_content = gr.Textbox(label="内容", lines=3, placeholder="输入记忆内容...")
                mem_type_new = gr.Dropdown(
                    ["long_term", "short_term", "permanent"],
                    label="记忆类型",
                    value="long_term"
                )
                mem_importance = gr.Slider(minimum=1, maximum=5, step=1, label="重要性", value=3)
                mem_tags = gr.Textbox(label="标签 (逗号分隔)", placeholder="工作, 重要")
                add_btn = gr.Button("添加记忆", variant="primary")
                add_result = gr.Textbox(label="添加结果", interactive=False)
                gr.Markdown("### 🔍 搜索记忆")
                search_query = gr.Textbox(label="搜索关键词", placeholder="输入搜索内容...")
                search_type = gr.Dropdown(
                    ["all", "long_term", "short_term", "permanent"],
                    label="记忆类型",
                    value="all"
                )
                search_btn = gr.Button("搜索", variant="primary")
                search_result = gr.Textbox(label="搜索结果", lines=10, interactive=False)
                gr.Markdown("### 🗑️ 删除记忆")
                del_id = gr.Textbox(label="记忆ID", placeholder="输入要删除的记忆ID")
                delete_btn = gr.Button("删除")
                delete_result = gr.Textbox(label="删除结果", interactive=False)

            with gr.TabItem("🔍 三维搜索"):
                gr.Markdown("### 🔍 三维评分搜索")
                gr.Markdown("基于重要性、时间、相关性三个维度进行智能搜索")
                search_3d_query = gr.Textbox(label="搜索关键词", placeholder="输入搜索内容...")
                search_3d_type = gr.Dropdown(
                    ["all", "long_term", "short_term"],
                    label="记忆类型",
                    value="all"
                )
                search_3d_weights = gr.Dropdown(
                    ["default", "importance", "time", "relevance"],
                    label="权重策略",
                    value="default"
                )
                search_3d_btn = gr.Button("三维搜索", variant="primary")
                search_3d_result = gr.Textbox(label="搜索结果", lines=10, interactive=False)

            with gr.TabItem("🔄 记忆召回"):
                gr.Markdown("### 🔄 记忆召回与重激活")
                gr.Markdown("召回记忆并增强其时间分数和情感分数")
                recall_id = gr.Textbox(label="记忆ID", placeholder="输入要召回的记忆ID")
                recall_emotion = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, label="情感强度", value=0.5)
                recall_btn = gr.Button("召回记忆", variant="primary")
                recall_result = gr.Textbox(label="召回结果", lines=8, interactive=False)

            with gr.TabItem("📦 永久记忆"):
                gr.Markdown("### 📦 永久记忆管理")
                gr.Markdown("永久记忆零衰减，适合存储重要信息")
                perm_list_btn = gr.Button("刷新永久记忆列表")
                perm_list = gr.Textbox(label="永久记忆", lines=10, interactive=False)
                gr.Markdown("### ➕ 添加永久记忆")
                perm_content = gr.Textbox(label="内容", lines=3, placeholder="输入永久记忆内容...")
                perm_tags = gr.Textbox(label="标签 (逗号分隔)", placeholder="重要, 用户偏好")
                perm_emotion = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, label="情感分数", value=0.5)
                perm_add_btn = gr.Button("添加永久记忆", variant="primary")
                perm_add_result = gr.Textbox(label="添加结果", interactive=False)

            with gr.TabItem("📊 批量操作"):
                gr.Markdown("### � 批量操作")
                gr.Markdown("批量添加、更新或删除记忆")
                batch_memories_text = gr.Textbox(
                    label="批量记忆 (JSON)",
                    lines=8,
                    placeholder='[{"content": "记忆1", "importance": 3}, {"content": "记忆2", "importance": 4}]',
                    value='[{"content": "示例记忆1", "importance": 3}, {"content": "示例记忆2", "importance": 4}]'
                )
                batch_add_btn = gr.Button("批量添加", variant="primary")
                batch_result = gr.Textbox(label="批量操作结果", lines=5, interactive=False)

            with gr.TabItem("📉 衰减统计"):
                gr.Markdown("### 📉 衰减统计信息")
                gr.Markdown("查看记忆系统的衰减分布和统计")
                decay_stats_btn = gr.Button("获取衰减统计")
                decay_stats_result = gr.Textbox(label="衰减统计", lines=10, interactive=False)

            with gr.TabItem("🤖 副模型命令"):
                gr.Markdown("### 🤖 副模型命令系统")
                gr.Markdown("执行副模型命令进行记忆管理")
                sec_cmds_btn = gr.Button("获取可用命令")
                sec_cmds_result = gr.Textbox(label="可用命令", lines=10, interactive=False)
                gr.Markdown("### ⚡ 执行命令")
                sec_cmd_name = gr.Dropdown(
                    ["summarize_memory", "archive_memory", "cleanup_memories", "analyze_importance",
                     "decay_memories", "get_memory_insights", "batch_process",
                     "summarize_conversation", "extract_key_points", "generate_memory_report"],
                    label="命令名称",
                    value="summarize_memory"
                )
                sec_cmd_params = gr.Textbox(
                    label="命令参数 (JSON)",
                    lines=3,
                    placeholder='{"memory_id": 123, "max_length": 200}'
                )
                sec_exec_btn = gr.Button("执行命令", variant="primary")
                sec_exec_result = gr.Textbox(label="执行结果", lines=8, interactive=False)

        refresh_list_btn.click(get_memory_list, [mem_type_filter], memory_list)
        add_btn.click(add_memory, [mem_content, mem_type_new, mem_importance, mem_tags], add_result)
        search_btn.click(search_memories, [search_query, search_type], search_result)
        delete_btn.click(delete_memory, [del_id], delete_result)
        search_3d_btn.click(search_memories_3d, [search_3d_query, search_3d_type, search_3d_weights], search_3d_result)
        recall_btn.click(recall_memory, [recall_id, recall_emotion], recall_result)
        perm_list_btn.click(get_permanent_memories, None, perm_list)
        
        # 创建隐藏组件来传递固定值
        perm_type_hidden = gr.Textbox(value="permanent", visible=False)
        perm_importance_hidden = gr.Number(value=5, visible=False)
        
        perm_add_btn.click(
            add_memory, 
            [perm_content, perm_type_hidden, perm_importance_hidden, perm_tags], 
            perm_add_result
        )
        batch_add_btn.click(batch_add_memories, [batch_memories_text], batch_result)
        decay_stats_btn.click(get_decay_stats, None, decay_stats_result)
        sec_cmds_btn.click(get_secondary_commands, None, sec_cmds_result)
        sec_exec_btn.click(execute_secondary_command, [sec_cmd_name, sec_cmd_params], sec_exec_result)


def create_acp_tab():
    def refresh_agents():
        result = run_async(call_api("/api/acp/agents"))
        if result.get("status") == "success":
            agents = result.get("agents", [])
            if not agents:
                return "未发现Agents"
            return "\n".join([
                f"🤖 **{a.get('name', 'Unknown')}**\n   地址: {a.get('host', 'N/A')}:{a.get('port', 0)}\n   状态: {a.get('status', 'unknown')} | 版本: {a.get('version', 'N/A')}"
                for a in agents
            ])
        return f"获取失败: {result.get('error', '未知错误')}"

    def refresh_groups():
        result = run_async(call_api("/api/acp/groups"))
        if result.get("status") == "success":
            groups = result.get("groups", [])
            if not groups:
                return "暂无群组"
            return "\n".join([
                f"👥 **{g.get('name', 'Unknown')}**\n   成员: {len(g.get('members', []))} | 创建: {g.get('creator_name', 'Unknown')}\n   ID: {g.get('id', 'N/A')[:8]}..."
                for g in groups
            ])
        return f"获取失败: {result.get('error', '未知错误')}"

    def refresh_connections():
        result = run_async(call_api("/api/acp/connections"))
        if result.get("status") == "success":
            connections = result.get("connections", [])
            if not connections:
                return "暂无连接"
            return "\n".join([
                f"🔗 **{c.get('remote_agent_name', 'Unknown')}**\n   状态: {c.get('status', 'unknown')}\n   地址: {c.get('host', 'N/A')}:{c.get('port', 0)}"
                for c in connections
            ])
        return f"获取失败: {result.get('error', '未知错误')}"

    def discover_agents(timeout_val: float):
        result = run_async(call_api("/api/acp/discover", {"timeout": timeout_val}, "POST"))
        if result.get("status") == "success":
            count = result.get("scanned_count", 0)
            return f"✓ 扫描完成，发现 {count} 个Agents"
        return f"✗ 扫描失败: {result.get('error', '未知错误')}"

    def create_group(name: str, description: str, max_members: int):
        result = run_async(call_api("/api/acp/groups", {"name": name, "description": description, "max_members": max_members}, "POST"))
        if result.get("status") == "success":
            return "✓ 群组创建成功", ""
        return f"✗ 创建失败: {result.get('error', '未知错误')}", name

    def join_group(group_id: str):
        if not group_id:
            return "请输入群组ID"
        result = run_async(call_api(f"/api/acp/groups/{group_id}/join", method="POST"))
        if result.get("status") == "success":
            return "✓ 已加入群组"
        return f"✗ 加入失败: {result.get('error', '未知错误')}"

    def get_stats():
        result = run_async(call_api("/api/acp/stats"))
        if result.get("status") == "success":
            stats = result.get("statistics", {})
            return f"🤖 Agents: {stats.get('total_agents', 0)} (在线: {stats.get('online_agents', 0)})\n👥 群组: {stats.get('total_groups', 0)}\n💬 消息: {stats.get('total_messages', 0)}"
        return "无法获取统计"

    with gr.TabItem("🔗 ACP互联"):
        gr.Markdown("## 🔗 ACP Connect 2.0")
        gr.Markdown("局域网Agent发现与互联 | 群组通讯 | 消息传递")

        stats_display = gr.Textbox(label="📊 统计信息", value=get_stats(), interactive=False, lines=2)

        with gr.Tabs():
            with gr.TabItem("🌐 发现"):
                with gr.Row():
                    timeout_slider = gr.Slider(minimum=1, maximum=30, value=5, label="扫描超时(秒)")
                    discover_btn = gr.Button("🔍 扫描网络", variant="primary")
                discover_status = gr.Textbox(label="状态", interactive=False)
                gr.Markdown("### 🤖 发现的Agents")
                agent_list = gr.Textbox(label="Agents", lines=8, interactive=False)
                refresh_agents_btn = gr.Button("刷新")

                discover_btn.click(discover_agents, [timeout_slider], discover_status)
                discover_btn.click(refresh_agents, None, agent_list)
                refresh_agents_btn.click(refresh_agents, None, agent_list)

            with gr.TabItem("🔗 连接"):
                gr.Markdown("### 当前连接")
                connection_list = gr.Textbox(label="连接列表", lines=8, interactive=False)
                refresh_conn_btn = gr.Button("刷新连接")
                refresh_conn_btn.click(refresh_connections, None, connection_list)

            with gr.TabItem("👥 群组"):
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.Markdown("### ➕ 创建群组")
                        group_name = gr.Textbox(label="群组名称", placeholder="输入群组名称")
                        group_desc = gr.Textbox(label="群组描述", placeholder="输入群组描述")
                        max_members = gr.Slider(minimum=2, maximum=100, value=50, label="最大成员数")
                        create_group_btn = gr.Button("创建群组")
                        create_result = gr.Textbox(label="创建结果", interactive=False)
                    with gr.Column(scale=2):
                        gr.Markdown("### 🚪 加入群组")
                        join_id = gr.Textbox(label="群组ID", placeholder="输入要加入的群组ID")
                        join_btn = gr.Button("加入群组")
                        join_result = gr.Textbox(label="操作结果", interactive=False)

                gr.Markdown("### 📋 群组列表")
                group_list = gr.Textbox(label="群组", lines=8, interactive=False)
                refresh_groups_btn = gr.Button("刷新群组")
                refresh_groups_btn.click(refresh_groups, None, group_list)

                create_group_btn.click(create_group, [group_name, group_desc, max_members], [create_result, group_name])
                join_btn.click(join_group, [join_id], join_result)


def create_context_tab():
    def get_sessions():
        result = run_async(call_api("/api/context/sessions"))
        if result.get("status") == "success":
            sessions = result.get("sessions", [])
            if not sessions:
                return "暂无会话"
            return "\n".join([
                f"💬 会话 #{s.get('id', 'N/A')[:8]}\n   消息数: {s.get('message_count', 0)} | 创建: {s.get('created_at', '')[:10]}"
                for s in sessions
            ])
        return "获取失败"

    def get_messages(session_id: str):
        if not session_id:
            return "请输入会话ID"
        result = run_async(call_api(f"/api/context/messages?session_id={session_id}"))
        if result.get("status") == "success":
            messages = result.get("messages", [])
            if not messages:
                return "暂无消息"
            return "\n".join([
                f"{'👤' if m.get('role') == 'user' else '🤖'}: {m.get('content', '')[:100]}..."
                for m in messages
            ])
        return f"获取失败: {result.get('error', '未知错误')}"

    def create_session(workspace_id: str = "default"):
        result = run_async(call_api("/api/context/sessions", {"workspace_id": workspace_id}, "POST"))
        if result.get("status") == "success":
            return f"✓ 会话创建成功 (ID: {result.get('session_id', 'N/A')[:8]}...)"
        return f"✗ 创建失败: {result.get('error', '未知错误')}"

    with gr.TabItem("💭 上下文"):
        gr.Markdown("## 💭 上下文管理")
        gr.Markdown("管理对话会话 | 消息历史 | 上下文窗口")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📋 会话列表")
                sessions_list = gr.Textbox(label="会话", lines=10, interactive=False)
                refresh_sessions_btn = gr.Button("刷新")
                refresh_sessions_btn.click(get_sessions, None, sessions_list)

            with gr.Column(scale=1):
                gr.Markdown("### 💬 消息历史")
                session_id_input = gr.Textbox(label="会话ID", placeholder="输入会话ID")
                get_msg_btn = gr.Button("获取消息")
                messages_display = gr.Textbox(label="消息", lines=8, interactive=False)

                gr.Markdown("### ➕ 创建会话")
                workspace_input = gr.Textbox(label="工作区ID", value="default")
                create_sess_btn = gr.Button("创建会话", variant="primary")
                create_sess_result = gr.Textbox(label="结果", interactive=False)

                get_msg_btn.click(get_messages, [session_id_input], messages_display)
                create_sess_btn.click(create_session, [workspace_input], create_sess_result)


def create_tools_tab():
    def get_tools():
        result = run_async(call_api("/api/tools"))
        if result.get("status") == "success":
            tools = result.get("tools", [])
            if not tools:
                return "暂无工具"
            return "\n".join([
                f"🔧 **{t.get('name', 'Unknown')}**\n   描述: {t.get('description', 'N/A')[:50]}..."
                for t in tools
            ])
        return "获取失败"

    def get_mcp_servers():
        result = run_async(call_api("/api/tools/mcp/servers"))
        if result.get("status") == "success":
            servers = result.get("servers", [])
            if not servers:
                return "暂无MCP服务器"
            return "\n".join([
                f"🖥️ **{s.get('name', 'Unknown')}**\n   状态: {s.get('status', 'unknown')}"
                for s in servers
            ])
        return "获取失败"

    def get_plugins():
        result = run_async(call_api("/api/tools/plugins"))
        if result.get("status") == "success":
            plugins = result.get("plugins", [])
            if not plugins:
                return "暂无插件"
            return "\n".join([
                f"🔌 **{p.get('name', 'Unknown')}** v{p.get('version', 'N/A')}"
                for p in plugins
            ])
        return "获取失败"

    with gr.TabItem("🛠️ 工具"):
        gr.Markdown("## 🛠️ 工具系统")
        gr.Markdown("工具注册表 | MCP服务器 | 插件管理")

        with gr.Tabs():
            with gr.TabItem("🔧 工具"):
                tools_list = gr.Textbox(label="已注册工具", lines=10, interactive=False)
                refresh_tools_btn = gr.Button("刷新工具列表")
                refresh_tools_btn.click(get_tools, None, tools_list)

            with gr.TabItem("🖥️ MCP"):
                mcp_list = gr.Textbox(label="MCP服务器", lines=10, interactive=False)
                refresh_mcp_btn = gr.Button("刷新")
                refresh_mcp_btn.click(get_mcp_servers, None, mcp_list)

            with gr.TabItem("🔌 插件"):
                plugins_list = gr.Textbox(label="插件", lines=10, interactive=False)
                refresh_plugins_btn = gr.Button("刷新")
                refresh_plugins_btn.click(get_plugins, None, plugins_list)


def create_admin_tab():
    def get_dashboard():
        result = run_async(call_api("/api/admin/dashboard"))
        if result.get("status") == "success":
            dashboard = result.get("dashboard", {})
            mem_stats = dashboard.get("memory", {})
            ctx_stats = dashboard.get("context", {})
            acp_stats = dashboard.get("acp", {})

            return f"""## 📊 系统仪表盘

### 🧠 记忆系统
- 总记忆: {mem_stats.get('total', 0)}
- 永久记忆: {mem_stats.get('permanent', 0)}
- 长期记忆: {mem_stats.get('by_type', {}).get('long_term', 0)}
- 短期记忆: {mem_stats.get('by_type', {}).get('short_term', 0)}

### 💭 上下文系统
- 会话总数: {ctx_stats.get('total_sessions', 0)}
- 活跃会话: {ctx_stats.get('active_sessions', 0)}
- 消息总数: {ctx_stats.get('total_messages', 0)}

### 🔗 ACP互联
- Agents: {acp_stats.get('total_agents', 0)}
- 在线: {acp_stats.get('online_agents', 0)}
- 群组: {acp_stats.get('total_groups', 0)}
- 消息: {acp_stats.get('total_messages', 0)}
"""
        return "获取仪表盘失败"

    def get_health():
        result = run_async(call_api("/api/admin/health"))
        if result.get("status") == "success":
            status = result.get("status", "unknown")
            components = result.get("components", {})
            uptime = result.get("uptime", "N/A")
            return f"""## 🏥 健康状态

**总体状态:** {status.upper()}
**运行时间:** {uptime}

### 组件状态
- 🧠 记忆: {components.get('memory', 'N/A')}
- 💭 上下文: {components.get('context', 'N/A')}
- 🔗 ACP: {components.get('acp', 'N/A')}
- 🤖 LLM: {components.get('llm', 'N/A')}
"""
        return "获取健康状态失败"

    def get_logs(level: str = "INFO", lines: int = 50):
        result = run_async(call_api(f"/api/admin/logs?level={level}&lines={lines}"))
        if result.get("status") == "success":
            logs = result.get("logs", [])
            if not logs:
                return "暂无日志"
            return "\n".join(logs[-lines:])
        return f"获取失败: {result.get('error', '未知错误')}"

    def backup():
        result = run_async(call_api("/api/admin/backup", method="POST"))
        if result.get("status") == "success":
            return f"✓ 备份成功: {result.get('path', 'N/A')}"
        return f"✗ 备份失败: {result.get('error', '未知错误')}"

    with gr.TabItem("📊 监控管理"):
        gr.Markdown("## 📊 系统监控")
        gr.Markdown("仪表盘 | 健康检查 | 日志 | 备份")

        with gr.Tabs():
            with gr.TabItem("📈 仪表盘"):
                dashboard = gr.Markdown(label="仪表盘")
                refresh_dash_btn = gr.Button("刷新仪表盘")
                refresh_dash_btn.click(get_dashboard, None, dashboard)

            with gr.TabItem("🏥 健康"):
                health = gr.Markdown(label="健康状态")
                refresh_health_btn = gr.Button("刷新")
                refresh_health_btn.click(get_health, None, health)

            with gr.TabItem("📋 日志"):
                log_level = gr.Dropdown(["DEBUG", "INFO", "WARNING", "ERROR"], label="日志级别", value="INFO")
                log_lines = gr.Slider(minimum=10, maximum=200, value=50, label="显示行数")
                logs_display = gr.Textbox(label="日志", lines=15, interactive=False)
                refresh_logs_btn = gr.Button("刷新日志")
                refresh_logs_btn.click(get_logs, [log_level, log_lines], logs_display)

            with gr.TabItem("💾 备份"):
                gr.Markdown("### 数据备份")
                backup_btn = gr.Button("创建备份", variant="primary")
                backup_result = gr.Textbox(label="备份结果", interactive=False)
                backup_btn.click(backup, None, backup_result)


def create_settings_tab():
    def get_config():
        try:
            result = run_async(call_api("/api/admin/config"))
            if result.get("status") == "success":
                config = result.get("config", {})
                import json
                return json.dumps(config, indent=2, ensure_ascii=False)
            return json.dumps({"error": "获取配置失败"}, indent=2, ensure_ascii=False)
        except Exception as e:
            import json
            return json.dumps({"error": f"加载配置时出错: {str(e)}"}, indent=2, ensure_ascii=False)

    def update_config(config_json: str):
        try:
            import json
            config = json.loads(config_json)
            result = run_async(call_api("/api/admin/config", config, "PUT"))
            if result.get("status") == "success":
                return "✓ 配置已更新，请重启服务生效"
            return f"✗ 更新失败: {result.get('error', '未知错误')}"
        except json.JSONDecodeError as e:
            return f"✗ JSON格式错误: {str(e)}"
        except Exception as e:
            return f"✗ 错误: {str(e)}"

    def validate_config(config_json: str):
        try:
            import json
            config = json.loads(config_json)
            errors = []

            if "llm" in config:
                llm = config["llm"]
                if "provider" not in llm:
                    errors.append("LLM: 缺少 provider")
                if "model" not in llm:
                    errors.append("LLM: 缺少 model")

            if "vector" in config:
                vector = config["vector"]
                if "port" in vector and not isinstance(vector["port"], int):
                    errors.append("Vector: port 必须是整数")

            if "system" in config:
                system = config["system"]
                if "port" in system and not isinstance(system["port"], int):
                    errors.append("System: port 必须是整数")

            if errors:
                return "⚠️ 配置验证失败:\n" + "\n".join(f"- {e}" for e in errors)
            return "✓ 配置格式正确"
        except json.JSONDecodeError as e:
            return f"✗ JSON格式错误: {str(e)}"
        except Exception as e:
            return f"✗ 验证错误: {str(e)}"

    def reset_config():
        try:
            import json
            default_config = {
                "llm": {
                    "provider": "ollama",
                    "host": "http://localhost:11434",
                    "model": "llama3.2",
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "vector": {
                    "enabled": True,
                    "host": "localhost",
                    "port": 6333,
                    "embedding_model": "nomic-embed-text"
                },
                "acp": {
                    "enabled": True,
                    "agent_id": "cxhms-agent-001",
                    "agent_name": "CXHMS Agent"
                },
                "system": {
                    "host": "0.0.0.0",
                    "port": 8000,
                    "debug": False,
                    "log_level": "INFO"
                }
            }
            return json.dumps(default_config, indent=2, ensure_ascii=False)
        except Exception as e:
            import json
            return json.dumps({"error": f"重置配置失败: {str(e)}"}, indent=2, ensure_ascii=False)

    def update_llm_config(provider: str, host: str, model: str, temperature: float, max_tokens: int):
        config = {
            "llm": {
                "provider": provider,
                "host": host,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        }
        result = run_async(call_api("/api/admin/config", config, "PUT"))
        if result.get("status") == "success":
            return "✓ LLM配置已更新"
        return f"✗ 更新失败: {result.get('error', '未知错误')}"

    def update_vector_config(
        enabled: bool, 
        backend: str, 
        milvus_db_path: str, 
        milvus_vector_size: int, 
        qdrant_host: str, 
        qdrant_port: int,
        provider: str,
        ollama_model: str,
        ollama_host: str,
        hf_model: str,
        hf_device: str,
        hf_normalize: bool,
        openai_model: str,
        openai_api_key: str,
        openai_dimensions: int,
        custom_type: str,
        custom_endpoint: str,
        custom_dimensions: int
    ):
        config = {
            "memory": {
                "vector_enabled": enabled,
                "vector_backend": backend,
                "milvus_lite": {
                    "db_path": milvus_db_path,
                    "vector_size": milvus_vector_size
                },
                "qdrant": {
                    "host": qdrant_host,
                    "port": qdrant_port
                }
            },
            "embedding": {
                "provider": provider,
                "ollama": {
                    "model": ollama_model,
                    "host": ollama_host
                },
                "huggingface": {
                    "model": hf_model,
                    "device": hf_device,
                    "normalize": hf_normalize
                },
                "openai": {
                    "model": openai_model,
                    "api_key": openai_api_key,
                    "dimensions": openai_dimensions
                },
                "custom": {
                    "type": custom_type,
                    "endpoint": custom_endpoint,
                    "dimensions": custom_dimensions
                }
            }
        }
        result = run_async(call_api("/api/admin/config", config, "PUT"))
        if result.get("status") == "success":
            return "✓ 向量配置已更新"
        return f"✗ 更新失败: {result.get('error', '未知错误')}"

    def update_acp_config(enabled: bool, agent_id: str, agent_name: str):
        config = {
            "acp": {
                "enabled": enabled,
                "agent_id": agent_id,
                "agent_name": agent_name
            }
        }
        result = run_async(call_api("/api/admin/config", config, "PUT"))
        if result.get("status") == "success":
            return "✓ ACP配置已更新"
        return f"✗ 更新失败: {result.get('error', '未知错误')}"

    def update_system_config(host: str, port: int, debug: bool, log_level: str):
        config = {
            "system": {
                "host": host,
                "port": int(port),
                "debug": debug,
                "log_level": log_level
            }
        }
        result = run_async(call_api("/api/admin/config", config, "PUT"))
        if result.get("status") == "success":
            return "✓ 系统配置已更新"
        return f"✗ 更新失败: {result.get('error', '未知错误')}"

    with gr.TabItem("⚙️ 设置"):
        gr.Markdown("## ⚙️ 系统设置")
        gr.Markdown("LLM配置 | 向量配置 | ACP配置 | 系统配置")

        with gr.Tabs():
            with gr.TabItem("🤖 LLM设置"):
                with gr.Row():
                    with gr.Column():
                        llm_provider = gr.Dropdown(
                            ["ollama", "vllm", "openai", "anthropic", "deepseek", "local"],
                            label="Provider",
                            value="ollama"
                        )
                        llm_host = gr.Textbox(label="Host", value="http://localhost:11434")
                        llm_model = gr.Textbox(label="Model", value="llama3.2")
                        llm_temperature = gr.Slider(minimum=0.0, maximum=2.0, step=0.1, label="Temperature", value=0.7)
                        llm_max_tokens = gr.Slider(minimum=512, maximum=8192, step=256, label="Max Tokens", value=4096)
                        llm_save_btn = gr.Button("保存LLM配置", variant="primary")
                        llm_result = gr.Textbox(label="结果", interactive=False)

                llm_save_btn.click(update_llm_config, [llm_provider, llm_host, llm_model, llm_temperature, llm_max_tokens], llm_result)

            with gr.TabItem("🔍 向量设置"):
                gr.Markdown("### 向量存储配置")
                gr.Markdown("选择并配置向量存储后端")
                
                vector_enabled = gr.Checkbox(label="启用向量搜索", value=True)
                
                vector_backend = gr.Dropdown(
                    ["milvus_lite", "qdrant"],
                    label="向量存储后端",
                    value="milvus_lite"
                )
                
                gr.Markdown("#### Milvus Lite 配置", visible=True)
                milvus_db_path = gr.Textbox(
                    label="数据库路径", 
                    value="data/milvus_lite.db",
                    visible=True
                )
                milvus_vector_size = gr.Number(
                    label="向量维度", 
                    value=768, 
                    precision=0,
                    visible=True
                )
                
                gr.Markdown("#### Qdrant 配置", visible=False)
                vector_host = gr.Textbox(
                    label="Host", 
                    value="localhost",
                    visible=False
                )
                vector_port = gr.Number(
                    label="Port", 
                    value=6333, 
                    precision=0,
                    visible=False
                )
                
                gr.Markdown("#### Embedding 模型配置")
                gr.Markdown("选择并配置Embedding模型")
                
                # Embedding模型选项卡
                with gr.Tabs():
                    with gr.TabItem("🤖 Ollama Embeddings"):
                        gr.Markdown("使用Ollama本地Embedding模型")
                        ollama_embedding_model = gr.Textbox(
                            label="模型名称", 
                            value="nomic-embed-text",
                            placeholder="例如: nomic-embed-text, mxbai-embed-large"
                        )
                        ollama_embedding_host = gr.Textbox(
                            label="Ollama Host", 
                            value="http://localhost:11434"
                        )
                    
                    with gr.TabItem("🤗 HuggingFace Embeddings"):
                        gr.Markdown("使用HuggingFace预训练模型")
                        hf_embedding_model = gr.Dropdown(
                            [
                                "sentence-transformers/all-MiniLM-L6-v2",
                                "sentence-transformers/all-mpnet-base-v2",
                                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                                "BAAI/bge-small-en-v1.5",
                                "BAAI/bge-base-en-v1.5",
                                "Thenlie/StreamTivation"
                            ],
                            label="选择模型",
                            value="sentence-transformers/all-MiniLM-L6-v2"
                        )
                        hf_embedding_device = gr.Dropdown(
                            ["cpu", "cuda"],
                            label="运行设备",
                            value="cpu"
                        )
                        hf_embedding_normalize = gr.Checkbox(
                            label="归一化向量", 
                            value=True
                        )
                    
                    with gr.TabItem("🌐 OpenAI Embeddings"):
                        gr.Markdown("使用OpenAI API Embedding模型")
                        openai_embedding_model = gr.Dropdown(
                            ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
                            label="选择模型",
                            value="text-embedding-3-small"
                        )
                        openai_embedding_api_key = gr.Textbox(
                            label="API Key", 
                            value="",
                            placeholder="sk-...",
                            type="password"
                        )
                        openai_embedding_dimensions = gr.Number(
                            label="向量维度 (可选)", 
                            value=1536,
                            precision=0
                        )
                    
                    with gr.TabItem("📝 本地/自定义"):
                        gr.Markdown("使用本地自定义Embedding模型")
                        custom_embedding_type = gr.Dropdown(
                            ["api", "local"],
                            label="类型",
                            value="api"
                        )
                        custom_embedding_endpoint = gr.Textbox(
                            label="API端点", 
                            value="http://localhost:8001/embed",
                            placeholder="http://localhost:8001/embed"
                        )
                        custom_embedding_dimensions = gr.Number(
                            label="向量维度", 
                            value=768,
                            precision=0
                        )
                
                # 当前选中的Embedding模型类型
                embedding_provider = gr.Dropdown(
                    ["ollama", "huggingface", "openai", "custom"],
                    label="当前使用的Embedding提供商",
                    value="ollama"
                )
                
                vector_save_btn = gr.Button("保存向量配置", variant="primary")
                vector_result = gr.Textbox(label="结果", interactive=False)

                def update_vector_backend_visibility(backend):
                    if backend == "milvus_lite":
                        return {
                            milvus_db_path: gr.update(visible=True),
                            milvus_vector_size: gr.update(visible=True),
                            vector_host: gr.update(visible=False),
                            vector_port: gr.update(visible=False)
                        }
                    else:
                        return {
                            milvus_db_path: gr.update(visible=False),
                            milvus_vector_size: gr.update(visible=False),
                            vector_host: gr.update(visible=True),
                            vector_port: gr.update(visible=True)
                        }

                vector_backend.change(
                    update_vector_backend_visibility,
                    [vector_backend],
                    [milvus_db_path, milvus_vector_size, vector_host, vector_port]
                )

                vector_save_btn.click(
                    update_vector_config, 
                    [
                        vector_enabled, 
                        vector_backend, 
                        milvus_db_path, 
                        milvus_vector_size, 
                        vector_host, 
                        vector_port,
                        embedding_provider,
                        ollama_embedding_model,
                        ollama_embedding_host,
                        hf_embedding_model,
                        hf_embedding_device,
                        hf_embedding_normalize,
                        openai_embedding_model,
                        openai_embedding_api_key,
                        openai_embedding_dimensions,
                        custom_embedding_type,
                        custom_embedding_endpoint,
                        custom_embedding_dimensions
                    ], 
                    vector_result
                )

            with gr.TabItem("🔗 ACP设置"):
                with gr.Row():
                    with gr.Column():
                        acp_enabled = gr.Checkbox(label="启用ACP", value=True)
                        acp_agent_id = gr.Textbox(label="Agent ID", value="cxhms-agent-001")
                        acp_agent_name = gr.Textbox(label="Agent名称", value="CXHMS Agent")
                        acp_save_btn = gr.Button("保存ACP配置", variant="primary")
                        acp_result = gr.Textbox(label="结果", interactive=False)

                acp_save_btn.click(update_acp_config, [acp_enabled, acp_agent_id, acp_agent_name], acp_result)

            with gr.TabItem("💻 系统设置"):
                with gr.Row():
                    with gr.Column():
                        system_host = gr.Textbox(label="Host", value="0.0.0.0")
                        system_port = gr.Number(label="Port", value=8000, precision=0)
                        system_debug = gr.Checkbox(label="Debug模式", value=False)
                        system_log_level = gr.Dropdown(["DEBUG", "INFO", "WARNING", "ERROR"], label="日志级别", value="INFO")
                        system_save_btn = gr.Button("保存系统配置", variant="primary")
                        system_result = gr.Textbox(label="结果", interactive=False)

                system_save_btn.click(update_system_config, [system_host, system_port, system_debug, system_log_level], system_result)

            with gr.TabItem("📝 JSON编辑"):
                gr.Markdown("### 高级配置编辑")
                gr.Markdown("直接编辑完整配置（JSON格式）")

                with gr.Row():
                    refresh_config_btn = gr.Button("🔄 刷新配置")
                    validate_config_btn = gr.Button("✅ 验证配置")
                    reset_config_btn = gr.Button("🔄 重置为默认值")

                config_editor = gr.Code(
                    label="JSON配置",
                    language="json",
                    lines=20,
                    value=get_config()
                )

                with gr.Row():
                    save_json_btn = gr.Button("💾 保存配置", variant="primary")
                    save_result = gr.Textbox(label="保存结果", interactive=False)

                refresh_config_btn.click(get_config, None, config_editor)
                validate_config_btn.click(validate_config, [config_editor], save_result)
                reset_config_btn.click(reset_config, None, config_editor)
                save_json_btn.click(update_config, [config_editor], save_result)


def create_app():
    with gr.Blocks(
        title="CXHMS - AI代理中间层服务"
    ) as app:
        gr.Markdown("""
        <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; margin-bottom: 20px;">
            <h1 style="color: white; margin: 0;">🚀 CXHMS - AI代理中间层服务</h1>
            <p style="color: white; opacity: 0.9; margin: 10px 0 0 0;">CX-O History & Memory Service</p>
        </div>
        """, elem_classes=["main"])

        with gr.Tabs():
            create_chat_tab()
            create_memory_tab()
            create_acp_tab()
            create_context_tab()
            create_tools_tab()
            create_admin_tab()
            create_settings_tab()

        gr.Markdown("---")
        gr.Markdown("*CXHMS v1.0.0 | Powered by Gradio | 🧠 记忆管理 | 🔗 ACP互联 | 🛠️ 工具调用*")

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        debug=True
    )
