"""模块11 独立知识库图片解析器测试（Task 4）。

全部用例通过 monkeypatch 注入假 `MultimodalPipeline`，不依赖真实 PaddleOCR /
vLLM，也不访问网络或真实模型服务。

覆盖：
    1. OCR + vision 成功 → parsed，text_content 含两者；
    2. text_content 为空时用 ocr_blocks 文本 + vision 描述；
    3. vision_degraded=True → parsed 且 metadata 标记；
    4. 合并后文本为空 → parsed 且 metadata 记录 empty_text=True；
    5. 模块导入失败 → failed + KNOWLEDGE_PARSE_FAILED（禁止 Mock 假成功）；
    6. 管线实例化失败 → failed + KNOWLEDGE_PARSE_FAILED；
    7. preprocess 抛异常 → failed + KNOWLEDGE_PARSE_FAILED；
    8. 文件不存在 → failed + KNOWLEDGE_PARSE_FAILED；
    9. 真实懒加载路径（sys.modules 注入假模块）可被调用。

运行方式：
    python -m pytest tests/units/test_knowledge_image_parser.py -q
"""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from backend.core.knowledge.parsers import image_parser
from backend.core.knowledge.parsers.base import KNOWLEDGE_PARSE_FAILED


# --------------------------------------------------------------------------- #
# 测试替身与工具
# --------------------------------------------------------------------------- #


def _artifact(
    text_content: str = "",
    ocr_blocks: list | None = None,
    vision_description: str = "",
    confidence: float = 0.9,
    vision_degraded: bool = False,
) -> SimpleNamespace:
    """构造假 MultimodalArtifact（字段对齐 modules/模块8_多模态管线）。"""
    return SimpleNamespace(
        text_content=text_content,
        extra_metadata={
            "ocr_blocks": list(ocr_blocks or []),
            "vision_description": vision_description,
        },
        confidence=confidence,
        vision_degraded=vision_degraded,
    )


def _install_fake_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    artifact: SimpleNamespace | None = None,
    init_error: Exception | None = None,
    preprocess_error: Exception | None = None,
):
    """注入假 MultimodalPipeline（patch image_parser 内部懒加载函数）。

    Returns:
        (calls, constructed)：
            calls: preprocess 调用记录 [(source_type, source_ref), ...]
            constructed: 构造时收到的 config 参数记录
    """
    calls: list = []
    constructed: list = []

    class FakePipeline:
        def __init__(self, config=None):
            constructed.append(config)
            if init_error is not None:
                raise init_error

        def preprocess(self, source_type, source_ref):
            calls.append((source_type, source_ref))
            if preprocess_error is not None:
                raise preprocess_error
            return artifact

    monkeypatch.setattr(image_parser, "_load_pipeline_class", lambda: FakePipeline)
    return calls, constructed


def _write_image(tmp_path, name: str = "sample.png"):
    """写入一个占位图片文件（内容无关，仅需存在且可 stat）。"""
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake-image-bytes")
    return path


# --------------------------------------------------------------------------- #
# 正向用例
# --------------------------------------------------------------------------- #


def test_parse_image_merges_ocr_and_vision(tmp_path, monkeypatch):
    """OCR + vision 成功 → parsed，text_content 同时含两者，并透传 config。"""
    path = _write_image(tmp_path)
    calls, constructed = _install_fake_pipeline(
        monkeypatch,
        artifact=_artifact(
            text_content="OCR文本: 街边招牌",
            ocr_blocks=[{"text": "第一行"}, {"text": "第二行"}],
            vision_description="一只猫坐在窗台上",
        ),
    )

    result = image_parser.parse_image(
        str(path), "sample.png", "image/png", {"ocr_language": "ch"}
    )

    assert result.parse_status == "parsed"
    assert result.parse_error is None
    assert "OCR文本: 街边招牌" in result.text_content
    assert "一只猫坐在窗台上" in result.text_content
    assert calls == [("image", str(path))]
    assert constructed == [{"ocr_language": "ch"}]
    assert result.source_refs == [str(path)]

    metadata = result.metadata
    assert metadata["vision_degraded"] is False
    assert metadata["confidence"] == pytest.approx(0.9)
    assert metadata["ocr_blocks_count"] == 2
    assert metadata["vision_chars"] == len("一只猫坐在窗台上")
    assert metadata["chars"] == len(result.text_content)
    assert metadata["mime"] == "image/png"


def test_parse_image_uses_ocr_blocks_when_text_empty(tmp_path, monkeypatch):
    """text_content 为空 → 使用 ocr_blocks 文本，并追加 vision 描述。"""
    path = _write_image(tmp_path)
    _install_fake_pipeline(
        monkeypatch,
        artifact=_artifact(
            text_content="",
            ocr_blocks=[{"text": "发票金额 128.00"}, {"text": "日期 2026-11-01"}],
            vision_description="一张购物小票照片",
        ),
    )

    result = image_parser.parse_image(str(path), "receipt.png", "image/png")

    assert result.parse_status == "parsed"
    assert "发票金额 128.00" in result.text_content
    assert "日期 2026-11-01" in result.text_content
    assert "一张购物小票照片" in result.text_content
    assert result.metadata["ocr_blocks_count"] == 2
    assert "empty_text" not in result.metadata


def test_parse_image_vision_degraded_still_parsed(tmp_path, monkeypatch):
    """vision_degraded=True → 仍 parsed，metadata 显式标记且 vision_chars=0。"""
    path = _write_image(tmp_path)
    _install_fake_pipeline(
        monkeypatch,
        artifact=_artifact(
            text_content="仅 OCR 文本",
            ocr_blocks=[{"text": "第一行"}],
            vision_description="",
            confidence=0.7,
            vision_degraded=True,
        ),
    )

    result = image_parser.parse_image(str(path), "degraded.png", "image/png")

    assert result.parse_status == "parsed"
    assert result.parse_error is None
    assert "仅 OCR 文本" in result.text_content
    assert result.metadata["vision_degraded"] is True
    assert result.metadata["vision_chars"] == 0


def test_parse_image_empty_text_marked(tmp_path, monkeypatch):
    """合并后文本为空 → parsed，metadata 记录 empty_text=True（不报错）。"""
    path = _write_image(tmp_path)
    _install_fake_pipeline(
        monkeypatch,
        artifact=_artifact(
            text_content="",
            ocr_blocks=[],
            vision_description="",
            confidence=0.7,
            vision_degraded=True,
        ),
    )

    result = image_parser.parse_image(str(path), "empty.png", "image/png")

    assert result.parse_status == "parsed"
    assert result.parse_error is None
    assert result.text_content == ""
    assert result.metadata["empty_text"] is True
    assert result.metadata["chars"] == 0
    assert result.metadata["ocr_blocks_count"] == 0


# --------------------------------------------------------------------------- #
# 失败用例
# --------------------------------------------------------------------------- #


def test_parse_image_module_import_failure_returns_failed(tmp_path, monkeypatch):
    """多模态管线模块导入失败 → failed + KNOWLEDGE_PARSE_FAILED（禁止假 parsed）。"""
    path = _write_image(tmp_path)

    def _boom():
        raise ImportError("No module named 'modules.模块8_多模态管线'")

    monkeypatch.setattr(image_parser, "_load_pipeline_class", _boom)

    result = image_parser.parse_image(str(path), "sample.png", "image/png")

    assert result.parse_status == "failed"
    assert result.parse_error == KNOWLEDGE_PARSE_FAILED
    assert result.text_content == ""
    assert "多模态管线不可用" in result.metadata["error"]


def test_parse_image_instantiation_failure_returns_failed(tmp_path, monkeypatch):
    """管线实例化失败 → failed + KNOWLEDGE_PARSE_FAILED。"""
    path = _write_image(tmp_path)

    class BoomPipeline:
        def __init__(self, config=None):
            raise RuntimeError("pipeline init failed")

    monkeypatch.setattr(image_parser, "_load_pipeline_class", lambda: BoomPipeline)

    result = image_parser.parse_image(str(path), "sample.png", "image/png")

    assert result.parse_status == "failed"
    assert result.parse_error == KNOWLEDGE_PARSE_FAILED
    assert result.text_content == ""


def test_parse_image_preprocess_error_returns_failed(tmp_path, monkeypatch):
    """preprocess 抛异常（如 OCR 引擎崩溃）→ failed + KNOWLEDGE_PARSE_FAILED。"""
    path = _write_image(tmp_path)
    _install_fake_pipeline(
        monkeypatch, preprocess_error=RuntimeError("OCR engine crashed")
    )

    result = image_parser.parse_image(str(path), "sample.png", "image/png")

    assert result.parse_status == "failed"
    assert result.parse_error == KNOWLEDGE_PARSE_FAILED
    assert result.text_content == ""
    assert "图片预处理失败" in result.metadata["error"]


def test_parse_image_missing_file_returns_failed(tmp_path, monkeypatch):
    """文件不存在 → failed + KNOWLEDGE_PARSE_FAILED，且不调用管线。"""
    calls, _ = _install_fake_pipeline(monkeypatch, artifact=_artifact("不应出现的文本"))
    missing = tmp_path / "missing.png"

    result = image_parser.parse_image(str(missing), "missing.png", "image/png")

    assert result.parse_status == "failed"
    assert result.parse_error == KNOWLEDGE_PARSE_FAILED
    assert result.text_content == ""
    assert calls == []


# --------------------------------------------------------------------------- #
# 懒加载路径（真实 import 分支）
# --------------------------------------------------------------------------- #


def test_parse_image_lazy_import_from_modules_package(tmp_path, monkeypatch):
    """通过 sys.modules 注入假模块，验证 `_load_pipeline_class` 的真实懒加载路径。"""
    path = _write_image(tmp_path)
    artifact = _artifact(
        text_content="OCR 文本",
        ocr_blocks=[{"text": "第一行"}],
        vision_description="照片描述",
    )

    class FakePipeline:
        def __init__(self, config=None):
            self.config = config

        def preprocess(self, source_type, source_ref):
            assert source_type == "image"
            assert source_ref == str(path)
            return artifact

    fake_module = ModuleType("modules.模块8_多模态管线")
    fake_module.MultimodalPipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "modules.模块8_多模态管线", fake_module)

    result = image_parser.parse_image(str(path), "sample.png", "image/png")

    assert result.parse_status == "parsed"
    assert "OCR 文本" in result.text_content
    assert "照片描述" in result.text_content
