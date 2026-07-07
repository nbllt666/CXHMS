"""注入多条 diary_summary 到 agent-default.json，用于测试多条横幅渲染效果。
执行完成后刷新前端页面验证。
"""
import json
import uuid
from datetime import datetime

# 读取现有 JSON
json_path = "data/context/agent-default.json"
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# 确保第一条 diary_summary 存在（已有）
existing_summaries = [m for m in data["messages"] if m.get("content_type") == "diary_summary" and not m.get("is_deleted", False)]
print(f"Existing diary_summaries: {len(existing_summaries)}")

# 新增 2 条 diary_summary（模拟不同时间的摘要）
new_summaries = [
    {
        "id": str(uuid.uuid4()),
        "role": "system",
        "content": "[上下文摘要 | 时间范围: 2026-07-07 21:20:00 ~ 2026-07-07 21:21:00 | 当日第2次摘要]\n用户请求搜索与计算相关的记忆，助手成功检索到多条历史记录并给出了详细总结。这展示了系统的语义检索能力。",
        "content_type": "diary_summary",
        "metadata": {
            "is_diary_summary": True,
            "summarized_up_to": 4,
            "time_range": {"start": "2026-07-07 21:20:00", "end": "2026-07-07 21:21:00"},
            "sequence": 2
        },
        "tokens": 0,
        "created_at": "2026-07-07T21:21:00.000000",
        "is_deleted": False
    },
    {
        "id": str(uuid.uuid4()),
        "role": "system",
        "content": "[上下文摘要 | 时间范围: 2026-07-07 21:25:00 ~ 2026-07-07 21:26:00 | 当日第3次摘要]\n用户与助手进行了关于系统功能的讨论，测试了工具调用和记忆管理功能。交互流畅且反馈及时。",
        "content_type": "diary_summary",
        "metadata": {
            "is_diary_summary": True,
            "summarized_up_to": 6,
            "time_range": {"start": "2026-07-07 21:25:00", "end": "2026-07-07 21:26:00"},
            "sequence": 3
        },
        "tokens": 0,
        "created_at": "2026-07-07T21:26:00.000000",
        "is_deleted": False
    },
]

# 插入到消息列表头部（按时间倒序，最新的在最前）
for s in reversed(new_summaries):
    data["messages"].insert(0, s)

# 更新 session 的 message_count
data["session"]["message_count"] = len([m for m in data["messages"] if not m.get("is_deleted", False)])

# 写回文件
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Injected {len(new_summaries)} new diary_summaries. Total: {len([m for m in data['messages'] if m.get('content_type') == 'diary_summary' and not m.get('is_deleted', False)])}")