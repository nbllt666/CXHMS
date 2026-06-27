"""模拟外部依赖的假实现。"""

from backend.tests.simulation.fakes.fake_embedding import FakeEmbeddingModel
from backend.tests.simulation.fakes.fake_vector_store import InMemoryVectorStore
from backend.tests.simulation.fakes.fake_llm import FakeLLMClient
from backend.tests.simulation.fakes.fake_graph import (
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
