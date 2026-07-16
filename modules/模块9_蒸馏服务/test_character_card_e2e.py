"""角色卡导入功能端到端 API 级测试。

验证：
    - POST /api/v1/distillation/parse-character-card（JSON 内容 + PNG 文件上传）
    - POST /api/v1/distillation/start-from-character-card（启动蒸馏）
"""

import io
import json
import os
import sys
import unittest

import requests

# 项目根目录
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_ROOT)

BACKEND_URL = "http://127.0.0.1:8001"


def _make_png_with_text(text_key: str, json_str: str) -> bytes:
    """构造含 tEXt chunk 的 PNG。"""
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    img = Image.new("RGB", (100, 100), color="red")
    pnginfo = PngInfo()
    pnginfo.add_text(text_key, json_str)
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=pnginfo)
    return buf.getvalue()


class TestParseCharacterCard(unittest.TestCase):
    """parse-character-card 端点测试。"""

    def test_parse_json_content_v2(self):
        """JSON 内容方式（V2 格式）。"""
        v2_card = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {
                "name": "E2E测试角色",
                "description": "端到端测试",
                "first_mes": "你好，我是测试角色",
                "mes_example": "用户：你好\n角色：你好呀",
                "personality": "温柔",
                "alternate_greetings": ["另一个开场白"],
            },
        }
        r = requests.post(
            f"{BACKEND_URL}/api/v1/distillation/parse-character-card",
            json={"json_content": v2_card},
            timeout=10,
        )
        self.assertEqual(r.status_code, 200, f"HTTP {r.status_code}: {r.text}")
        data = r.json()
        self.assertEqual(data["status"], "success")
        card = data["character_card_data"]
        self.assertEqual(card["name"], "E2E测试角色")
        self.assertEqual(card["first_mes"], "你好，我是测试角色")
        self.assertEqual(card["alternate_greetings"], ["另一个开场白"])
        # source_ref 应包含标签
        self.assertIn("角色名: E2E测试角色", data["source_ref"])
        self.assertIn("开场白: 你好", data["source_ref"])

    def test_parse_json_content_non_standard(self):
        """非标准角色卡（含额外字段）。"""
        card = {
            "name": "非标准角色",
            "description": "有额外字段",
            "custom_power": "火球术",
            "custom_level": 99,
        }
        r = requests.post(
            f"{BACKEND_URL}/api/v1/distillation/parse-character-card",
            json={"json_content": card},
            timeout=10,
        )
        self.assertEqual(r.status_code, 200, f"HTTP {r.status_code}: {r.text}")
        data = r.json()
        card_data = data["character_card_data"]
        self.assertEqual(card_data["name"], "非标准角色")
        self.assertIn("custom_power", card_data["extra_fields"])
        self.assertEqual(card_data["extra_fields"]["custom_power"], "火球术")
        self.assertIn("额外字段 - custom_power: 火球术", data["source_ref"])

    def test_parse_png_file_upload(self):
        """PNG 文件上传方式。"""
        card_json = json.dumps({
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {"name": "PNG上传角色", "first_mes": "从PNG导入"},
        })
        png_bytes = _make_png_with_text("chara", card_json)

        r = requests.post(
            f"{BACKEND_URL}/api/v1/distillation/parse-character-card",
            files={"file": ("test.png", png_bytes, "image/png")},
            timeout=10,
        )
        self.assertEqual(r.status_code, 200, f"HTTP {r.status_code}: {r.text}")
        data = r.json()
        self.assertEqual(data["character_card_data"]["name"], "PNG上传角色")
        self.assertIn("角色名: PNG上传角色", data["source_ref"])

    def test_parse_invalid_json_raises_400(self):
        """无效 JSON 返回 400。"""
        r = requests.post(
            f"{BACKEND_URL}/api/v1/distillation/parse-character-card",
            json={"json_content": "not valid json {{{"},
            timeout=10,
        )
        self.assertEqual(r.status_code, 400)


class TestStartFromCharacterCard(unittest.TestCase):
    """start-from-character-card 端点测试。"""

    def test_start_distillation_from_card(self):
        """从角色卡启动蒸馏会话。"""
        card_data = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "name": "蒸馏启动测试",
            "description": "测试从角色卡启动蒸馏",
            "first_mes": "你好，我是蒸馏测试角色",
            "personality": "友好",
        }
        r = requests.post(
            f"{BACKEND_URL}/api/v1/distillation/start-from-character-card",
            json={
                "character_card_data": card_data,
                "template_id": "default",
                "max_turns": 2,
                "distillation_goal": "memory",
                "chunk_size": 10000,
            },
            timeout=30,
        )
        self.assertEqual(r.status_code, 200, f"HTTP {r.status_code}: {r.text}")
        data = r.json()
        self.assertEqual(data["status"], "success")
        distillation = data["distillation"]
        self.assertIn("session_group_id", distillation)
        self.assertIn("sessions", distillation)
        self.assertGreaterEqual(distillation["total_chunks"], 1)
        # 验证 session 已创建
        session_id = distillation["sessions"][0]["session_id"]
        self.assertTrue(session_id)

        # 清理：查询 session 状态确认存在
        r2 = requests.get(
            f"{BACKEND_URL}/api/v1/distillation/{session_id}",
            timeout=10,
        )
        self.assertEqual(r2.status_code, 200)


if __name__ == "__main__":
    # 先检查服务
    try:
        r = requests.get(f"{BACKEND_URL}/api/agents", timeout=30)
        if r.status_code != 200:
            print(f"后端不可用: HTTP {r.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"后端连接失败: {e}")
        sys.exit(1)

    unittest.main(verbosity=2)
