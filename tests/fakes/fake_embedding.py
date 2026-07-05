"""确定性假嵌入模型，用于端到端模拟测试。

基于字符级 2-gram/3-gram 词袋 + 哈希分桶构造 256 维向量：
- 相同文本返回完全相同的向量（进程内缓存）。
- 共享 n-gram 越多，向量余弦相似度越高，从而具备一定语义性。
- 向量经 L2 归一化，余弦相似度等于点积。
- 使用 hashlib (sha1) 哈希以避免 Python 内置 hash() 的进程级随机化。
"""

import hashlib
import math
from typing import Dict, List

from backend.core.memory.embedding import EmbeddingModel

_DIMENSION = 256


def _char_ngrams(text: str) -> List[str]:
    """提取字符级 2-gram 与 3-gram（适用于中文等无空格分隔的文本）。"""
    grams: List[str] = []
    n = len(text)
    for size in (2, 3):
        if n < size:
            break
        for i in range(n - size + 1):
            grams.append(text[i : i + size])
    return grams


def _hash_to_bucket(gram: str, mod: int = _DIMENSION) -> int:
    """用 sha1 将 n-gram 确定性地映射到 [0, mod) 桶。"""
    digest = hashlib.sha1(gram.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % mod


def _raw_vector(text: str) -> List[float]:
    """根据 n-gram 词袋累加得到未归一化向量。"""
    vec = [0.0] * _DIMENSION
    for gram in _char_ngrams(text):
        vec[_hash_to_bucket(gram)] += 1.0
    return vec


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度。

    输入向量即使未归一化也能得到正确结果；归一化向量退化为点积。
    """
    if not a or not b:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class FakeEmbeddingModel(EmbeddingModel):
    """确定性假嵌入模型（继承真实 ABC 契约）。

    使用字符级 2-gram/3-gram 词袋 + sha1 哈希分桶构造 256 维归一化向量。
    """

    def __init__(self) -> None:
        self._dim = _DIMENSION
        self._cache: Dict[str, List[float]] = {}

    async def get_embedding(self, text: str) -> List[float]:
        if text in self._cache:
            return self._cache[text]
        vec = _l2_normalize(_raw_vector(text))
        self._cache[text] = vec
        return vec

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [await self.get_embedding(text) for text in texts]

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return "fake/n-gram"

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        return cosine_similarity(a, b)
