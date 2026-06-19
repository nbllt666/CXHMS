"""
性能监控中间件
记录 API 响应时间和性能指标
"""
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        process_time = (time.perf_counter() - start_time) * 1000
        
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
        
        path = request.url.path
        method = request.method
        
        if process_time > 100:
            logger.warning(
                f"慢请求: {method} {path} - {process_time:.2f}ms"
            )
        elif process_time > 50:
            logger.info(
                f"中等请求: {method} {path} - {process_time:.2f}ms"
            )
        else:
            logger.debug(
                f"快速请求: {method} {path} - {process_time:.2f}ms"
            )
        
        return response

