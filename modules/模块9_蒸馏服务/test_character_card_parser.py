"""角色卡解析器单元测试。

覆盖：
    - JSON V1/V2/V3 解析
    - PNG tEXt chunk 解析（V2/V3）
    - 非标准字段保留
    - base64 编码兜底
    - character_card_to_source_ref 转换
"""

import base64
import io
import json
import os
import sys
import unittest

# 项目根目录
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from modules.模块9_蒸馏服务.character_card_parser import (
    character_card_to_source_ref,
    normalize_character_card,
    parse_character_card_from_bytes,
    parse_character_card_from_json_str,
    parse_json_character_card,
    parse_png_character_card,
)


def _make_png_with_text(text_key: str, json_str: str, use_base64: bool = False) -> bytes:
    """构造含 tEXt chunk 的 PNG 文件。

    Args:
        text_key: tEXt 关键字（"chara" 或 "chara_card_v3"）
        json_str: 角色卡 JSON 字符串
        use_base64: 是否 base64 编码

    Returns:
        bytes: PNG 文件二进制数据
    """
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    data = json_str
    if use_base64:
        data = base64.b64encode(json_str.encode("utf-8")).decode("ascii")

    img = Image.new("RGB", (100, 100), color="red")
    pnginfo = PngInfo()
    pnginfo.add_text(text_key, data)
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=pnginfo)
    return buf.getvalue()


class TestJsonParsing(unittest.TestCase):
    """JSON 角色卡解析测试。"""

    def test_v1_flat_format(self):
        """V1 格式：扁平化 JSON，无 spec/data。"""
        v1_json = json.dumps({
            "name": "测试角色",
            "description": "描述",
            "first_mes": "你好",
            "mes_example": "示例对话",
        })
        result = parse_character_card_from_json_str(v1_json)
        self.assertEqual(result["name"], "测试角色")
        self.assertEqual(result["description"], "描述")
        self.assertEqual(result["first_mes"], "你好")
        self.assertEqual(result["spec"], "v1_legacy")

    def test_v2_format(self):
        """V2 格式：spec + data 嵌套。"""
        v2_json = json.dumps({
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {
                "name": "V2角色",
                "description": "V2描述",
                "first_mes": "V2开场白",
                "personality": "V2性格",
            },
        })
        result = parse_character_card_from_json_str(v2_json)
        self.assertEqual(result["name"], "V2角色")
        self.assertEqual(result["description"], "V2描述")
        self.assertEqual(result["first_mes"], "V2开场白")
        self.assertEqual(result["personality"], "V2性格")
        self.assertEqual(result["spec"], "chara_card_v2")
        self.assertEqual(result["spec_version"], "2.0")

    def test_v3_format(self):
        """V3 格式：spec + data 嵌套。"""
        v3_json = json.dumps({
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": "V3角色",
                "description": "V3描述",
                "alternate_greetings": ["问候1", "问候2"],
                "system_prompt": "系统提示",
            },
        })
        result = parse_character_card_from_json_str(v3_json)
        self.assertEqual(result["name"], "V3角色")
        self.assertEqual(result["alternate_greetings"], ["问候1", "问候2"])
        self.assertEqual(result["system_prompt"], "系统提示")
        self.assertEqual(result["spec"], "chara_card_v3")

    def test_missing_name_defaults(self):
        """缺少 name 字段时使用默认值。"""
        json_str = json.dumps({"description": "无名角色"})
        result = parse_character_card_from_json_str(json_str)
        self.assertEqual(result["name"], "未命名角色")

    def test_non_standard_fields_preserved(self):
        """非标准字段保留到 extra_fields。"""
        json_str = json.dumps({
            "name": "测试",
            "custom_field": "自定义值",
            "another_extra": {"nested": "data"},
            "description": "标准字段",
        })
        result = parse_character_card_from_json_str(json_str)
        self.assertEqual(result["name"], "测试")
        self.assertEqual(result["description"], "标准字段")
        self.assertIn("custom_field", result["extra_fields"])
        self.assertEqual(result["extra_fields"]["custom_field"], "自定义值")
        self.assertIn("another_extra", result["extra_fields"])


class TestPngParsing(unittest.TestCase):
    """PNG 角色卡解析测试。"""

    def test_png_v2_chara_key(self):
        """PNG V2 格式：chara 关键字。"""
        card_json = json.dumps({
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {"name": "PNG V2角色", "first_mes": "PNG开场白"},
        })
        png_bytes = _make_png_with_text("chara", card_json)
        result = parse_png_character_card(png_bytes)
        # parse_png 返回原始数据，需 normalize
        normalized = normalize_character_card(result)
        self.assertEqual(normalized["name"], "PNG V2角色")
        self.assertEqual(normalized["first_mes"], "PNG开场白")

    def test_png_v3_key_priority(self):
        """PNG V3 关键字优先于 V2。"""
        v2_data = {"name": "V2", "description": "V2描述"}
        v3_data = {"spec": "chara_card_v3", "spec_version": "3.0",
                   "data": {"name": "V3", "description": "V3描述"}}
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        img = Image.new("RGB", (50, 50), color="blue")
        pnginfo = PngInfo()
        pnginfo.add_text("chara", json.dumps(v2_data))
        pnginfo.add_text("chara_card_v3", json.dumps(v3_data))
        buf = io.BytesIO()
        img.save(buf, format="PNG", pnginfo=pnginfo)

        result = parse_png_character_card(buf.getvalue())
        normalized = normalize_character_card(result)
        self.assertEqual(normalized["name"], "V3")
        self.assertEqual(normalized["description"], "V3描述")

    def test_png_base64_encoded(self):
        """PNG base64 编码的 JSON。"""
        card_json = json.dumps({"name": "Base64角色", "first_mes": "编码测试"})
        png_bytes = _make_png_with_text("chara", card_json, use_base64=True)
        result = parse_png_character_card(png_bytes)
        normalized = normalize_character_card(result)
        self.assertEqual(normalized["name"], "Base64角色")

    def test_png_no_card_data_raises(self):
        """PNG 无角色卡数据时抛异常。"""
        from PIL import Image

        img = Image.new("RGB", (50, 50), color="green")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        with self.assertRaises(ValueError) as ctx:
            parse_png_character_card(buf.getvalue())
        self.assertIn("未找到角色卡数据", str(ctx.exception))


class TestSourceRefConversion(unittest.TestCase):
    """character_card_to_source_ref 转换测试。"""

    def test_standard_fields_conversion(self):
        """标准字段转换为带标签文本。"""
        card = {
            "name": "林夕",
            "description": "温柔的诗人",
            "personality": "温柔、敏感",
            "first_mes": "你好",
            "mes_example": "示例",
        }
        source_ref = character_card_to_source_ref(card)
        self.assertIn("角色名: 林夕", source_ref)
        self.assertIn("描述: 温柔的诗人", source_ref)
        self.assertIn("性格: 温柔、敏感", source_ref)
        self.assertIn("开场白: 你好", source_ref)
        self.assertIn("对话示例: 示例", source_ref)

    def test_alternate_greetings_conversion(self):
        """备选问候语转换。"""
        card = {
            "name": "测试",
            "alternate_greetings": ["问候1", "问候2"],
        }
        source_ref = character_card_to_source_ref(card)
        self.assertIn("备选问候语 1: 问候1", source_ref)
        self.assertIn("备选问候语 2: 问候2", source_ref)

    def test_extra_fields_conversion(self):
        """非标准字段转换。"""
        card = {
            "name": "测试",
            "extra_fields": {
                "custom_field": "自定义值",
                "nested_field": {"key": "value"},
            },
        }
        source_ref = character_card_to_source_ref(card)
        self.assertIn("额外字段 - custom_field: 自定义值", source_ref)
        self.assertIn("额外字段 - nested_field:", source_ref)

    def test_empty_fields_skipped(self):
        """空字段跳过。"""
        card = {
            "name": "测试",
            "description": "",
            "first_mes": "有内容",
            "personality": "",
        }
        source_ref = character_card_to_source_ref(card)
        self.assertIn("角色名: 测试", source_ref)
        self.assertNotIn("描述:", source_ref)
        self.assertIn("开场白: 有内容", source_ref)
        self.assertNotIn("性格:", source_ref)


class TestBytesParsing(unittest.TestCase):
    """parse_character_card_from_bytes 测试。"""

    def test_json_bytes(self):
        """JSON 字节解析。"""
        json_bytes = json.dumps({
            "name": "字节角色",
            "first_mes": "测试",
        }).encode("utf-8")
        result = parse_character_card_from_bytes(json_bytes, "card.json")
        self.assertEqual(result["name"], "字节角色")

    def test_png_bytes_by_filename(self):
        """PNG 字节解析（按文件名判断）。"""
        card_json = json.dumps({"name": "PNG角色", "description": "PNG"})
        png_bytes = _make_png_with_text("chara", card_json)
        result = parse_character_card_from_bytes(png_bytes, "card.png")
        self.assertEqual(result["name"], "PNG角色")

    def test_png_bytes_by_magic_number(self):
        """PNG 字节解析（按魔术数字判断，无文件名）。"""
        card_json = json.dumps({"name": "魔术数字角色"})
        png_bytes = _make_png_with_text("chara_card_v3", card_json)
        result = parse_character_card_from_bytes(png_bytes, "")
        self.assertEqual(result["name"], "魔术数字角色")


if __name__ == "__main__":
    unittest.main(verbosity=2)
