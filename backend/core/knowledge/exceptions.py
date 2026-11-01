"""独立知识库异常契约实现（模块11）。

全部异常继承 `backend.core.exceptions.CXHMSException`，携带统一 error_code 与
http_status，挂接到全局错误码体系（rules-3 §一 error_codes / rules-4 项目错误码规范）。

错误码与 `public/schema/knowledge.json::definitions.error_codes` 一一对应：
    KNOWLEDGE_ERROR                → KnowledgeError                  → 500
    KNOWLEDGE_VALIDATION_ERROR     → KnowledgeValidationError        → 400
    KNOWLEDGE_PARSE_FAILED         → KnowledgeParseError             → 500
    KNOWLEDGE_UNSUPPORTED_MIME     → KnowledgeUnsupportedMediaError  → 415
    KNOWLEDGE_STORE_UNAVAILABLE    → KnowledgeStoreError             → 503
    KNOWLEDGE_ASR_UNAVAILABLE      → KnowledgeASRUnavailableError    → 503
    KNOWLEDGE_FFMPEG_UNAVAILABLE   → KnowledgeFFmpegUnavailableError → 503

`KNOWLEDGE_MEDIA_TOO_LONG` 不抛异常，仅写入文档 `parse_error`（上传阶段返回 413）。
"""

from backend.core.exceptions import CXHMSException


class KnowledgeError(CXHMSException):
    """知识库通用异常（HTTP 500）。"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, "KNOWLEDGE_ERROR", 500, details)


class KnowledgeValidationError(KnowledgeError):
    """知识库数据/参数不符合数据契约（HTTP 400）。"""

    def __init__(self, message: str, details: dict | None = None):
        CXHMSException.__init__(self, message, "KNOWLEDGE_VALIDATION_ERROR", 400, details)


class KnowledgeParseError(KnowledgeError):
    """文档或媒体解析失败（HTTP 500）。"""

    def __init__(self, message: str, details: dict | None = None):
        CXHMSException.__init__(self, message, "KNOWLEDGE_PARSE_FAILED", 500, details)


class KnowledgeUnsupportedMediaError(KnowledgeError):
    """MIME 不在允许白名单（HTTP 415）。"""

    def __init__(self, message: str, details: dict | None = None):
        CXHMSException.__init__(self, message, "KNOWLEDGE_UNSUPPORTED_MIME", 415, details)


class KnowledgeStoreError(KnowledgeError):
    """知识库存储不可用或未启用（HTTP 503）。"""

    def __init__(self, message: str, details: dict | None = None):
        CXHMSException.__init__(self, message, "KNOWLEDGE_STORE_UNAVAILABLE", 503, details)


class KnowledgeASRUnavailableError(KnowledgeError):
    """ASR 依赖不可用或转写超时（HTTP 503）。"""

    def __init__(self, message: str, details: dict | None = None):
        CXHMSException.__init__(self, message, "KNOWLEDGE_ASR_UNAVAILABLE", 503, details)


class KnowledgeFFmpegUnavailableError(KnowledgeError):
    """ffmpeg 不可用导致音视频抽取失败（HTTP 503）。"""

    def __init__(self, message: str, details: dict | None = None):
        CXHMSException.__init__(self, message, "KNOWLEDGE_FFMPEG_UNAVAILABLE", 503, details)
