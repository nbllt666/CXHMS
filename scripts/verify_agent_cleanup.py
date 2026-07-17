"""端到端验证：删除 agent 时清理 per-agent 记忆表（使用 httpx）"""
import json
import os
import re
import sqlite3
import time
import httpx

BACKEND = "http://127.0.0.1:8001"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "memories.db")


def check_table_exists(table_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def check_agent_memory_table_record(agent_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT agent_id, table_name FROM agent_memory_tables WHERE agent_id = ?",
        (agent_id,),
    )
    result = cursor.fetchone()
    conn.close()
    return result


def main():
    print("=" * 60)
    print("端到端验证：删除 agent 时清理 per-agent 记忆表")
    print("=" * 60)

    with httpx.Client(timeout=60.0) as client:
        # Step 1: 创建测试 agent
        print("\n[Step 1] 创建测试 agent...")
        resp = client.post(f"{BACKEND}/api/agents", json={
            "name": f"test-cleanup-{int(time.time())}",
            "description": "测试删除清理",
            "system_prompt": "你是一个测试助手",
            "model": "main",
            "temperature": 0.7,
            "use_memory": True,
            "use_tools": False,
            "memory_scene": "default",
        })
        assert resp.status_code == 200, f"创建 agent 失败: {resp.status_code} {resp.text}"
        agent_id = resp.json()["agent"]["id"]
        print(f"  ✓ agent_id: {agent_id}")

        # 预测表名
        safe_agent_id = re.sub(r"[^a-zA-Z0-9_]", "_", agent_id)
        if not re.match(r"^[a-zA-Z_]", safe_agent_id):
            safe_agent_id = "agent_" + safe_agent_id
        expected_table = f"memories_{safe_agent_id}"
        print(f"  ✓ 预期表名: {expected_table}")

        # Step 2: 写入记忆（触发 per-agent 表创建）
        print("\n[Step 2] 写入记忆（触发 per-agent 表创建）...")
        resp = client.post(f"{BACKEND}/api/memories", json={
            "content": "这是一条测试记忆，用于验证删除清理",
            "agent_id": agent_id,
            "memory_type": "short_term",
            "importance": 3,
        })
        assert resp.status_code == 200, f"写入记忆失败: {resp.status_code} {resp.text}"
        print(f"  ✓ 记忆已写入")

        # Step 3: 检查表已创建
        print("\n[Step 3] 检查 per-agent 表已创建...")
        time.sleep(0.5)
        table_exists = check_table_exists(expected_table)
        assert table_exists, f"表 {expected_table} 不存在"
        print(f"  ✓ 表 {expected_table} 已创建")

        record = check_agent_memory_table_record(agent_id)
        assert record is not None, f"agent_memory_tables 中无 {agent_id} 记录"
        print(f"  ✓ agent_memory_tables 记录: {record[0]} -> {record[1]}")

        # Step 4: 删除 agent
        print("\n[Step 4] 删除 agent...")
        resp = client.delete(f"{BACKEND}/api/agents/{agent_id}")
        assert resp.status_code == 200, f"删除 agent 失败: {resp.status_code} {resp.text}"
        print(f"  ✓ agent 已删除")

        # Step 5: 检查表已清理
        print("\n[Step 5] 检查 per-agent 表已清理...")
        time.sleep(1)
        table_exists = check_table_exists(expected_table)
        assert not table_exists, f"表 {expected_table} 仍存在（清理失败）"
        print(f"  ✓ 表 {expected_table} 已删除")

        record = check_agent_memory_table_record(agent_id)
        assert record is None, f"agent_memory_tables 中仍有 {agent_id} 记录（清理失败）"
        print(f"  ✓ agent_memory_tables 记录已清理")

    print("\n" + "=" * 60)
    print("✅ 端到端验证通过：删除 agent 时 per-agent 记忆表已正确清理")
    print("=" * 60)


if __name__ == "__main__":
    main()
