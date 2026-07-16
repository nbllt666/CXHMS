"""模块8_多模态管线。

RADIX-Lite 多模态预处理管线（MultimodalPipeline）:
    - 3 模态预处理：文本 / 角色卡 / 图片
    - 统一产出 MultimodalArtifact
    - 图片模态支持 PaddleOCR + vLLM vision 双通道，vision 不可用时降级
    - 接管 parser.py 下沉的解析能力（Task 6 改造 parser.py 为 thin wrapper）

对应契约:
    - 接口: public/interface_stub/multimodal_pipeline.pyi
    - 数据: public/schema/multimodal_artifact.schema.json
    - 配置: public/config_template/radix_config.json（multimodal_pipeline + vllm 段）

@version 1.0.0
"""

from .multimodal_pipeline import (
    CharacterCardFields,
    MultimodalArtifact,
    MultimodalPipeline,
    OCRBlock,
)

__all__ = [
    "MultimodalPipeline",
    "MultimodalArtifact",
    "OCRBlock",
    "CharacterCardFields",
]
