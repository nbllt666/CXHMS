from typing import Any, Dict, Optional
import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.exceptions import CXHMSException
from .response import APIResponse, ErrorResponse

logger = logging.getLogger(__name__)


class CXHMSError(CXHMSException):
    """B3：CXHMSError 现继承自统一的 CXHMSException 基类。

    保留原 (message, error_code, status_code, details) 签名以兼容旧调用方，
    内部委托给 CXHMSException。这样 core 层与 api 层异常共享同一基类，
    FastAPI 注册单一 handler 处理 CXHMSException 即可覆盖全部业务异常。
    """

    def __init__(
        self,
        message: str,
        error_code: str = None,
        status_code: int = 500,
        details: Dict[str, Any] = None,
    ):
        super().__init__(
            message,
            error_code or "INTERNAL_ERROR",
            status_code,
            details,
        )


class DatabaseError(CXHMSError):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "DATABASE_ERROR", 500, details)


class MemoryNotFoundError(CXHMSError):
    def __init__(self, memory_id: str):
        super().__init__(f"Memory not found: {memory_id}", "MEMORY_NOT_FOUND", 404)


class AgentNotFoundError(CXHMSError):
    def __init__(self, agent_id: str):
        super().__init__(f"Agent not found: {agent_id}", "AGENT_NOT_FOUND", 404)


class SessionNotFoundError(CXHMSError):
    def __init__(self, session_id: str):
        super().__init__(f"Session not found: {session_id}", "SESSION_NOT_FOUND", 404)


class LLMError(CXHMSError):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "LLM_ERROR", 503, details)


class VectorStoreError(CXHMSError):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "VECTOR_STORE_ERROR", 503, details)


class ValidationError(CXHMSError):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, "VALIDATION_ERROR", 400, details)


class AuthenticationError(CXHMSError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, "AUTHENTICATION_ERROR", 401)


class RateLimitError(CXHMSError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after} seconds",
            "RATE_LIMIT_ERROR",
            429,
            {"retry_after": retry_after},
        )


async def cxhms_exception_handler(request: Request, exc: CXHMSException) -> JSONResponse:
    # B3: 单一 handler 处理所有 CXHMSException 子类（含 core 层 DatabaseError/MemoryOperationError 等）
    return JSONResponse(
        status_code=exc.http_status,
        content=ErrorResponse(
            error=exc.message, error_code=exc.error_code, details=exc.details
        ).model_dump(),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=str(exc.detail), error_code=f"HTTP_{exc.status_code}"
        ).model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="Validation failed", error_code="VALIDATION_ERROR", details={"errors": errors}
        ).model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception processing request to %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            error_code="INTERNAL_ERROR",
        ).model_dump(),
    )
