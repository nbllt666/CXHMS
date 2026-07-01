"""Token 预算管理：基于字符启发式估算 token 数，截断历史消息以适配模型上下文长度。

vLLM 无 /tokenize 端点，tiktoken 未安装，故用字符启发式：
- 英文约 4 字符/token
- 中文约 1.5 字符/token（每个中文字符约 1-2 token）
- 混合内容取折中 3 字符/token 作为粗略估计，偏保守（高估 token 数以留安全余量）
"""
import json
from typing import Dict, List, Optional, Tuple


def estimate_tokens(text: str) -> int:
    """估算字符串的 token 数（保守估计，偏高）。"""
    if not text:
        return 0
    # 统计中文字符数（CJK 统一汉字范围）
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_count = len(text) - cjk_count
    # 中文 ~1.5 字符/token，英文 ~4 字符/token，取保守估计
    return int(cjk_count / 1.2 + other_count / 3.5) + 1


def estimate_messages_tokens(messages: List[Dict]) -> int:
    """估算消息列表的总 token 数（含每条消息的 overhead ~4 token）。"""
    total = 0
    for msg in messages:
        content = msg.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        total += estimate_tokens(content) + 4  # role + delimiters overhead
        if msg.get("tool_calls"):
            total += estimate_tokens(json.dumps(msg["tool_calls"], ensure_ascii=False)) + 4
    return total


def estimate_tools_tokens(tools: Optional[List[Dict]]) -> int:
    """估算 tools schema 的 token 数。"""
    if not tools:
        return 0
    return estimate_tokens(json.dumps(tools, ensure_ascii=False))


def truncate_history_for_budget(
    messages: List[Dict],
    max_model_len: int,
    max_tokens: int,
    tools: Optional[List[Dict]] = None,
    safety_margin: int = 256,
) -> Tuple[List[Dict], int]:
    """截断消息历史以适配模型上下文长度预算。

    策略：
    1. 识别 messages 中的"固定部分"（system 类消息）和"历史部分"（user/assistant 消息）
    2. 计算固定部分 + tools + safety_margin 的 token 数
    3. 计算 history_budget = max_model_len - max_tokens - fixed_tokens
    4. 从历史末尾（最新）向前填充，直到用完预算
    5. 动态调整 max_tokens：如果输入已超 budget，缩减 max_tokens 保底

    Args:
        messages: 完整消息列表（system + history + user）
        max_model_len: 模型最大上下文长度（如 8192）
        max_tokens: 期望的最大输出 token 数
        tools: 工具 schema 列表（可选）
        safety_margin: 安全余量（token）

    Returns:
        (truncated_messages, adjusted_max_tokens)
    """
    if not messages:
        return messages, max_tokens

    tools_tokens = estimate_tools_tokens(tools)

    # 分离固定消息（system）和可截断消息（非 system）
    fixed_messages = []
    history_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            fixed_messages.append(msg)
        else:
            history_messages.append(msg)

    fixed_tokens = estimate_messages_tokens(fixed_messages) + tools_tokens + safety_margin

    # 历史预算
    history_budget = max_model_len - max_tokens - fixed_tokens

    if history_budget <= 0:
        # 固定部分 + tools 已占满预算，必须缩减 max_tokens
        # 保底留 256 token 给输出
        min_output = 256
        history_budget = max_model_len - min_output - fixed_tokens
        adjusted_max_tokens = min_output
        if history_budget <= 0:
            # 连最低输出都装不下，丢弃所有历史
            return fixed_messages, min_output
    else:
        adjusted_max_tokens = max_tokens

    # 从最新消息向前填充历史
    kept_history: List[Dict] = []
    used = 0
    for msg in reversed(history_messages):
        msg_tokens = estimate_messages_tokens([msg])
        if used + msg_tokens > history_budget:
            break
        kept_history.insert(0, msg)
        used += msg_tokens

    return fixed_messages + kept_history, adjusted_max_tokens
