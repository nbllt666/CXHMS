"""检查默认 memories 表中的记忆，看是否有角色卡蒸馏的记忆混入"""
import sqlite3
import os
import json

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "memories.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查默认 memories 表
print("=== 默认 memories 表 ===")
cursor.execute("SELECT COUNT(*) FROM memories")
print(f"总记录数: {cursor.fetchone()[0]}")

cursor.execute("SELECT id, agent_id, memory_type, tags, metadata, substr(content, 1, 80) FROM memories ORDER BY id DESC LIMIT 20")
rows = cursor.fetchall()
print(f"\n最近 20 条记忆:")
for row in rows:
    mem_id, agent_id, mem_type, tags, metadata, content_preview = row
    try:
        tags_list = json.loads(tags) if tags else []
    except:
        tags_list = []
    try:
        meta_dict = json.loads(metadata) if metadata else {}
    except:
        meta_dict = {}
    source = meta_dict.get("source", "")
    print(f"  id={mem_id}, agent_id={agent_id}, type={mem_type}, tags={tags_list}, source={source}")
    print(f"    content: {content_preview}")

# 检查是否有 distillation 来源的记忆
print("\n=== 蒸馏来源的记忆（source=distillation_service）===")
cursor.execute("SELECT id, agent_id, tags, substr(content, 1, 80) FROM memories WHERE metadata LIKE '%distillation_service%' ORDER BY id")
rows = cursor.fetchall()
print(f"数量: {len(rows)}")
for row in rows:
    print(f"  id={row[0]}, agent_id={row[1]}, tags={row[2]}, content={row[3]}")

# 检查所有 per-agent 表
print("\n=== per-agent 表 ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'memories_%' AND name NOT LIKE 'memories_fts%' ORDER BY name")
tables = [r[0] for r in cursor.fetchall()]
for table in tables:
    cursor.execute(f"SELECT id, agent_id, tags, substr(content, 1, 80) FROM {table} ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    print(f"\n{table} (最近 5 条):")
    for row in rows:
        print(f"  id={row[0]}, agent_id={row[1]}, tags={row[2]}, content={row[3]}")

# 检查现有 agents
print("\n=== 现有 agents ===")
agents_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "agents.json")
with open(agents_path, "r", encoding="utf-8") as f:
    agents = json.load(f)
for a in agents:
    print(f"  id={a['id']}, name={a['name']}, model={a.get('model', 'N/A')}")

conn.close()
