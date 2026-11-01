"""知识库解析器包（模块11 Task 3）。

仅导出基座符号 `ParseResult` / `ParseError` 与统一入口 `parse`。
图片/音频/视频解析器由 `router.parse` 在函数内懒加载，本包顶层不导入它们，
以保证并行开发期导入安全（Task 4 / Task 6 尚未就绪时本包仍可导入）。
"""

from backend.core.knowledge.parsers.base import ParseError, ParseResult
from backend.core.knowledge.parsers.router import parse

__all__ = ["ParseResult", "ParseError", "parse"]
