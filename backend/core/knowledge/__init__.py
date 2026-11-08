"""模块11 独立知识库公开入口。

对外导出管理器、注册表、存储、配置加载、分块、解析基座、向量索引与异常契约。
"""

from backend.core.knowledge.chunker import chunk_text
from backend.core.knowledge.config import (
    CODE_DEFAULTS,
    load_knowledge_config,
    resolve_project_path,
)
from backend.core.knowledge.exceptions import (
    KnowledgeASRUnavailableError,
    KnowledgeError,
    KnowledgeFFmpegUnavailableError,
    KnowledgeParseError,
    KnowledgeStoreError,
    KnowledgeUnsupportedMediaError,
    KnowledgeValidationError,
)
from backend.core.knowledge.manager import (
    DEFAULT_AGENT_ID,
    KnowledgeManager,
    KnowledgeRegistry,
    is_default_agent,
    safe_agent_id,
)
from backend.core.knowledge.parsers.base import ParseError, ParseResult
from backend.core.knowledge.parsers.router import parse
from backend.core.knowledge.store import KnowledgeStore
from backend.core.knowledge.vector_index import KnowledgeVectorIndex

__all__ = [
    "CODE_DEFAULTS",
    "DEFAULT_AGENT_ID",
    "KnowledgeASRUnavailableError",
    "KnowledgeError",
    "KnowledgeFFmpegUnavailableError",
    "KnowledgeManager",
    "KnowledgeParseError",
    "KnowledgeRegistry",
    "KnowledgeStore",
    "KnowledgeStoreError",
    "KnowledgeUnsupportedMediaError",
    "KnowledgeValidationError",
    "KnowledgeVectorIndex",
    "ParseError",
    "ParseResult",
    "chunk_text",
    "is_default_agent",
    "load_knowledge_config",
    "parse",
    "resolve_project_path",
    "safe_agent_id",
]
