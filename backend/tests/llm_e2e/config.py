"""Test configuration for the LLM-based end-to-end testing framework."""

import os
from dataclasses import dataclass, field


_ENV_PREFIX = "CXHMS_TEST_"


@dataclass
class TestConfig:
    """Configuration for LLM E2E tests.

    All settings are configurable via environment variables with the
    ``CXHMS_TEST_`` prefix (e.g. ``CXHMS_TEST_CXHMS_BASE_URL``).
    """

    # --- Service endpoints ---
    cxhms_base_url: str = "http://127.0.0.1:8001"
    judge_vllm_base_url: str = "http://127.0.0.1:8000/v1"

    # --- Judge model settings ---
    judge_model: str = "gemma4-e4b"
    judge_api_key: str = ""
    judge_supports_tools: bool = True
    judge_temperature: float = 0.1
    judge_max_tokens: int = 2048
    judge_max_retries: int = 3

    # --- Timeout / concurrency ---
    chat_timeout: int = 120
    concurrent_users: int = 5
    long_conversation_rounds: int = 50

    # --- Performance thresholds ---
    performance_threshold_ms: int = 120
    ttft_threshold_ms: int = 5000
    tps_min_threshold: float = 5.0
    judge_score_pass: int = 3

    # --- Output ---
    report_output_dir: str = "test_reports"

    # --- Internal: field name -> env key mapping (populated in __post_init__) ---
    _env_mapping: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._env_mapping = {
            "cxhms_base_url": f"{_ENV_PREFIX}CXHMS_BASE_URL",
            "judge_vllm_base_url": f"{_ENV_PREFIX}JUDGE_VLLM_BASE_URL",
            "judge_model": f"{_ENV_PREFIX}JUDGE_MODEL",
            "judge_api_key": f"{_ENV_PREFIX}JUDGE_API_KEY",
            "judge_supports_tools": f"{_ENV_PREFIX}JUDGE_SUPPORTS_TOOLS",
            "judge_temperature": f"{_ENV_PREFIX}JUDGE_TEMPERATURE",
            "judge_max_tokens": f"{_ENV_PREFIX}JUDGE_MAX_TOKENS",
            "judge_max_retries": f"{_ENV_PREFIX}JUDGE_MAX_RETRIES",
            "chat_timeout": f"{_ENV_PREFIX}CHAT_TIMEOUT",
            "concurrent_users": f"{_ENV_PREFIX}CONCURRENT_USERS",
            "long_conversation_rounds": f"{_ENV_PREFIX}LONG_CONVERSATION_ROUNDS",
            "performance_threshold_ms": f"{_ENV_PREFIX}PERFORMANCE_THRESHOLD_MS",
            "ttft_threshold_ms": f"{_ENV_PREFIX}TTFT_THRESHOLD_MS",
            "tps_min_threshold": f"{_ENV_PREFIX}TPS_MIN_THRESHOLD",
            "judge_score_pass": f"{_ENV_PREFIX}JUDGE_SCORE_PASS",
            "report_output_dir": f"{_ENV_PREFIX}REPORT_OUTPUT_DIR",
        }

    @classmethod
    def from_env(cls) -> "TestConfig":
        """Create a TestConfig instance, reading overrides from environment variables.

        Environment variable names follow the pattern ``CXHMS_TEST_<UPPER_SNAKE_FIELD>``.
        Values are automatically coerced to the correct type based on the field's
        default type (str, int, or float).
        """
        instance = cls()
        type_hints: dict[str, type] = {
            "cxhms_base_url": str,
            "judge_vllm_base_url": str,
            "judge_model": str,
            "judge_api_key": str,
            "judge_supports_tools": bool,
            "judge_temperature": float,
            "judge_max_tokens": int,
            "judge_max_retries": int,
            "chat_timeout": int,
            "concurrent_users": int,
            "long_conversation_rounds": int,
            "performance_threshold_ms": int,
            "ttft_threshold_ms": int,
            "tps_min_threshold": float,
            "judge_score_pass": int,
            "report_output_dir": str,
        }

        for field_name, env_key in instance._env_mapping.items():
            raw = os.environ.get(env_key)
            if raw is not None:
                target_type = type_hints.get(field_name, str)
                try:
                    if target_type is bool:
                        coerced = raw.lower() in ("true", "1", "yes")
                    else:
                        coerced = target_type(raw)
                except (ValueError, TypeError):
                    # Skip invalid env values — keep the default
                    continue
                setattr(instance, field_name, coerced)

        return instance
