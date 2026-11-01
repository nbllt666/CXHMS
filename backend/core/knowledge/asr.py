"""知识库 ASR 客户端（模块11）。

冻结签名见 spec「冻结的 ASR / 媒体签名」::

    class ASRClient:
        def __init__(self, config: dict) -> None: ...
        def is_available(self) -> bool: ...
        def transcribe(self, audio_path: str) -> tuple[str, dict]: ...

支持两种 provider：
1. ``faster_whisper``：进程内模型缓存 + 全局锁，``WhisperModel`` 懒加载，
   模型缓存目录遵守 ``asr_download_root``；合并 segments 文本。
2. ``openai_compatible``：调用 ``{base_url}/audio/transcriptions``（httpx multipart）。

任何不可用/超时/异常一律抛 ``KnowledgeASRUnavailableError``，禁止静默返回空文本。
``asr_api_key`` 仅用于请求头，绝不写入日志或异常文本。
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from backend.core.knowledge.exceptions import KnowledgeASRUnavailableError

# 进程内 faster-whisper 模型缓存：键为 (model, device, compute_type, download_root)。
_MODEL_CACHE: Dict[Tuple[str, str, str, Optional[str]], Any] = {}
_MODEL_CACHE_LOCK = threading.Lock()

_PROVIDER_FASTER_WHISPER = "faster_whisper"
_PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"


class ASRClient:
    """语音转写客户端（本地 faster-whisper 或 OpenAI 兼容端点）。"""

    def __init__(self, config: dict) -> None:
        """从知识库配置构造客户端。

        Args:
            config: 知识库配置 dict（键见 spec「冻结的配置字段表」）。
        """
        cfg = config if isinstance(config, dict) else {}

        provider = str(cfg.get("asr_provider") or _PROVIDER_FASTER_WHISPER).strip()
        self.provider: str = provider or _PROVIDER_FASTER_WHISPER

        self.model_name: str = str(cfg.get("asr_model") or "small")
        self.device: str = str(cfg.get("asr_device") or "auto")
        self.compute_type: str = str(cfg.get("asr_compute_type") or "int8")
        self.language: Optional[str] = str(cfg.get("asr_language") or "zh") or None

        download_root = cfg.get("asr_download_root")
        self.download_root: Optional[str] = (
            os.path.abspath(str(download_root)) if download_root else None
        )

        base_url = str(cfg.get("asr_base_url") or "").strip()
        self.base_url: str = base_url.rstrip("/")
        # api_key 仅保存在实例内用于请求头，不进入日志/异常文本。
        self.api_key: str = str(cfg.get("asr_api_key") or "")

        try:
            self.timeout_seconds: float = float(cfg.get("asr_timeout_seconds") or 600)
        except (TypeError, ValueError):
            self.timeout_seconds = 600.0

    # ------------------------------------------------------------------ #
    # 可用性
    # ------------------------------------------------------------------ #
    def is_available(self) -> bool:
        """判断当前 provider 是否可用；任何异常返回 False。"""
        try:
            if self.provider == _PROVIDER_FASTER_WHISPER:
                from faster_whisper import WhisperModel  # noqa: F401

                return True
            if self.provider == _PROVIDER_OPENAI_COMPATIBLE:
                return bool(self.base_url)
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # 转写入口
    # ------------------------------------------------------------------ #
    def transcribe(self, audio_path: str) -> Tuple[str, dict]:
        """转写音频文件。

        Args:
            audio_path: 音频文件路径（WAV 或 ffmpeg 可解析格式）。

        Returns:
            ``(text, metadata)``；``metadata`` 至少包含 provider/model，
            faster-whisper 路径另含 language/duration/segments。

        Raises:
            KnowledgeASRUnavailableError: 文件缺失、provider 不可用、
                依赖缺失、请求失败/超时、转写异常或转写结果为空。
        """
        path = os.path.abspath(audio_path)
        if not os.path.isfile(path):
            raise KnowledgeASRUnavailableError(
                f"audio file not found: {path}", {"audio_path": path}
            )

        if not self.is_available():
            raise KnowledgeASRUnavailableError(
                f"ASR provider '{self.provider}' is not available",
                {"provider": self.provider, "model": self.model_name},
            )

        if self.provider == _PROVIDER_FASTER_WHISPER:
            return self._transcribe_faster_whisper(path)
        if self.provider == _PROVIDER_OPENAI_COMPATIBLE:
            return self._transcribe_openai_compatible(path)

        raise KnowledgeASRUnavailableError(
            f"unsupported ASR provider: {self.provider}",
            {"provider": self.provider},
        )

    # ------------------------------------------------------------------ #
    # faster-whisper
    # ------------------------------------------------------------------ #
    def _get_model(self) -> Any:
        """获取（并缓存）faster-whisper 模型实例，双重检查锁定。"""
        cache_key = (self.model_name, self.device, self.compute_type, self.download_root)

        with _MODEL_CACHE_LOCK:
            model = _MODEL_CACHE.get(cache_key)
            if model is None:
                from faster_whisper import WhisperModel

                model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=self.download_root,
                )
                _MODEL_CACHE[cache_key] = model
            return model

    def _transcribe_faster_whisper(self, path: str) -> Tuple[str, dict]:
        """使用本地 faster-whisper 模型转写。"""
        details = {"provider": self.provider, "model": self.model_name}

        try:
            model = self._get_model()
            segments, info = model.transcribe(path, language=self.language)
            segment_list = list(segments)
        except KnowledgeASRUnavailableError:
            raise
        except Exception as exc:
            raise KnowledgeASRUnavailableError(
                f"faster-whisper transcription failed: {exc}", details
            ) from exc

        text = "".join(
            str(getattr(segment, "text", "") or "") for segment in segment_list
        ).strip()
        if not text:
            raise KnowledgeASRUnavailableError(
                "faster-whisper returned empty transcript", details
            )

        duration = getattr(info, "duration", None)
        detected_language = getattr(info, "language", None) or self.language

        segment_meta: List[dict] = []
        for segment in segment_list:
            segment_meta.append(
                {
                    "start": getattr(segment, "start", None),
                    "end": getattr(segment, "end", None),
                    "text": str(getattr(segment, "text", "") or "").strip(),
                }
            )

        metadata = {
            "provider": self.provider,
            "model": self.model_name,
            "language": detected_language,
            "duration": duration,
            "segments": segment_meta,
        }
        return text, metadata

    # ------------------------------------------------------------------ #
    # OpenAI 兼容端点
    # ------------------------------------------------------------------ #
    def _transcribe_openai_compatible(self, path: str) -> Tuple[str, dict]:
        """调用 OpenAI 兼容 ``/audio/transcriptions`` 端点转写。"""
        details = {"provider": self.provider, "model": self.model_name}

        if not self.base_url:
            raise KnowledgeASRUnavailableError(
                "openai_compatible ASR base_url is empty", details
            )

        try:
            import httpx
        except Exception as exc:
            raise KnowledgeASRUnavailableError(
                "httpx is required for openai_compatible ASR", details
            ) from exc

        url = f"{self.base_url}/audio/transcriptions"
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data: Dict[str, str] = {"model": self.model_name}
        if self.language:
            data["language"] = self.language

        try:
            with open(path, "rb") as handle:
                files = {
                    "file": (
                        os.path.basename(path),
                        handle,
                        "application/octet-stream",
                    )
                }
                response = httpx.post(
                    url,
                    files=files,
                    data=data,
                    headers=headers or None,
                    timeout=self.timeout_seconds,
                )
        except Exception as exc:
            # 不把请求头/此刻的 api_key 放进异常文本，仅保留异常类型与消息。
            raise KnowledgeASRUnavailableError(
                f"openai_compatible ASR request failed: {type(exc).__name__}: {exc}",
                details,
            ) from exc

        status_code = getattr(response, "status_code", None)
        if status_code is None or int(status_code) >= 400:
            raise KnowledgeASRUnavailableError(
                "openai_compatible ASR returned an error status",
                {**details, "status_code": status_code},
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise KnowledgeASRUnavailableError(
                "openai_compatible ASR returned non-JSON response", details
            ) from exc

        if not isinstance(payload, dict):
            raise KnowledgeASRUnavailableError(
                "openai_compatible ASR returned unexpected payload", details
            )

        text = str(payload.get("text") or "").strip()
        if not text:
            raise KnowledgeASRUnavailableError(
                "openai_compatible ASR returned empty transcript", details
            )

        metadata = {
            "provider": self.provider,
            "model": self.model_name,
            "language": payload.get("language") or self.language,
        }
        if "duration" in payload:
            metadata["duration"] = payload.get("duration")
        return text, metadata
