"""模块11 知识库文本分块（spec「文档入库后分块」）。

规则：
- 按 `chunk_size` 字符切分，相邻块保留 `chunk_overlap` 字符重叠；
- 空白块（仅空白字符）直接丢弃，不写入条目；
- 单文档最多 `max_chunks` 块，超出截断；
- 参数越界自动收敛，保证不会死循环。
"""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """统一换行符并去除首尾空白（不压缩内部空白，保留段落结构）。"""
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    max_chunks: int = 2000,
) -> list[str]:
    """把长文本切分为带重叠的分块列表。

    Args:
        text: 待切分文本
        chunk_size: 单块字符数（下限 1）
        chunk_overlap: 相邻块重叠字符数（收敛到 `[0, chunk_size - 1]`）
        max_chunks: 最大块数（下限 1，超出截断）

    Returns:
        非空白块列表；空文本返回 `[]`
    """
    normalized = normalize_text(text)
    if not normalized:
        return []

    size = max(1, int(chunk_size))
    overlap = max(0, min(int(chunk_overlap), size - 1))
    limit = max(1, int(max_chunks))

    chunks: list[str] = []
    start = 0
    length = len(normalized)
    while start < length and len(chunks) < limit:
        end = min(start + size, length)
        piece = normalized[start:end]
        if piece.strip():
            chunks.append(piece.strip())
        if end >= length:
            break
        # 重叠步进：size - overlap ≥ 1，保证必然前进
        start = end - overlap
    return chunks
