"""MultimodalPipeline 预生成 Mock 实现。

对应接口契约: public/interface_stub/multimodal_pipeline.pyi
对应数据契约: public/schema/multimodal_artifact.schema.json

Mock 策略:
- 返回符合 schema 的固定样例数据
- 3 模态（text / character_card / image）分发到对应 worker
- 异常路径通过 raise 模拟（ValueError=422 / FileNotFoundError=404 / RuntimeError=500）
- 真实实现就位后，切换导入路径即可替换

@version 1.0.0
@see public/interface_stub/multimodal_pipeline.pyi
@see public/schema/multimodal_artifact.schema.json
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# --------------------------------------------------------------------------- #
# 路径锚点（rules-0 §三：os.path.dirname(os.path.abspath(__file__))）
# --------------------------------------------------------------------------- #
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _iso_now() -> str:
    """返回 ISO 8601 带时区时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    """生成 UUID v4 字符串。"""
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Pydantic 模型（与 .pyi 存根保持一致，Mock 自包含）
# --------------------------------------------------------------------------- #


class MultimodalArtifact(BaseModel):
    """多模态预处理产物。字段与 multimodal_artifact.schema.json 一致。"""
    artifact_id: str
    type: str  # enum: text / character_card / image
    source: str
    text_content: str
    extra_metadata: Dict[str, Any] = {}
    confidence: float = 1.0
    vision_degraded: bool = False
    processing_time_ms: Optional[int] = None
    created_at: str


class OCRBlock(BaseModel):
    """OCR 文本块。"""
    text: str
    bbox: List[float]  # [x1, y1, x2, y2]


class CharacterCardFields(BaseModel):
    """角色卡字段（标准化后）。"""
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""


# --------------------------------------------------------------------------- #
# 枚举常量（与 multimodal_artifact.schema.json 一致）
# --------------------------------------------------------------------------- #

_SOURCE_TYPES = {"text", "character_card", "image"}

# 角色卡样例字段
_CHARACTER_CARD_FIELDS = CharacterCardFields(
    name="示例角色",
    description="一个用于 Mock 演示的虚构角色。",
    personality="温和、好奇、喜欢追问细节。",
    scenario="在 RADIX-Lite 项目中担任测试角色。",
    first_mes="你好，我是示例角色，很高兴认识你。",
    mes_example="{{user}}: 今天天气如何？\n{{char}}: 让我看看……今天是个晴天。",
)

# OCR 样例文本块
_OCR_BLOCKS = [
    OCRBlock(text="[Mock] 标题：RADIX-Lite", bbox=[10.0, 10.0, 300.0, 50.0]),
    OCRBlock(text="[Mock] 副标题：多模态预处理管线", bbox=[10.0, 60.0, 320.0, 100.0]),
    OCRBlock(text="[Mock] 正文：支持文本/角色卡/图片三模态。", bbox=[10.0, 110.0, 400.0, 150.0]),
]

# vision 描述样例
_VISION_DESCRIPTION = (
    "[Mock] 视觉描述：图片为一张技术架构图，包含 RADIX-Lite 三层结构，"
    "顶部为 DistillationService，中部为 DecisionCore，底部为 MemoryManager。"
)


class MockMultimodalPipeline:
    """MultimodalPipeline 的 Mock 实现。

    3 模态预处理，内存态产出统一 MultimodalArtifact。
    返回值通过 multimodal_artifact.schema.json 校验。
    """

    def __init__(self) -> None:
        # vision 是否可用（默认可用，可被测试设置为 False 模拟降级）
        self._vision_available: bool = True

    # ------------------------------------------------------------------ #
    # 公开 API
    # ------------------------------------------------------------------ #

    def preprocess(
        self,
        source_type: str,
        source_ref: str,
    ) -> MultimodalArtifact:
        """统一预处理入口。

        Mock behavior: 根据 source_type 分发到对应 worker。
        source_type 不在枚举中 raise ValueError。
        """
        if source_type not in _SOURCE_TYPES:
            raise ValueError(
                f"source_type 不在枚举中（422）: {source_type}"
            )
        if not source_ref:
            raise ValueError("source_ref 不能为空（422）")

        if source_type == "text":
            return self._text_worker(source_ref)
        elif source_type == "character_card":
            return self._character_card_worker(source_ref)
        else:  # image
            return self._image_worker(source_ref)

    # ------------------------------------------------------------------ #
    # 内部 worker
    # ------------------------------------------------------------------ #

    def _text_worker(self, source_ref: str) -> MultimodalArtifact:
        """内部方法：文本模态 worker。

        Mock behavior: 返回 type=text, confidence=1.0 的 artifact。
        extra_metadata 含 encoding/normalized 字段。
        """
        return MultimodalArtifact(
            artifact_id=_new_uuid(),
            type="text",
            source=source_ref,
            text_content=(
                f"[Mock] 归一化后的文本内容（来源：{source_ref}）。"
                "包含 NFKC 归一化与 strip 处理。"
            ),
            extra_metadata={
                "encoding": "utf-8",
                "normalized": True,
            },
            confidence=1.0,
            vision_degraded=False,
            processing_time_ms=5,
            created_at=_iso_now(),
        )

    def _character_card_worker(self, source_ref: str) -> MultimodalArtifact:
        """内部方法：角色卡模态 worker。

        Mock behavior: 返回 type=character_card 的 artifact。
        extra_metadata 含 CharacterCardFields 字段。
        """
        fields = _CHARACTER_CARD_FIELDS
        text_content = (
            f"[Mock] 角色卡字段：name={fields.name}, "
            f"description={fields.description}, "
            f"personality={fields.personality}"
        )
        return MultimodalArtifact(
            artifact_id=_new_uuid(),
            type="character_card",
            source=source_ref,
            text_content=text_content,
            extra_metadata=fields.model_dump(),
            confidence=0.95,
            vision_degraded=False,
            processing_time_ms=20,
            created_at=_iso_now(),
        )

    def _image_worker(self, source_ref: str) -> MultimodalArtifact:
        """内部方法：图片模态 worker（双通道）。

        Mock behavior: 调用 _ocr_worker + _vision_worker，合并结果。
        vision 不可用时 vision_degraded=True。
        """
        ocr_blocks = self._ocr_worker(source_ref)
        vision_degraded = False
        vision_description = ""

        if self._vision_available:
            vision_description = self._vision_worker(source_ref)
        else:
            vision_degraded = True

        return self._merge_ocr_vision(ocr_blocks, vision_description) if not vision_degraded else MultimodalArtifact(
            artifact_id=_new_uuid(),
            type="image",
            source=source_ref,
            text_content="\n".join(b.text for b in ocr_blocks),
            extra_metadata={
                "ocr_blocks": [b.model_dump() for b in ocr_blocks],
                "vision_description": "",
            },
            confidence=0.7,
            vision_degraded=True,
            processing_time_ms=150,
            created_at=_iso_now(),
        )

    def _ocr_worker(self, image_path: str) -> List[OCRBlock]:
        """内部方法：PaddleOCR worker。

        Mock behavior: 返回固定样例 OCR 文本块列表。
        """
        # Mock 不实际读取文件，仅校验参数非空
        if not image_path:
            raise RuntimeError("image_path 不能为空（500）")
        return list(_OCR_BLOCKS)

    def _vision_worker(self, image_path: str) -> str:
        """内部方法：vLLM vision worker。

        Mock behavior: 返回固定样例视觉描述。
        _vision_available=False 时 raise ConnectionError 触发降级。
        """
        if not self._vision_available:
            raise ConnectionError(
                "vLLM vision 端点不可用（503），触发降级路径"
            )
        if not image_path:
            raise RuntimeError("image_path 不能为空（500）")
        return _VISION_DESCRIPTION

    def _merge_ocr_vision(
        self,
        ocr_blocks: List[OCRBlock],
        vision_description: str,
    ) -> MultimodalArtifact:
        """内部方法：合并 OCR + vision 通道结果。

        Mock behavior: 合并 OCR 文本块 + vision 描述为统一 artifact。
        """
        ocr_text = "\n".join(b.text for b in ocr_blocks)
        combined = (
            f"{ocr_text}\n\n[Mock] 视觉描述：{vision_description}"
        ) if vision_description else ocr_text

        # vision 存在时置信度高，vision 为空时降级
        confidence = 0.92 if vision_description else 0.7
        vision_degraded = not bool(vision_description)

        return MultimodalArtifact(
            artifact_id=_new_uuid(),
            type="image",
            source="[Mock] merged_ocr_vision",
            text_content=combined,
            extra_metadata={
                "ocr_blocks": [b.model_dump() for b in ocr_blocks],
                "vision_description": vision_description,
            },
            confidence=confidence,
            vision_degraded=vision_degraded,
            processing_time_ms=180,
            created_at=_iso_now(),
        )
