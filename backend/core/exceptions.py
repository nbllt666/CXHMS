"""
自定义异常类模块

B3：合并 core/api 双重异常体系。
本模块定义唯一的 CXHMSException 基类（带 error_code / http_status / details），
所有业务异常继承自它。FastAPI 只需注册单一 exception handler 处理 CXHMSException，
即可保留 error_code / http_status 透传，避免 core 层 raise 的异常落入 generic 500。
"""

from typing import Any, Dict, Optional


class CXHMSException(Exception):
    """CXHMS 统一基础异常类

    Attributes:
        message: 人类可读的错误描述
        error_code: 机器可读的错误码（如 DATABASE_ERROR），用于跨层透传
        http_status: 对应的 HTTP 状态码
        details: 额外细节，随响应体返回
    """

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        http_status: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.http_status = http_status
        # 向后兼容：旧 handler / 调用方读取 status_code
        self.status_code = http_status
        self.details = details or {}
        super().__init__(self.message)


class DatabaseError(CXHMSException):
    """数据库操作异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "DATABASE_ERROR", 500, details)


class ValidationError(CXHMSException):
    """数据验证异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VALIDATION_ERROR", 400, details)


class ACPError(CXHMSException):
    """ACP相关异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "ACP_ERROR", 500, details)


class MemoryOperationError(CXHMSException):
    """记忆管理异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "MEMORY_OPERATION_ERROR", 500, details)


class MemoryNotFoundError(CXHMSException):
    """记忆不存在异常"""

    def __init__(self, memory_id):
        super().__init__(
            f"Memory not found: {memory_id}", "MEMORY_NOT_FOUND", 404, {"memory_id": str(memory_id)}
        )


class VectorStoreError(CXHMSException):
    """向量存储异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VECTOR_STORE_ERROR", 503, details)


class LLMError(CXHMSException):
    """LLM调用异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "LLM_ERROR", 503, details)


class ToolError(CXHMSException):
    """工具调用异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "TOOL_ERROR", 500, details)


class MCPError(CXHMSException):
    """MCP协议异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "MCP_ERROR", 500, details)


class ContextError(CXHMSException):
    """上下文管理异常"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "CONTEXT_ERROR", 500, details)
