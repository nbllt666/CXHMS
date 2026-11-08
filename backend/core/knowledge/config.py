"""模块11 独立知识库配置加载（rules-3 §三 配置契约）。

加载优先级（高 → 低）：
1. 调用方 `overrides`（测试/运行时注入）
2. `config/default.yaml::knowledge`（运行时唯一真相源）
3. `public/config_template/knowledge_config.json` 各字段 `default`
4. 本模块 `CODE_DEFAULTS` 兜底

加载后执行 auto_fill：缺失字段补齐、类型收敛、关联约束修正
（`chunk_overlap < chunk_size`、`*_top_k_max >= *_top_k_default`、
`parse_max_workers ∈ [1, 8]`）。禁止引入第二份 knowledge 配置文件。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Mapping

try:
    import yaml
except ImportError:  # pragma: no cover - requirements 保证 PyYAML 存在
    yaml = None

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 绝对路径锚点（禁止相对路径 / ".."）
# --------------------------------------------------------------------------- #
_KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.dirname(_KNOWLEDGE_DIR)
_BACKEND_DIR = os.path.dirname(_CORE_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_DEFAULT_YAML_PATH = os.path.join(_PROJECT_ROOT, "config", "default.yaml")
_CONFIG_TEMPLATE_PATH = os.path.join(
    _PROJECT_ROOT, "public", "config_template", "knowledge_config.json"
)

# 代码兜底默认值：必须与 public/config_template/knowledge_config.json 的 39 键一致。
CODE_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "db_dir": "data",
    "db_filename_prefix": "knowledge",
    "files_dir": "data/knowledge_files",
    "collection_prefix": "CXHMSKnowledge",
    "max_document_size_mb": 20,
    "max_media_size_mb": 200,
    "allowed_document_mimes": [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
        "text/markdown",
    ],
    "allowed_image_mimes": ["image/png", "image/jpeg", "image/webp", "image/bmp"],
    "allowed_audio_mimes": [
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/mp4",
        "audio/flac",
        "audio/ogg",
        "audio/aac",
        "audio/opus",
    ],
    "allowed_video_mimes": [
        "video/mp4",
        "video/quicktime",
        "video/x-matroska",
        "video/webm",
        "video/x-msvideo",
        "video/x-flv",
    ],
    "chunk_size": 800,
    "chunk_overlap": 120,
    "max_chunks_per_document": 2000,
    "parse_max_workers": 2,
    "asr_provider": "faster_whisper",
    "asr_model": "small",
    "asr_device": "auto",
    "asr_compute_type": "int8",
    "asr_language": "zh",
    "asr_download_root": "data/models/faster_whisper",
    "asr_base_url": "",
    "asr_api_key": "",
    "asr_timeout_seconds": 600,
    "ffmpeg_path": "",
    "ffmpeg_fallback_to_imageio": True,
    "ffmpeg_audio_sample_rate": 16000,
    "video_frame_interval_seconds": 10,
    "video_max_frames": 12,
    "max_media_duration_seconds": 3600,
    "vector_enabled": True,
    "vector_top_k_default": 8,
    "vector_top_k_max": 50,
    "vector_rrf_k": 60,
    "fts_enabled": True,
    "fts_fallback_like": True,
    "search_top_k_default": 8,
    "search_top_k_max": 50,
    "preview_chars": 500,
}

_MINIMUMS: Dict[str, int] = {
    "max_document_size_mb": 1,
    "max_media_size_mb": 1,
    "chunk_size": 100,
    "chunk_overlap": 0,
    "max_chunks_per_document": 1,
    "parse_max_workers": 1,
    "asr_timeout_seconds": 30,
    "ffmpeg_audio_sample_rate": 8000,
    "video_frame_interval_seconds": 1,
    "video_max_frames": 1,
    "max_media_duration_seconds": 1,
    "vector_top_k_default": 1,
    "vector_top_k_max": 1,
    "vector_rrf_k": 1,
    "search_top_k_default": 1,
    "search_top_k_max": 1,
    "preview_chars": 1,
}


def resolve_project_path(path: str) -> str:
    """把配置中的相对路径解析为锚定项目根的绝对路径。"""
    text = str(path or "").strip()
    if not text:
        return _PROJECT_ROOT
    if os.path.isabs(text):
        return os.path.normpath(text)
    return os.path.normpath(os.path.join(_PROJECT_ROOT, text))


def _load_template_defaults() -> Dict[str, Any]:
    """读取配置契约中各字段的 `default`（失败返回空字典）。"""
    try:
        with open(_CONFIG_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
            template = json.load(handle)
    except (OSError, ValueError) as exc:  # pragma: no cover - 契约文件由仓库保证
        logger.warning("读取知识库配置契约失败，使用代码兜底: %s", exc)
        return {}
    properties = template.get("properties")
    if not isinstance(properties, dict):
        return {}
    defaults: Dict[str, Any] = {}
    for key, spec in properties.items():
        if isinstance(spec, dict) and "default" in spec:
            defaults[key] = spec["default"]
    return defaults


def _load_yaml_section() -> Dict[str, Any]:
    """读取 `config/default.yaml::knowledge`（优先复用已加载的 settings）。"""
    try:  # 避免在模块导入期拉起 settings，延迟到调用时再尝试
        from config.settings import settings as _settings

        raw = getattr(_settings, "raw_config", None)
        if isinstance(raw, Mapping):
            section = raw.get("knowledge")
            if isinstance(section, Mapping):
                return dict(section)
    except Exception:  # noqa: BLE001 - settings 不可用时回退直接读文件
        pass

    if yaml is None:  # pragma: no cover - PyYAML 由 requirements 保证
        return {}
    try:
        with open(_DEFAULT_YAML_PATH, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except (OSError, ValueError) as exc:  # pragma: no cover
        logger.warning("读取 config/default.yaml 失败: %s", exc)
        return {}
    section = raw.get("knowledge") if isinstance(raw, Mapping) else None
    return dict(section) if isinstance(section, Mapping) else {}


def _coerce(key: str, value: Any) -> Any:
    """按代码兜底类型收敛配置值（非法值回退兜底）。"""
    fallback = CODE_DEFAULTS[key]
    if isinstance(fallback, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        return fallback
    if isinstance(fallback, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
    if isinstance(fallback, list):
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value]
        return list(fallback)
    return str(value) if value is not None else fallback


def _normalize(config: Dict[str, Any]) -> Dict[str, Any]:
    """auto_fill 后执行类型收敛与关联约束修正。"""
    normalized: Dict[str, Any] = {}
    for key, fallback in CODE_DEFAULTS.items():
        normalized[key] = _coerce(key, config.get(key, fallback))

    for key, minimum in _MINIMUMS.items():
        normalized[key] = max(minimum, int(normalized[key]))

    normalized["parse_max_workers"] = min(8, int(normalized["parse_max_workers"]))
    if normalized["chunk_overlap"] >= normalized["chunk_size"]:
        normalized["chunk_overlap"] = max(0, int(normalized["chunk_size"]) - 1)
    normalized["vector_top_k_max"] = max(
        normalized["vector_top_k_default"], normalized["vector_top_k_max"]
    )
    normalized["search_top_k_max"] = max(
        normalized["search_top_k_default"], normalized["search_top_k_max"]
    )
    return normalized


def load_knowledge_config(
    overrides: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """加载知识库配置（39 键，auto_fill 完成）。

    Args:
        overrides: 最高优先级覆盖值（测试 / 运行时注入）

    Returns:
        规范化后的配置字典
    """
    merged: Dict[str, Any] = dict(CODE_DEFAULTS)
    merged.update(_load_template_defaults())
    merged.update(_load_yaml_section())
    if overrides:
        merged.update(dict(overrides))
    return _normalize(merged)
