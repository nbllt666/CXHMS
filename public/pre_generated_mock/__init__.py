"""预生成 Mock 包。

遵循 AC 范式 v6 rules-3 §四 Mock 机制三原则：
- 预生成：基于 public/interface_stub/*.pyi 自动生成默认 Mock 实现，返回符合数据契约的模拟值。
- 零等待：开发阶段直接导入本包，无需等待真实实现就绪即可联调。
- 可覆盖：开发者可在 public/global_mock/ 下提供同名实现覆盖默认值。

切换路径：Mock → 真实实现只需修改导入路径，代码无需其他改动。
"""

from .memory_mock import MockMemoryService
from .chat_mock import MockChatService
from .agent_mock import MockAgentService
from .tool_mock import MockToolService
from .graph_mock import MockGraphService

__all__ = [
    "MockMemoryService",
    "MockChatService",
    "MockAgentService",
    "MockToolService",
    "MockGraphService",
]
