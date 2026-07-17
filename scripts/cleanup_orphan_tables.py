"""清理孤儿 agent 记忆表（agent 已删除但表还在）。

清理范围：
1. DROP TABLE memories_{agent_id}（孤儿表）
2. DELETE FROM agent_memory_tables WHERE agent_id NOT IN (现有 agent ids)
3. DELETE FROM rejected_content WHERE session_id LIKE '{orphan_agent_id}%'

使用方式：
    python scripts/cleanup_orphan_tables.py          # 预览模式（不执行删除）
    python scripts/cleanup_orphan_tables.py --execute # 执行清理
"""
import json
import os
import sqlite3
import sys


def main():
    execute = "--execute" in sys.argv

    # 路径解析
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    db_path = os.path.join(project_root, "data", "memories.db")
    agents_path = os.path.join(project_root, "data", "agents.json")

    # 加载现有 agent ids
    with open(agents_path, "r", encoding="utf-8") as f:
        agents = json.load(f)
    existing_agent_ids = {a["id"] for a in agents}

    print(f"现有 agent ids: {existing_agent_ids}")
    print(f"模式: {'执行清理' if execute else '预览（不执行删除，加 --execute 执行）'}")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 查询 agent_memory_tables 中的所有记录
    cursor.execute("SELECT agent_id, table_name FROM agent_memory_tables")
    records = cursor.fetchall()

    orphan_records = [
        (agent_id, table_name)
        for agent_id, table_name in records
        if agent_id not in existing_agent_ids
    ]

    print(f"孤儿表数量: {len(orphan_records)}")
    for agent_id, table_name in orphan_records:
        # 统计表中的记录数
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  {agent_id} -> {table_name} ({count} 条记录)")

    if not orphan_records:
        print("无孤儿表需要清理")
        conn.close()
        return

    if not execute:
        print("\n[预览模式] 加 --execute 参数执行清理")
        conn.close()
        return

    # 执行清理
    print("\n[执行清理]")

    for agent_id, table_name in orphan_records:
        # 1. DROP TABLE
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        print(f"  DROP TABLE {table_name} ✓")

        # 2. DELETE FROM agent_memory_tables
        cursor.execute(
            "DELETE FROM agent_memory_tables WHERE agent_id = ?",
            (agent_id,),
        )
        print(f"  DELETE agent_memory_tables WHERE agent_id={agent_id} ✓ ({cursor.rowcount} 条)")

        # 3. DELETE FROM rejected_content（通过 session_id 前缀匹配）
        cursor.execute(
            "DELETE FROM rejected_content WHERE session_id LIKE ?",
            (f"{agent_id}%",),
        )
        if cursor.rowcount > 0:
            print(f"  DELETE rejected_content WHERE session_id LIKE '{agent_id}%' ✓ ({cursor.rowcount} 条)")

    conn.commit()
    conn.close()
    print("\n清理完成")


if __name__ == "__main__":
    main()
