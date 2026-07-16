"""MultimodalPipeline 实例化测试（Task 3 验证）。

验证内容:
    1. text 模态预处理产出 MultimodalArtifact，通过 multimodal_artifact.schema 校验
    2. character_card 模态（JSON 字符串）预处理 + schema 校验
    3. image 模态降级路径（vision 不可用 → vision_degraded=True）
    4. _merge_ocr_vision 合并 + schema 校验
    5. 错误路径（无效 source_type / 空 source_ref / 缺 name 字段）

运行方式:
    $env:PYTHONPATH = "."; python -m pytest tests/contract/test_multimodal_pipeline_unit.py -v

@version 1.0.0
@see .trae/specs/add-management-agent-radix/spec.md (Task 3 闭合判据)
"""

import json
import os
import sys
from pathlib import Path

import jsonschema
import pytest

# 路径锚点（rules-0 §三）
_THIS_FILE = os.path.abspath(__file__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from modules.模块8_多模态管线 import (  # noqa: E402
    CharacterCardFields,
    MultimodalArtifact,
    MultimodalPipeline,
    OCRBlock,
)

_SCHEMA_PATH = (
    Path(_PROJECT_ROOT) / "public" / "schema" / "multimodal_artifact.schema.json"
)


def _load_schema() -> dict:
    """加载 multimodal_artifact 数据契约 schema。"""
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _assert_artifact_schema_valid(artifact: MultimodalArtifact) -> None:
    """断言 artifact 通过 multimodal_artifact.schema.json 校验。"""
    schema = _load_schema()
    data = artifact.model_dump()
    # jsonschema.validate 不 raise 即通过
    jsonschema.validate(data, schema)


# =========================================================================== #
# 一、text 模态预处理
# =========================================================================== #


class TestTextModality:
    """text 模态预处理验证。"""

    def test_text_preprocess_returns_artifact(self):
        """preprocess(text) 返回 MultimodalArtifact 实例。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="测试文本")
        assert isinstance(artifact, MultimodalArtifact)

    def test_text_artifact_type_is_text(self):
        """artifact.type == 'text'。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="测试文本")
        assert artifact.type == "text"

    def test_text_artifact_text_content_nonempty(self):
        """artifact.text_content 非空。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="测试文本")
        assert artifact.text_content != ""
        assert "测试文本" in artifact.text_content

    def test_text_artifact_confidence_is_1(self):
        """artifact.confidence == 1.0。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="测试文本")
        assert artifact.confidence == 1.0

    def test_text_artifact_schema_valid(self):
        """artifact 通过 multimodal_artifact.schema 校验。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="hello world")
        _assert_artifact_schema_valid(artifact)

    def test_text_nfkc_normalization(self):
        """NFKC 归一化：全角字母/数字转半角。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(
            source_type="text", source_ref="ＡＢＣ１２３"
        )
        # NFKC 将全角转为半角
        assert artifact.text_content == "ABC123"

    def test_text_strip_whitespace(self):
        """strip 首尾空白。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(
            source_type="text", source_ref="   hello   "
        )
        assert artifact.text_content == "hello"

    def test_text_artifact_id_is_uuid_v4(self):
        """artifact_id 为 UUID v4 格式（36 字符，含 4 个连字符）。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="x")
        assert len(artifact.artifact_id) == 36
        # UUID v4 第 3 段以 4 开头
        assert artifact.artifact_id.split("-")[2].startswith("4")

    def test_text_artifact_created_at_iso8601(self):
        """created_at 为 ISO 8601 带时区格式。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="x")
        # jsonschema date-time 校验
        _assert_artifact_schema_valid(artifact)

    def test_text_artifact_vision_degraded_false(self):
        """text 模态 vision_degraded=False。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="x")
        assert artifact.vision_degraded is False

    def test_text_artifact_processing_time_ms_set(self):
        """processing_time_ms 被填充。"""
        pipeline = MultimodalPipeline()
        artifact = pipeline.preprocess(source_type="text", source_ref="x")
        assert artifact.processing_time_ms is not None
        assert artifact.processing_time_ms >= 0


# =========================================================================== #
# 二、character_card 模态预处理
# =========================================================================== #


class TestCharacterCardModality:
    """character_card 模态预处理验证。"""

    def test_character_card_json_string(self):
        """JSON 字符串角色卡预处理。"""
        pipeline = MultimodalPipeline()
        card = json.dumps(
            {
                "name": "测试角色",
                "description": "一个测试角色",
                "personality": "温和",
            }
        )
        artifact = pipeline.preprocess(
            source_type="character_card", source_ref=card
        )
        assert artifact.type == "character_card"
        assert artifact.confidence == 0.95
        assert artifact.extra_metadata["name"] == "测试角色"
        assert artifact.extra_metadata["personality"] == "温和"

    def test_character_card_schema_valid(self):
        """character_card artifact 通过 schema 校验。"""
        pipeline = MultimodalPipeline()
        card = json.dumps({"name": "角色A"})
        artifact = pipeline.preprocess(
            source_type="character_card", source_ref=card
        )
        _assert_artifact_schema_valid(artifact)

    def test_character_card_missing_name_raises(self):
        """角色卡缺 name 字段 raise ValueError（422）。"""
        pipeline = MultimodalPipeline()
        card = json.dumps({"description": "无名字"})
        with pytest.raises(ValueError):
            pipeline.preprocess(source_type="character_card", source_ref=card)

    def test_character_card_invalid_json_raises(self):
        """非法 JSON raise ValueError（422）。"""
        pipeline = MultimodalPipeline()
        with pytest.raises(ValueError):
            pipeline.preprocess(
                source_type="character_card", source_ref="{invalid json"
            )


# =========================================================================== #
# 三、image 模态降级路径
# =========================================================================== #


class TestImageModalityDegraded:
    """image 模态降级路径验证。

    vision 不可用时（vision_model 默认空），_vision_worker raise ConnectionError，
    _image_worker 捕获后 vision_degraded=True。
    """

    @pytest.fixture
    def temp_png(self, tmp_path):
        """生成临时 PNG 图片用于测试。"""
        from PIL import Image

        img_path = tmp_path / "test.png"
        Image.new("RGB", (32, 32), "white").save(img_path)
        return str(img_path)

    def test_vision_worker_raises_when_not_configured(self, temp_png):
        """vision_model 为空时 _vision_worker raise ConnectionError（503）。"""
        pipeline = MultimodalPipeline()  # 默认 vision_model=""
        assert pipeline._vision_model == ""
        with pytest.raises(ConnectionError):
            pipeline._vision_worker(temp_png)

    def test_image_worker_degraded_when_vision_unavailable(
        self, monkeypatch, temp_png
    ):
        """vision 不可用时 _image_worker 降级（vision_degraded=True）。

        monkeypatch OCR 返回固定 blocks，避免依赖 PaddleOCR 安装。
        """
        pipeline = MultimodalPipeline()
        # 替换 OCR 为固定返回（绕过 PaddleOCR 依赖）
        fake_blocks = [
            {"text": "fake OCR line 1", "bbox": [0.0, 0.0, 100.0, 20.0]},
            {"text": "fake OCR line 2", "bbox": [0.0, 25.0, 100.0, 45.0]},
        ]
        monkeypatch.setattr(
            pipeline._image_worker_impl, "ocr", lambda path: (fake_blocks, 0.85)
        )

        artifact = pipeline.preprocess(
            source_type="image", source_ref=temp_png
        )
        assert artifact.type == "image"
        assert artifact.vision_degraded is True
        assert "fake OCR line 1" in artifact.text_content
        assert "fake OCR line 2" in artifact.text_content
        assert artifact.extra_metadata["vision_description"] == ""

    def test_image_degraded_artifact_schema_valid(self, monkeypatch, temp_png):
        """降级 artifact 通过 schema 校验。"""
        pipeline = MultimodalPipeline()
        fake_blocks = [{"text": "ocr text", "bbox": [0.0, 0.0, 50.0, 10.0]}]
        monkeypatch.setattr(
            pipeline._image_worker_impl, "ocr", lambda path: (fake_blocks, 0.8)
        )
        artifact = pipeline.preprocess(
            source_type="image", source_ref=temp_png
        )
        _assert_artifact_schema_valid(artifact)

    def test_image_degraded_confidence_is_07(self, monkeypatch, temp_png):
        """降级时 confidence=0.7。"""
        pipeline = MultimodalPipeline()
        fake_blocks = [{"text": "x", "bbox": [0.0, 0.0, 10.0, 10.0]}]
        monkeypatch.setattr(
            pipeline._image_worker_impl, "ocr", lambda path: (fake_blocks, 0.95)
        )
        artifact = pipeline.preprocess(
            source_type="image", source_ref=temp_png
        )
        assert artifact.vision_degraded is True
        assert artifact.confidence == 0.7


# =========================================================================== #
# 四、_merge_ocr_vision 合并
# =========================================================================== #


class TestMergeOcrVision:
    """_merge_ocr_vision 合并验证。"""

    def test_merge_with_vision(self):
        """双通道合并：vision_degraded=False。"""
        pipeline = MultimodalPipeline()
        blocks = [
            OCRBlock(text="line1", bbox=[0.0, 0.0, 100.0, 20.0]),
            OCRBlock(text="line2", bbox=[0.0, 25.0, 100.0, 45.0]),
        ]
        artifact = pipeline._merge_ocr_vision(blocks, "图片描述内容")
        assert artifact.type == "image"
        assert artifact.vision_degraded is False
        assert "line1" in artifact.text_content
        assert "line2" in artifact.text_content
        assert "图片描述内容" in artifact.text_content
        _assert_artifact_schema_valid(artifact)

    def test_merge_without_vision_degraded(self):
        """降级合并：vision 为空 → vision_degraded=True, confidence=0.7。"""
        pipeline = MultimodalPipeline()
        blocks = [OCRBlock(text="only ocr", bbox=[0.0, 0.0, 50.0, 10.0])]
        artifact = pipeline._merge_ocr_vision(blocks, "")
        assert artifact.vision_degraded is True
        assert artifact.confidence == 0.7
        _assert_artifact_schema_valid(artifact)

    def test_merge_extra_metadata_contains_ocr_blocks(self):
        """extra_metadata 含 ocr_blocks 列表。"""
        pipeline = MultimodalPipeline()
        blocks = [OCRBlock(text="t", bbox=[1.0, 2.0, 3.0, 4.0])]
        artifact = pipeline._merge_ocr_vision(blocks, "desc")
        assert "ocr_blocks" in artifact.extra_metadata
        assert len(artifact.extra_metadata["ocr_blocks"]) == 1
        assert artifact.extra_metadata["vision_description"] == "desc"


# =========================================================================== #
# 五、错误路径
# =========================================================================== #


class TestErrorPaths:
    """错误路径验证。"""

    def test_invalid_source_type_raises_value_error(self):
        """无效 source_type raise ValueError（422）。"""
        pipeline = MultimodalPipeline()
        with pytest.raises(ValueError):
            pipeline.preprocess(source_type="audio", source_ref="x")

    def test_empty_source_ref_raises_value_error(self):
        """空 source_ref raise ValueError（422）。"""
        pipeline = MultimodalPipeline()
        with pytest.raises(ValueError):
            pipeline.preprocess(source_type="text", source_ref="")

    def test_disabled_modality_raises_value_error(self):
        """未启用的模态 raise ValueError（422）。"""
        pipeline = MultimodalPipeline(
            config={"enabled_modalities": ["text"]}
        )
        with pytest.raises(ValueError):
            pipeline.preprocess(source_type="image", source_ref="x")


# =========================================================================== #
# 六、模型完整性
# =========================================================================== #


class TestModelsIntegrity:
    """数据模型完整性验证（与 .pyi 存根对齐）。"""

    def test_ocr_block_fields(self):
        """OCRBlock 含 text + bbox（严格匹配 .pyi，无 confidence）。"""
        block = OCRBlock(text="hello", bbox=[0.0, 0.0, 10.0, 20.0])
        assert block.text == "hello"
        assert block.bbox == [0.0, 0.0, 10.0, 20.0]
        # .pyi 仅定义 text + bbox，不含 confidence
        assert not hasattr(block, "confidence")

    def test_character_card_fields_defaults(self):
        """CharacterCardFields 缺失字段补默认空串。"""
        fields = CharacterCardFields(name="角色")
        assert fields.name == "角色"
        assert fields.description == ""
        assert fields.personality == ""
        assert fields.scenario == ""
        assert fields.first_mes == ""
        assert fields.mes_example == ""

    def test_multimodal_artifact_all_fields(self):
        """MultimodalArtifact 含全部字段（与 .pyi + schema 对齐）。"""
        artifact = MultimodalArtifact(
            artifact_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            type="text",
            source="test",
            text_content="hello",
            created_at="2026-07-15T10:00:00+00:00",
        )
        assert artifact.confidence == 1.0
        assert artifact.vision_degraded is False
        assert artifact.processing_time_ms is None
        assert artifact.extra_metadata == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
