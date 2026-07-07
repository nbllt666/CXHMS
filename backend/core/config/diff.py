"""配置差异计算模块。

提供 ConfigDiff dataclass 与 compute_diff 函数，用于在配置热重载时
识别哪些顶层段发生了变化以及具体字段路径，供下游决定增量重载策略。

设计要点：
    - 输入两个 CXHMSConfig 实例（来自 config.settings），递归对比 12 个顶层段
    - 顶层段映射：llm/models/vector/acp/database/memory/context/rate_limit/
      cors/system/graph/cxfc
    - changed_sections 记录哪个顶层段变化（如 "models"、"memory"）
    - field_changes 记录具体字段路径（如 "models.main.model"、"memory.weaviate.host"）
    - 无变化返回空 ConfigDiff

特殊规则：
    - 顶层 vector 段变化 → changed_sections={'vector'}
    - memory.vector_backend 或 memory.{milvus_lite/qdrant/weaviate/chroma} 子段变化
      → changed_sections={'memory'}，field_changes 记录具体嵌套字段路径
"""

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, List, Set


@dataclass
class ConfigDiff:
    """配置差异。

    Attributes:
        changed_sections: 发生变化的顶层段名集合（如 {"models", "memory"}）。
        field_changes: 具体字段路径列表（如 ["models.main.model", "memory.weaviate.host"]）。
    """

    changed_sections: Set[str] = field(default_factory=set)
    field_changes: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """无任何变化时返回 True。"""
        return not self.changed_sections


# CXHMSConfig 的 12 个顶层段（与 config.settings.CXHMSConfig 字段对齐）
_TOP_LEVEL_SECTIONS = (
    "llm",
    "models",
    "vector",
    "acp",
    "database",
    "memory",
    "context",
    "rate_limit",
    "cors",
    "system",
    "graph",
    "cxfc",
)


def _to_dict(obj: Any) -> Any:
    """将 dataclass 实例递归转为纯 dict / list / 标量。

    使用 dataclasses.asdict 实现，自动递归嵌套 dataclass。
    若 asdict 失败（非 dataclass），回退到 obj.__dict__ 浅拷贝。
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def _diff_dict(old: Any, new: Any, prefix: str, field_changes: List[str]) -> bool:
    """递归比较两个 dict，记录叶子字段路径到 field_changes。

    Returns:
        True 表示存在差异，False 表示无差异。
    """
    # 标量或类型不一致 → 直接比较
    if not isinstance(old, dict) or not isinstance(new, dict):
        return old != new

    changed = False
    all_keys = set(old.keys()) | set(new.keys())
    for key in all_keys:
        path = f"{prefix}.{key}" if prefix else key
        old_val = old.get(key)
        new_val = new.get(key)

        if isinstance(old_val, dict) and isinstance(new_val, dict):
            # 嵌套 dict → 递归
            if _diff_dict(old_val, new_val, path, field_changes):
                changed = True
        elif isinstance(old_val, list) and isinstance(new_val, list):
            # 列表直接比较（不递归到元素内部路径）
            if old_val != new_val:
                changed = True
                field_changes.append(path)
        else:
            if old_val != new_val:
                changed = True
                field_changes.append(path)

    return changed


def compute_diff(old: Any, new: Any) -> ConfigDiff:
    """计算两个 CXHMSConfig 实例的差异。

    Args:
        old: 旧的 CXHMSConfig 实例。
        new: 新的 CXHMSConfig 实例。

    Returns:
        ConfigDiff: 差异描述。无差异时 is_empty() 返回 True。
    """
    diff = ConfigDiff()

    if old is None and new is None:
        return diff

    # 首次加载（old 为 None）→ 视为全量变化
    if old is None:
        if new is None:
            return diff
        for section in _TOP_LEVEL_SECTIONS:
            if hasattr(new, section):
                diff.changed_sections.add(section)
                # 全量变化时也记录每个段的字段路径（顶层前缀 + 子字段）
                new_section_val = getattr(new, section)
                new_section_dict = _to_dict(new_section_val)
                if isinstance(new_section_dict, dict):
                    for sub_key in new_section_dict.keys():
                        diff.field_changes.append(f"{section}.{sub_key}")
                else:
                    diff.field_changes.append(section)
        return diff

    # 正常 diff：逐段比较
    for section in _TOP_LEVEL_SECTIONS:
        if not (hasattr(old, section) and hasattr(new, section)):
            continue

        old_section = getattr(old, section)
        new_section = getattr(new, section)

        # 同一对象引用 → 跳过
        if old_section is new_section:
            continue

        old_dict = _to_dict(old_section)
        new_dict = _to_dict(new_section)

        section_changes: List[str] = []
        if _diff_dict(old_dict, new_dict, section, section_changes):
            diff.changed_sections.add(section)
            diff.field_changes.extend(section_changes)

    return diff
