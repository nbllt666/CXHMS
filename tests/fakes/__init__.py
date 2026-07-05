"""模拟外部依赖的假实现。"""

from .fake_embedding import FakeEmbeddingModel
from .fake_vector_store import InMemoryVectorStore
from .fake_llm import FakeLLMClient
from .fake_graph import (
    InMemoryGraphDatabase,
    InMemoryGraphStore,
    make_in_memory_graph_store,
)

__all__ = [
    "FakeEmbeddingModel",
    "InMemoryVectorStore",
    "FakeLLMClient",
    "InMemoryGraphDatabase",
    "InMemoryGraphStore",
    "make_in_memory_graph_store",
]
