"""模块11 独立知识库音视频解析器单元测试。

覆盖（全部 monkeypatch，不依赖真实 ffmpeg / ASR / OCR）：
    1. 音频正向：抽音轨 + 转写 → parsed，且 text_content 非空、metadata 齐全；
    2. 音频空转写：failed + KNOWLEDGE_PARSE_FAILED（不得 parsed 空文本）；
    3. 音频 ASR 不可用：failed + KNOWLEDGE_ASR_UNAVAILABLE；
    4. 音频 ffmpeg 不可用：failed + KNOWLEDGE_FFMPEG_UNAVAILABLE；
    5. 媒体时长超限：unsupported + KNOWLEDGE_MEDIA_TOO_LONG；
    6. 视频正向：音轨转写 + 带时间戳帧描述合并 → parsed；
    7. 视频 ASR 不可用：降级但继续抽帧，仍 parsed；
    8. 视频 ffmpeg 不可用：整体 failed + KNOWLEDGE_FFMPEG_UNAVAILABLE；
    9. 视频帧数受 video_max_frames 限制；
    10. 音轨与帧描述皆空：failed + KNOWLEDGE_PARSE_FAILED；
    11. 临时目录清理：cleanup_paths 收到整个临时目录且目录消失。

运行方式：
    python -m pytest tests/units/test_knowledge_media_parsers.py -q
"""

from __future__ import annotations

import os
import shutil

import pytest

from backend.core.knowledge.exceptions import (
    KnowledgeASRUnavailableError,
    KnowledgeFFmpegUnavailableError,
)
from backend.core.knowledge.parsers import audio_parser, video_parser
from backend.core.knowledge.parsers.base import ParseResult

MEDIA_TOO_LONG = "KNOWLEDGE_MEDIA_TOO_LONG"
PARSE_FAILED = "KNOWLEDGE_PARSE_FAILED"
ASR_UNAVAILABLE = "KNOWLEDGE_ASR_UNAVAILABLE"
FFMPEG_UNAVAILABLE = "KNOWLEDGE_FFMPEG_UNAVAILABLE"


@pytest.fixture
def media_file(tmp_path):
    """生成一个真实存在的假媒体文件，满足文件存在性校验。"""

    def _make(name: str = "sample.mp3", payload: bytes = b"fake-media-bytes") -> str:
        target = tmp_path / name
        target.write_bytes(payload)
        return str(target)

    return _make


def _patch_cleanup(monkeypatch, parser_module, calls: list) -> None:
    """替换 cleanup_paths：记录调用参数并真实删除，便于断言无临时残留。"""

    def fake_cleanup(paths):
        calls.append(list(paths))
        for target in paths:
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.exists(target):
                try:
                    os.remove(target)
                except OSError:
                    pass

    monkeypatch.setattr(parser_module.media, "cleanup_paths", fake_cleanup)


def _make_asr_class(transcript: str = "", metadata: dict | None = None, error=None):
    """构造可注入的 ASRClient 替身类。"""

    class FakeASR:
        def __init__(self, config):
            self.config = dict(config or {})

        def is_available(self) -> bool:
            return error is None

        def transcribe(self, audio_path):
            if error is not None:
                raise error
            return transcript, dict(metadata or {})

    return FakeASR


def _patch_extract_audio(monkeypatch, parser_module, recorded: dict) -> None:
    """替换 extract_audio：记录目标 WAV 路径，不真正执行 ffmpeg。"""

    def fake_extract_audio(src, dst, sample_rate=16000):
        recorded["src"] = src
        recorded["dst"] = dst
        recorded["sample_rate"] = sample_rate
        return dst

    monkeypatch.setattr(parser_module.media, "extract_audio", fake_extract_audio)


def test_parse_audio_returns_parsed_with_transcript(monkeypatch, media_file):
    """正向音频：抽音轨 + ASR 转写非空 → parsed。"""
    source = media_file("meeting.mp3")
    cleanup_calls: list = []
    extracted: dict = {}

    monkeypatch.setattr(audio_parser.media, "probe_duration", lambda _path: 95.0)
    _patch_extract_audio(monkeypatch, audio_parser, extracted)
    _patch_cleanup(monkeypatch, audio_parser, cleanup_calls)

    fake_asr_class = _make_asr_class(
        "这是一段示例转写",
        {"language": "zh", "provider": "mock", "segments": 4},
    )
    monkeypatch.setattr(audio_parser, "ASRClient", fake_asr_class)

    result = audio_parser.parse_audio(
        source,
        "meeting.mp3",
        "audio/mpeg",
        {"ffmpeg_audio_sample_rate": 16000, "max_media_duration_seconds": 3600},
    )

    assert result.parse_status == "parsed"
    assert result.parse_error is None
    assert result.text_content == "这是一段示例转写"
    assert extracted["sample_rate"] == 16000
    assert result.metadata["duration"] == 95.0
    assert result.metadata["language"] == "zh"
    assert result.metadata["provider"] == "mock"
    assert result.metadata["segments"] == 4
    assert result.metadata["transcript_chars"] == len("这是一段示例转写")
    assert result.metadata["mime"] == "audio/mpeg"
    assert result.source_refs == [source]

    temp_dir = os.path.dirname(extracted["dst"])
    assert cleanup_calls == [[temp_dir]]
    assert not os.path.exists(temp_dir)


def test_parse_audio_empty_transcript_is_failed(monkeypatch, media_file):
    """空转写不得返回 parsed 空文本。"""
    source = media_file("empty.wav")
    extracted: dict = {}
    cleanup_calls: list = []

    monkeypatch.setattr(audio_parser.media, "probe_duration", lambda _path: 3.0)
    _patch_extract_audio(monkeypatch, audio_parser, extracted)
    _patch_cleanup(monkeypatch, audio_parser, cleanup_calls)
    monkeypatch.setattr(audio_parser, "ASRClient", _make_asr_class("   "))

    result = audio_parser.parse_audio(source, "empty.wav", "audio/wav", {})

    assert result.parse_status == "failed"
    assert result.parse_error == PARSE_FAILED
    assert result.text_content == ""
    assert cleanup_calls, "空转写路径同样必须清理临时目录"


def test_parse_audio_asr_unavailable(monkeypatch, media_file):
    """ASR 不可用 → failed + KNOWLEDGE_ASR_UNAVAILABLE。"""
    source = media_file("meeting.m4a")
    extracted: dict = {}
    cleanup_calls: list = []

    monkeypatch.setattr(audio_parser.media, "probe_duration", lambda _path: 30.0)
    _patch_extract_audio(monkeypatch, audio_parser, extracted)
    _patch_cleanup(monkeypatch, audio_parser, cleanup_calls)
    monkeypatch.setattr(
        audio_parser,
        "ASRClient",
        _make_asr_class(error=KnowledgeASRUnavailableError("ASR 服务不可用")),
    )

    result = audio_parser.parse_audio(source, "meeting.m4a", "audio/mp4", {})

    assert result.parse_status == "failed"
    assert result.parse_error == ASR_UNAVAILABLE
    assert result.text_content == ""
    assert cleanup_calls, "ASR 降级路径必须清理临时 WAV 目录"


def test_parse_audio_ffmpeg_unavailable(monkeypatch, media_file):
    """ffmpeg 不可用 → failed + KNOWLEDGE_FFMPEG_UNAVAILABLE。"""
    source = media_file("meeting.flac")
    cleanup_calls: list = []

    def fake_extract_audio(_src, _dst, sample_rate=16000):
        raise KnowledgeFFmpegUnavailableError("ffmpeg 未安装")

    monkeypatch.setattr(audio_parser.media, "probe_duration", lambda _path: 30.0)
    monkeypatch.setattr(audio_parser.media, "extract_audio", fake_extract_audio)
    _patch_cleanup(monkeypatch, audio_parser, cleanup_calls)

    result = audio_parser.parse_audio(source, "meeting.flac", "audio/flac", {})

    assert result.parse_status == "failed"
    assert result.parse_error == FFMPEG_UNAVAILABLE
    assert cleanup_calls, "抽音轨失败时临时目录仍必须清理"


def test_parse_audio_duration_exceeded(monkeypatch, media_file):
    """时长超过 max_media_duration_seconds → unsupported + KNOWLEDGE_MEDIA_TOO_LONG。"""
    source = media_file("long.mp3")
    extract_calls: list = []
    cleanup_calls: list = []

    monkeypatch.setattr(audio_parser.media, "probe_duration", lambda _path: 7200.0)

    def fake_extract_audio(_src, dst, sample_rate=16000):
        extract_calls.append(dst)
        return dst

    monkeypatch.setattr(audio_parser.media, "extract_audio", fake_extract_audio)
    _patch_cleanup(monkeypatch, audio_parser, cleanup_calls)

    result = audio_parser.parse_audio(
        source,
        "long.mp3",
        "audio/mpeg",
        {"max_media_duration_seconds": 3600},
    )

    assert result.parse_status == "unsupported"
    assert result.parse_error == MEDIA_TOO_LONG
    assert result.text_content == ""
    assert extract_calls == []
    assert cleanup_calls == []


def _patch_extract_frames(monkeypatch, parser_module, frames: list, recorded: dict) -> None:
    """替换 extract_frames：记录调用参数并返回预设帧路径。"""

    def fake_extract_frames(src, out_dir, interval=10, max_frames=12):
        recorded["src"] = src
        recorded["out_dir"] = out_dir
        recorded["interval"] = interval
        recorded["max_frames"] = max_frames
        return list(frames)

    monkeypatch.setattr(parser_module.media, "extract_frames", fake_extract_frames)


def _patch_parse_image(monkeypatch, parser_module, recorded: dict) -> None:
    """替换 parse_image：返回符合数据契约的 parsed 结果。"""

    def fake_parse_image(path, filename, mime, config=None):
        recorded.setdefault("calls", []).append(
            {"path": path, "filename": filename, "mime": mime}
        )
        return ParseResult(
            text_content=f"{filename} 画面描述",
            parse_status="parsed",
            metadata={"mime": mime},
        )

    monkeypatch.setattr(parser_module, "parse_image", fake_parse_image)


def test_parse_video_merges_transcript_and_frames(monkeypatch, media_file):
    """正向视频：音轨转写 + 带时间戳帧描述合并 → parsed。"""
    source = media_file("clip.mp4")
    cleanup_calls: list = []
    audio_extracted: dict = {}
    frame_extracted: dict = {}
    image_calls: dict = {}

    monkeypatch.setattr(video_parser.media, "probe_duration", lambda _path: 45.0)
    _patch_extract_audio(monkeypatch, video_parser, audio_extracted)

    def fake_extract_frames(src, out_dir, interval=10, max_frames=12):
        frame_extracted.update(
            {"src": src, "out_dir": out_dir, "interval": interval, "max_frames": max_frames}
        )
        return [
            os.path.join(out_dir, "frame_0.jpg"),
            os.path.join(out_dir, "frame_1.jpg"),
        ]

    monkeypatch.setattr(video_parser.media, "extract_frames", fake_extract_frames)
    _patch_cleanup(monkeypatch, video_parser, cleanup_calls)
    _patch_parse_image(monkeypatch, video_parser, image_calls)
    monkeypatch.setattr(
        video_parser,
        "ASRClient",
        _make_asr_class("示例音轨文本", {"language": "zh", "provider": "mock"}),
    )

    result = video_parser.parse_video(
        source,
        "clip.mp4",
        "video/mp4",
        {
            "video_frame_interval_seconds": 10,
            "video_max_frames": 12,
            "ffmpeg_audio_sample_rate": 16000,
            "max_media_duration_seconds": 3600,
        },
    )

    assert result.parse_status == "parsed"
    assert result.parse_error is None
    assert "[视频音轨转写]" in result.text_content
    assert "示例音轨文本" in result.text_content
    assert "[帧 0 @ 0s]" in result.text_content
    assert "[帧 1 @ 10s]" in result.text_content
    assert frame_extracted["interval"] == 10
    assert frame_extracted["max_frames"] == 12
    assert result.metadata["frames_count"] == 2
    assert result.metadata["frame_errors"] == []
    assert result.metadata["transcript_chars"] == len("示例音轨文本")
    assert result.metadata["asr_available"] is True
    assert result.metadata["duration"] == 45.0
    assert result.metadata["mime"] == "video/mp4"

    temp_dir = os.path.dirname(audio_extracted["dst"])
    assert cleanup_calls == [[temp_dir]]
    assert not os.path.exists(temp_dir)


def test_parse_video_asr_unavailable_still_parses_frames(monkeypatch, media_file):
    """ASR 不可用：记录 audio_error，但继续抽帧并返回 parsed。"""
    source = media_file("clip.mp4")
    cleanup_calls: list = []
    audio_extracted: dict = {}
    image_calls: dict = {}

    monkeypatch.setattr(video_parser.media, "probe_duration", lambda _path: 20.0)
    _patch_extract_audio(monkeypatch, video_parser, audio_extracted)
    _patch_extract_frames(
        monkeypatch,
        video_parser,
        ["frame_0.jpg", "frame_1.jpg"],
        {},
    )
    _patch_cleanup(monkeypatch, video_parser, cleanup_calls)
    _patch_parse_image(monkeypatch, video_parser, image_calls)
    monkeypatch.setattr(
        video_parser,
        "ASRClient",
        _make_asr_class(error=KnowledgeASRUnavailableError("ASR 服务不可用")),
    )

    result = video_parser.parse_video(source, "clip.mp4", "video/mp4", {})

    assert result.parse_status == "parsed"
    assert result.metadata["asr_available"] is False
    assert result.metadata["audio_error"] == ASR_UNAVAILABLE
    assert result.metadata["transcript_chars"] == 0
    assert "[视频音轨转写]" not in result.text_content
    assert "[帧 0 @ 0s]" in result.text_content
    assert result.metadata["frames_count"] == 2


def test_parse_video_ffmpeg_unavailable(monkeypatch, media_file):
    """ffmpeg 不可用：整体 failed + KNOWLEDGE_FFMPEG_UNAVAILABLE。"""
    source = media_file("clip.mov")
    cleanup_calls: list = []
    frame_calls: list = []

    def fake_extract_audio(_src, _dst, sample_rate=16000):
        raise KnowledgeFFmpegUnavailableError("ffmpeg 未安装")

    def fake_extract_frames(_src, _out_dir, interval=10, max_frames=12):
        frame_calls.append(max_frames)
        return []

    monkeypatch.setattr(video_parser.media, "probe_duration", lambda _path: 20.0)
    monkeypatch.setattr(video_parser.media, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(video_parser.media, "extract_frames", fake_extract_frames)
    _patch_cleanup(monkeypatch, video_parser, cleanup_calls)

    result = video_parser.parse_video(source, "clip.mov", "video/quicktime", {})

    assert result.parse_status == "failed"
    assert result.parse_error == FFMPEG_UNAVAILABLE
    assert result.text_content == ""
    assert frame_calls == []
    assert cleanup_calls, "ffmpeg 不可用时临时目录必须清理"


def test_parse_video_respects_max_frames(monkeypatch, media_file):
    """帧数受 video_max_frames 限制（抽取参数与返回列表双重截断）。"""
    source = media_file("clip.mkv")
    cleanup_calls: list = []
    frame_extracted: dict = {}
    image_calls: dict = {}
    frames = [os.path.join("out", f"frame_{index}.jpg") for index in range(5)]

    monkeypatch.setattr(video_parser.media, "probe_duration", lambda _path: 60.0)
    _patch_extract_audio(monkeypatch, video_parser, {})
    _patch_extract_frames(monkeypatch, video_parser, frames, frame_extracted)
    _patch_cleanup(monkeypatch, video_parser, cleanup_calls)
    _patch_parse_image(monkeypatch, video_parser, image_calls)
    monkeypatch.setattr(video_parser, "ASRClient", _make_asr_class("音轨"))

    result = video_parser.parse_video(
        source,
        "clip.mkv",
        "video/x-matroska",
        {"video_max_frames": 3, "video_frame_interval_seconds": 5},
    )

    assert result.parse_status == "parsed"
    assert frame_extracted["max_frames"] == 3
    assert frame_extracted["interval"] == 5
    assert result.metadata["frames_count"] == 3
    assert len(image_calls["calls"]) == 3
    assert "[帧 2 @ 10s]" in result.text_content
    assert "[帧 3 @" not in result.text_content


def test_parse_video_empty_content_is_failed(monkeypatch, media_file):
    """音轨转写与帧描述皆空 → failed + KNOWLEDGE_PARSE_FAILED。"""
    source = media_file("silent.mp4")
    cleanup_calls: list = []

    monkeypatch.setattr(video_parser.media, "probe_duration", lambda _path: 8.0)
    _patch_extract_audio(monkeypatch, video_parser, {})
    _patch_extract_frames(monkeypatch, video_parser, [], {})
    _patch_cleanup(monkeypatch, video_parser, cleanup_calls)
    monkeypatch.setattr(
        video_parser,
        "ASRClient",
        _make_asr_class("", {"language": "zh"}),
    )

    result = video_parser.parse_video(source, "silent.mp4", "video/mp4", {})

    assert result.parse_status == "failed"
    assert result.parse_error == PARSE_FAILED
    assert result.text_content == ""
    assert result.metadata["frames_count"] == 0
    assert cleanup_calls, "空内容失败路径必须清理临时目录"


def test_parse_video_duration_exceeded(monkeypatch, media_file):
    """视频时长超限 → unsupported + KNOWLEDGE_MEDIA_TOO_LONG。"""
    source = media_file("long.mp4")
    cleanup_calls: list = []
    extract_calls: list = []

    monkeypatch.setattr(video_parser.media, "probe_duration", lambda _path: 7200.0)

    def fake_extract_audio(_src, dst, sample_rate=16000):
        extract_calls.append(dst)
        return dst

    monkeypatch.setattr(video_parser.media, "extract_audio", fake_extract_audio)
    _patch_cleanup(monkeypatch, video_parser, cleanup_calls)

    result = video_parser.parse_video(
        source,
        "long.mp4",
        "video/mp4",
        {"max_media_duration_seconds": 3600},
    )

    assert result.parse_status == "unsupported"
    assert result.parse_error == MEDIA_TOO_LONG
    assert extract_calls == []
    assert cleanup_calls == []
