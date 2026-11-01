"""KnowledgeManager 接口契约存根。

模块11 独立知识库（per-agent 隔离）接口契约（@version 1.0.0）。
定义知识库管理器 10 个公开方法 + __init__（共 11 个类签名）、模块级统一解析入口
parse(...) 与 7 个异常声明。实现必须严格匹配此存根定义的签名，否则契约测试不通过
（rules-3 §二 signature_match）。

设计边界（冻结，不得扩张）：
- 顶层只允许：typing 导入、KnowledgeManager 类、模块级 parse 函数、7 个异常类。
- 不得声明 KnowledgeParser / ASRClient / ParseResult 类。
- parse 返回值为前向引用的 "ParseResult"（真实定义位于
  backend/core/knowledge/parsers/base.py，属实现层，不在契约层重复声明）。
- 7 个异常类只写类头 + `...`，不定义任何方法；真实实现位于
  backend/core/knowledge/exceptions.py。

@see public/schema/knowledge.json
@see public/config_template/knowledge_config.json
"""

from typing import Any, Mapping, Sequence


class KnowledgeManager:
    """独立知识库管理器接口契约。

    每个 agent 一个 KnowledgeManager 实例，按 agent 隔离 SQLite、文件目录与
    向量 collection；default 回退到主库（data/knowledge.db / CXHMSKnowledge）。
    """

    def __init__(
        self,
        agent_id: str,
        config: Mapping[str, Any],
        embedding_model: Any | None = ...,
        vector_index: Any | None = ...,
    ) -> None:
        """构造知识库管理器。

        Args:
            agent_id: agent 标识（default 回退主库）
            config: knowledge 配置段（已 auto_fill）
            embedding_model: 嵌入模型（可为 None，向量不可用时降级 FTS/LIKE）
            vector_index: 向量索引适配器（可为 None）

        Raises:
            KnowledgeStoreError: 存储初始化失败（503）
        """
        ...

    async def add_document(
        self,
        filename: str,
        mime: str,
        data: bytes | None = ...,
        source_path: str | None = ...,
        tags: Sequence[str] = ...,
        title: str | None = ...,
    ) -> dict:
        """上传并解析文档（文本/图片/音频/视频）。

        Returns:
            dict: 符合 knowledge_document 的文档记录（含 deduplicated 标记语义由实现补充）

        Raises:
            KnowledgeUnsupportedMediaError: MIME 不在白名单（415）
            KnowledgeValidationError: 参数或数据不符合契约（400）
            KnowledgeParseError: 解析失败（500）
            KnowledgeFFmpegUnavailableError: 音视频抽取依赖不可用（503）
            KnowledgeStoreError: 存储不可用（503）
        """
        ...

    async def add_experience(
        self,
        title: str | None = ...,
        content: str = ...,
        tags: Sequence[str] = ...,
        importance: int = 3,
    ) -> dict:
        """写入可复用经验（item_type=experience）。

        title 省略时取规范化 content 前 40 字符（去换行、压缩空白）。

        Returns:
            dict: 符合 knowledge_item 的条目记录

        Raises:
            KnowledgeValidationError: content 为空或 importance 越界（400）
            KnowledgeStoreError: 存储不可用（503）
        """
        ...

    async def search(
        self,
        query: str,
        top_k: int = 8,
        tags: Sequence[str] | None = ...,
        item_type: str | None = ...,
    ) -> list[dict]:
        """混合检索（向量 + FTS，RRF 融合；向量不可用时降级关键词）。

        Returns:
            list[dict]: 符合 knowledge_search_hit 的命中列表（降级时实现补充 fallback 标记）
        """
        ...

    def list_items(
        self,
        item_type: str | None = ...,
        tags: Sequence[str] | None = ...,
        q: str | None = ...,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """分页列出知识条目。"""
        ...

    def get_item(self, item_id: str) -> dict | None:
        """按 item_id 查询条目；不存在返回 None。"""
        ...

    async def delete_item(self, item_id: str) -> bool:
        """软删除条目并删除其向量；返回是否删除成功。"""
        ...

    def list_documents(self, limit: int = 20, offset: int = 0) -> dict:
        """分页列出文档与解析状态。"""
        ...

    def get_document(self, document_id: str) -> dict | None:
        """按 document_id 查询文档；不存在返回 None。"""
        ...

    async def delete_document(self, document_id: str) -> bool:
        """删除文档及其分块、向量与物理文件；返回是否删除成功。"""
        ...

    def health(self) -> dict:
        """知识库健康检查（enabled / vector_enabled / fts_enabled / asr_provider / ffmpeg_available）。"""
        ...


def parse(
    source_path: str,
    filename: str,
    mime: str,
    config: dict | None = ...,
) -> "ParseResult":
    """统一解析入口：按 MIME/扩展名分派到文本/图片/音频/视频解析器。

    Returns:
        "ParseResult": 解析结果（text_content / parse_status / parse_error / metadata / source_refs）
    """
    ...


# 契约占位：真实实现 `KnowledgeError` 继承 backend.core.exceptions.CXHMSException
class KnowledgeError(Exception): ...


class KnowledgeValidationError(KnowledgeError): ...


class KnowledgeParseError(KnowledgeError): ...


class KnowledgeUnsupportedMediaError(KnowledgeError): ...


class KnowledgeStoreError(KnowledgeError): ...


class KnowledgeASRUnavailableError(KnowledgeError): ...


class KnowledgeFFmpegUnavailableError(KnowledgeError): ...
