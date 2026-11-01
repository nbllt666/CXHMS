"""模块11 Task 3 文本解析与统一路由测试。

覆盖：
    1. TXT / MD 正向解析（parsed 且 text_content 非空）
    2. 旧版 `.doc` → unsupported
    3. 未知 MIME → unsupported
    4. 不存在路径 → failed 且 parse_error 非空
    5. MIME 兜底：application/octet-stream + .md → document 且 parsed
    6. 基座工具（文件名清洗 / MIME 推断 / MIME 分类）
    7. 白名单拒绝 → unsupported
    8. 媒体解析器模块缺失 → failed（禁止 Mock 假成功）
    9. 文档大小超限 → ParseError（router 转 failed）

运行方式：
    python -m pytest tests/units/test_knowledge_text_parser.py -q
"""

import sys

import pytest

from backend.core.knowledge.parsers import text_parser
from backend.core.knowledge.parsers.base import (
    KNOWLEDGE_PARSE_FAILED,
    KNOWLEDGE_UNSUPPORTED_MIME,
    ParseError,
    ParseResult,
    classify_mime,
    infer_mime,
    sanitize_filename,
)
from backend.core.knowledge.parsers.router import parse
from backend.core.knowledge.parsers.text_parser import parse_text_document


def _write(tmp_path, name: str, content: bytes) -> str:
    """在临时目录写入文件并返回绝对路径。"""
    target = tmp_path / name
    target.write_bytes(content)
    return str(target)


# --------------------------------------------------------------------------- #
# 1. 文本类正向解析
# --------------------------------------------------------------------------- #
def test_txt_document_parsed(tmp_path):
    """TXT 文件经统一入口解析为 parsed 且文本非空。"""
    path = _write(tmp_path, "note.txt", "知识库测试文本".encode("utf-8"))
    result = parse(path, "note.txt", "text/plain")

    assert isinstance(result, ParseResult)
    assert result.parse_status == "parsed"
    assert result.text_content.strip()
    assert "知识库测试文本" in result.text_content
    assert result.parse_error is None
    assert result.metadata["chars"] == len(result.text_content)
    assert result.metadata["mime"] == "text/plain"


def test_markdown_document_parsed(tmp_path):
    """Markdown 文件经 parse_text_document 解析为 parsed。"""
    path = _write(tmp_path, "readme.md", "# 标题\n\n正文内容\n".encode("utf-8"))
    result = parse_text_document(path, "readme.md", "text/markdown")

    assert result.parse_status == "parsed"
    assert "# 标题" in result.text_content
    assert result.metadata["mime"] == "text/markdown"


# --------------------------------------------------------------------------- #
# 2. 旧版 .doc → unsupported
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mime", ["application/msword", "application/octet-stream"])
def test_legacy_doc_unsupported(tmp_path, mime):
    """任意字节的 .doc 文件均判为 unsupported（不抛异常）。"""
    path = _write(tmp_path, "legacy.doc", b"\x00\x01binary-doc-bytes")
    result = parse(path, "legacy.doc", mime)

    assert result.parse_status == "unsupported"
    assert result.parse_error
    assert KNOWLEDGE_UNSUPPORTED_MIME in result.parse_error
    assert result.text_content == ""


# --------------------------------------------------------------------------- #
# 3. 未知 MIME → unsupported
# --------------------------------------------------------------------------- #
def test_unknown_mime_unsupported(tmp_path):
    """未知 MIME 与未知扩展名 → unsupported 且携带 KNOWLEDGE_UNSUPPORTED_MIME。"""
    path = _write(tmp_path, "data.xyz", b"whatever")
    result = parse(path, "data.xyz", "application/x-unknown-format")

    assert result.parse_status == "unsupported"
    assert result.parse_error == "KNOWLEDGE_UNSUPPORTED_MIME: 不支持的 MIME 类型 application/x-unknown-format"
    assert result.text_content == ""


# --------------------------------------------------------------------------- #
# 4. 不存在路径 → failed
# --------------------------------------------------------------------------- #
def test_missing_file_failed(tmp_path):
    """源文件不存在时返回 failed 且 parse_error 非空，不抛出异常。"""
    missing = str(tmp_path / "not-exists.txt")
    result = parse(missing, "not-exists.txt", "text/plain")

    assert result.parse_status == "failed"
    assert result.parse_error == KNOWLEDGE_PARSE_FAILED
    assert result.metadata["error"]
    assert result.text_content == ""


# --------------------------------------------------------------------------- #
# 5. MIME 兜底
# --------------------------------------------------------------------------- #
def test_octet_stream_falls_back_to_extension_markdown(tmp_path):
    """mime=application/octet-stream + .md → 识别为 document 并 parsed。"""
    path = _write(tmp_path, "fallback.md", "兜底识别正文".encode("utf-8"))
    result = parse(path, "fallback.md", "application/octet-stream")

    assert result.parse_status == "parsed"
    assert "兜底识别正文" in result.text_content
    assert result.metadata["mime"] == "text/markdown"


def test_octet_stream_falls_back_to_extension_pdf(tmp_path):
    """mime 为空 + .pdf → MIME 兜底为 application/pdf（走 document 分支）。"""
    path = _write(tmp_path, "fake.pdf", b"%PDF-1.4 not a real pdf")
    result = parse(path, "fake.pdf", "")

    assert result.metadata["mime"] == "application/pdf"
    assert result.parse_status in ("parsed", "failed", "unsupported")


# --------------------------------------------------------------------------- #
# 6. 基座工具
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\secret.txt", "secret.txt"),
        ("a/b/c.txt", "c.txt"),
        ("bad\x00name.txt", "badname.txt"),
        ("", "unnamed"),
        ("   ", "unnamed"),
        ("..", "unnamed"),
    ],
)
def test_sanitize_filename(raw, expected):
    """文件名清洗：去穿越/路径/控制字符，空值回退 unnamed。"""
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize(
    ("filename", "mime", "expected"),
    [
        ("report.pdf", "application/octet-stream", "application/pdf"),
        ("doc.docx", "", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("old.doc", "application/octet-stream", "application/msword"),
        ("note.md", "application/octet-stream", "text/markdown"),
        ("note.txt", "text/plain", "text/plain"),
        ("photo.jpeg", "", "image/jpeg"),
        ("voice.m4a", "", "audio/mp4"),
        ("movie.mkv", "application/octet-stream", "video/x-matroska"),
        ("unknown.zzz", "", "application/octet-stream"),
    ],
)
def test_infer_mime(filename, mime, expected):
    """MIME 兜底推断：octet-stream/空值按扩展名映射，否则原样返回。"""
    assert infer_mime(filename, mime) == expected


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("application/pdf", "document"),
        ("application/msword", "document"),
        ("text/plain; charset=utf-8", "document"),
        ("image/png", "image"),
        ("audio/mpeg", "audio"),
        ("video/mp4", "video"),
        ("application/zip", "unsupported"),
        ("", "unsupported"),
    ],
)
def test_classify_mime(mime, expected):
    """MIME 分类：document / image / audio / video / unsupported。"""
    assert classify_mime(mime) == expected


# --------------------------------------------------------------------------- #
# 7. 白名单拒绝
# --------------------------------------------------------------------------- #
def test_config_whitelist_rejects_markdown(tmp_path):
    """配置白名单不含 text/markdown 时判为 unsupported。"""
    path = _write(tmp_path, "blocked.md", "内容".encode("utf-8"))
    result = parse(
        path,
        "blocked.md",
        "text/markdown",
        config={"allowed_document_mimes": ["text/plain"]},
    )

    assert result.parse_status == "unsupported"
    assert KNOWLEDGE_UNSUPPORTED_MIME in result.parse_error


# --------------------------------------------------------------------------- #
# 8. 媒体解析器缺失 → failed（禁止 Mock 假成功）
# --------------------------------------------------------------------------- #
def test_media_parser_missing_returns_failed(tmp_path, monkeypatch):
    """image 解析器模块不可导入 → failed + KNOWLEDGE_PARSE_FAILED，不产生假文本。"""
    path = _write(tmp_path, "photo.png", b"\x89PNG-fake")
    monkeypatch.setitem(sys.modules, "backend.core.knowledge.parsers.image_parser", None)

    result = parse(path, "photo.png", "image/png")

    assert result.parse_status == "failed"
    assert result.parse_error == KNOWLEDGE_PARSE_FAILED
    assert result.text_content == ""
    assert "不可用" in result.metadata["error"]


# --------------------------------------------------------------------------- #
# 9. 文档大小超限
# --------------------------------------------------------------------------- #
def test_document_size_limit_raises_parse_error(tmp_path, monkeypatch):
    """超过 max_document_size_mb 时 parse_text_document 抛 ParseError。"""
    path = _write(tmp_path, "big.txt", b"12345")
    monkeypatch.setattr(text_parser, "DEFAULT_MAX_DOCUMENT_SIZE_MB", 0)

    with pytest.raises(ParseError) as exc_info:
        parse_text_document(path, "big.txt", "text/plain")

    assert "超过上限" in str(exc_info.value)
    assert exc_info.value.parse_error == KNOWLEDGE_PARSE_FAILED


def test_document_size_limit_router_returns_failed(tmp_path, monkeypatch):
    """大小超限经 router 统一转为 failed，不向调用方抛出。"""
    path = _write(tmp_path, "big.txt", b"12345")
    monkeypatch.setattr(text_parser, "DEFAULT_MAX_DOCUMENT_SIZE_MB", 0)

    result = parse(path, "big.txt", "text/plain")

    assert result.parse_status == "failed"
    assert result.parse_error == KNOWLEDGE_PARSE_FAILED
    assert result.metadata["error"]
