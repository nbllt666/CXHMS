"""模块11 媒体工具与 ASR 客户端单元测试。

覆盖 spec Task 5 / checklist「三、多模态解析」的降级路径：
1. ffmpeg 缺失 → ``ffmpeg_available=False``，``extract_audio`` 抛
   ``KnowledgeFFmpegUnavailableError``；
2. ``cleanup_paths`` 幂等（文件、目录、缺失路径重复删除均不抛异常）；
3. ``ASRClient(provider=faster_whisper)`` 且 import 失败 → ``is_available=False``，
   ``transcribe`` 抛 ``KnowledgeASRUnavailableError``；
4. ``openai_compatible`` 且 base_url 为空 → ``is_available=False``；
5. 本机存在 ffmpeg 时额外正向验证（1 秒静音 WAV → ``probe_duration`` 非空 +
   ``extract_audio`` 产出 WAV）；缺失时以显式原因 skip。

不依赖 faster-whisper 真实模型，也不访问真实网络。
运行方式：
    python -m pytest tests/units/test_knowledge_media.py -q
"""

import os
import sys
import wave

import pytest

import backend.core.knowledge.asr as asr_module
import backend.core.knowledge.media as media
from backend.core.knowledge.asr import ASRClient
from backend.core.knowledge.exceptions import (
    KnowledgeASRUnavailableError,
    KnowledgeFFmpegUnavailableError,
)

BASE_CONFIG = {
    "asr_provider": "faster_whisper",
    "asr_model": "small",
    "asr_device": "auto",
    "asr_compute_type": "int8",
    "asr_language": "zh",
    "asr_download_root": "data/models/faster_whisper",
    "asr_base_url": "",
    "asr_api_key": "",
    "asr_timeout_seconds": 30,
    "ffmpeg_path": "",
    "ffmpeg_fallback_to_imageio": True,
    "ffmpeg_audio_sample_rate": 16000,
    "video_frame_interval_seconds": 10,
    "video_max_frames": 12,
}


def make_config(**overrides):
    """构造一份 fake 知识库配置（覆盖指定键）。"""
    config = dict(BASE_CONFIG)
    config.update(overrides)
    return config


def _write_silent_wav(path, seconds=1.0, rate=16000, channels=1):
    """写入一个静音 WAV（16-bit PCM），返回绝对路径。"""
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames * channels)
    return str(path)


def _raise_imageio_import_error():
    """模拟 imageio_ffmpeg 未安装。"""
    raise ImportError("imageio_ffmpeg is not installed")


def _simulate_missing_ffmpeg(monkeypatch):
    """让 ffmpeg 发现链路全部失效（which 无结果 + imageio 导入失败）。"""
    monkeypatch.setattr(media.shutil, "which", lambda name: None)
    monkeypatch.setattr(media, "_import_imageio_ffmpeg", _raise_imageio_import_error)
    media.reset_ffmpeg_cache()


@pytest.fixture(autouse=True)
def _reset_caches():
    """每个用例前后清空 ffmpeg 发现缓存与 faster-whisper 模型缓存。"""
    media.reset_ffmpeg_cache()
    asr_module._MODEL_CACHE.clear()
    yield
    media.reset_ffmpeg_cache()
    asr_module._MODEL_CACHE.clear()


# --------------------------------------------------------------------------- #
# ffmpeg 发现与抽取
# --------------------------------------------------------------------------- #


def test_ffmpeg_available_false_when_missing(monkeypatch, tmp_path):
    """ffmpeg 缺失时 ffmpeg_available 返回 False，且 extract_audio 抛不可用异常。"""
    _simulate_missing_ffmpeg(monkeypatch)
    config = make_config(ffmpeg_path="", ffmpeg_fallback_to_imageio=True)

    assert media.ffmpeg_available(config) is False

    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    destination = tmp_path / "normalized.wav"

    with pytest.raises(KnowledgeFFmpegUnavailableError):
        media.extract_audio(str(source), str(destination), sample_rate=16000)
    assert not destination.exists()


def test_ffmpeg_available_false_for_nonexistent_explicit_path(monkeypatch, tmp_path):
    """显式 ffmpeg_path 不存在且禁用 imageio 回退时返回 False。"""
    monkeypatch.setattr(media.shutil, "which", lambda name: None)
    monkeypatch.setattr(media, "_import_imageio_ffmpeg", _raise_imageio_import_error)
    media.reset_ffmpeg_cache()

    config = make_config(
        ffmpeg_path=str(tmp_path / "not_exists" / "ffmpeg.exe"),
        ffmpeg_fallback_to_imageio=False,
    )
    assert media.ffmpeg_available(config) is False


def test_ffmpeg_available_caches_result(monkeypatch):
    """同一配置键重复探测命中缓存，不会因后续 which 结果变化而改变。"""
    _simulate_missing_ffmpeg(monkeypatch)
    config = make_config(ffmpeg_path="", ffmpeg_fallback_to_imageio=True)

    assert media.ffmpeg_available(config) is False
    monkeypatch.setattr(media.shutil, "which", lambda name: r"C:\fake\ffmpeg.exe")
    assert media.ffmpeg_available(config) is False


def test_extract_frames_missing_ffmpeg_raises(monkeypatch, tmp_path):
    """ffmpeg 缺失时 extract_frames 抛 KnowledgeFFmpegUnavailableError。"""
    _simulate_missing_ffmpeg(monkeypatch)

    source = tmp_path / "video.mp4"
    source.write_bytes(b"\x00\x00\x00\x00")
    out_dir = tmp_path / "frames"

    with pytest.raises(KnowledgeFFmpegUnavailableError):
        media.extract_frames(str(source), str(out_dir), interval=10, max_frames=3)
    assert not out_dir.exists()


def test_cleanup_paths_idempotent(tmp_path):
    """cleanup_paths 删除文件与目录，重复调用幂等且不抛异常。"""
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    (frame_dir / "frame_001.jpg").write_bytes(b"jpg")
    audio_file = tmp_path / "temp.wav"
    audio_file.write_bytes(b"wav")
    missing = tmp_path / "missing.wav"

    media.cleanup_paths([str(audio_file), str(frame_dir), str(missing)])

    assert not audio_file.exists()
    assert not frame_dir.exists()

    # 重复调用不应抛出异常。
    media.cleanup_paths([str(audio_file), str(frame_dir), str(missing)])
    media.cleanup_paths([])

    assert not audio_file.exists()
    assert not frame_dir.exists()


# --------------------------------------------------------------------------- #
# ASRClient
# --------------------------------------------------------------------------- #


def test_asr_faster_whisper_import_failure(monkeypatch, tmp_path):
    """faster_whisper 导入失败时 is_available=False，transcribe 抛不可用异常。"""
    monkeypatch.setitem(sys.modules, "faster_whisper", None)

    client = ASRClient(make_config(asr_provider="faster_whisper"))
    assert client.is_available() is False

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    with pytest.raises(KnowledgeASRUnavailableError):
        client.transcribe(str(audio))


def test_asr_openai_compatible_empty_base_url(tmp_path):
    """openai_compatible 且 base_url 为空时 is_available=False，transcribe 抛异常。"""
    client = ASRClient(
        make_config(asr_provider="openai_compatible", asr_base_url="")
    )
    assert client.is_available() is False

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    with pytest.raises(KnowledgeASRUnavailableError):
        client.transcribe(str(audio))


def test_asr_openai_compatible_timeout_raises(monkeypatch, tmp_path):
    """openai_compatible 请求超时转为 KnowledgeASRUnavailableError（不静默返回空文本）。"""
    import httpx

    client = ASRClient(
        make_config(
            asr_provider="openai_compatible",
            asr_base_url="http://127.0.0.1:1",
            asr_api_key="secret-key",
        )
    )
    assert client.is_available() is True

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    def _raise_timeout(*args, **kwargs):
        raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr(httpx, "post", _raise_timeout)

    with pytest.raises(KnowledgeASRUnavailableError) as exc_info:
        client.transcribe(str(audio))
    # 异常文本不得泄漏 api_key。
    assert "secret-key" not in str(exc_info.value)


def test_asr_openai_compatible_success(monkeypatch, tmp_path):
    """openai_compatible 成功路径返回 text 与 provider/model 元数据。"""
    import httpx

    client = ASRClient(
        make_config(
            asr_provider="openai_compatible",
            asr_base_url="http://127.0.0.1:1",
        )
    )

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"text": "你好世界", "language": "zh"}

    def _fake_post(*args, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)

    text, metadata = client.transcribe(str(audio))
    assert text == "你好世界"
    assert metadata["provider"] == "openai_compatible"
    assert metadata["model"] == "small"


# --------------------------------------------------------------------------- #
# ffmpeg 正向证据
# --------------------------------------------------------------------------- #


def test_probe_duration_and_extract_audio_positive_or_skip(tmp_path):
    """本机有 ffmpeg 时验证 1 秒静音 WAV 的时长探测与音轨抽取；否则显式 skip。"""
    config = make_config(ffmpeg_path="", ffmpeg_fallback_to_imageio=True)
    if not media.ffmpeg_available(config):
        pytest.skip(
            "ffmpeg not available: shutil.which('ffmpeg') returned None and "
            "imageio_ffmpeg is not installed"
        )

    source = _write_silent_wav(tmp_path / "silence.wav", seconds=1.0, rate=16000)

    duration = media.probe_duration(source)
    assert duration is not None
    assert 0.5 <= duration <= 2.0

    destination = tmp_path / "normalized.wav"
    output = media.extract_audio(source, str(destination), sample_rate=16000)
    assert os.path.isfile(output)
