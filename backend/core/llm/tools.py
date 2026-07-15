import json
import re
import uuid
from typing import Any, Dict, List, Optional

from backend.core.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


def parse_text_tool_calls(text: str, available_tool_names: set = None) -> List[Dict]:
    """从 LLM 文本输出中解析工具调用意图。

    当 LLM 不支持 function calling 时，它会用文本模拟工具调用。
    此函数尝试从文本中提取这些工具调用，返回标准格式。

    支持的格式：
    - <execute_tool>tool_name(args)</execute_tool>
    - <tool_call>tool_name(args)</tool_call>
    - [调用工具: tool_name(args)]
    - [调用工具: tool_name()]  (无参数)
    - tool_name(arg1="value1", arg2=123)  (独立行)
    - ```tool\nname: tool_name\narguments: {...}\n```

    Args:
        text: LLM 的文本输出
        available_tool_names: 可用工具名称集合，用于验证

    Returns:
        解析出的工具调用列表，格式与 OpenAI function calling 一致
    """
    if not text:
        return []

    parsed_calls = []

    # 模式1: <execute_tool>tool_name(args)</execute_tool> 或 <tool_call>tool_name(args)</tool_call>
    pattern1 = r'<(?:execute_tool|tool_call)>\s*(\w+)\s*\((.*?)\)\s*</(?:execute_tool|tool_call)>'
    for match in re.finditer(pattern1, text, re.DOTALL):
        tool_name, args_str = match.group(1), match.group(2).strip()
        args = _parse_args_string(args_str)
        if available_tool_names is None or tool_name in available_tool_names:
            parsed_calls.append(_make_tool_call(tool_name, args))
            logger.info(f"文本工具调用解析(模式1): {tool_name}({args})")

    # 模式2: [调用工具: tool_name(args)] 或 [调用工具: tool_name()]
    pattern2 = r'\[调用工具[：:]\s*(\w+)\s*\((.*?)\)\s*\]'
    for match in re.finditer(pattern2, text, re.DOTALL):
        tool_name, args_str = match.group(1), match.group(2).strip()
        args = _parse_args_string(args_str)
        if available_tool_names is None or tool_name in available_tool_names:
            parsed_calls.append(_make_tool_call(tool_name, args))
            logger.info(f"文本工具调用解析(模式2): {tool_name}({args})")

    # 模式3: ```tool\nname: tool_name\narguments: {...}\n```
    pattern3 = r'```tool\s*\n\s*name[：:]\s*(\w+)\s*\n\s*arguments[：:]\s*(\{.*?\})\s*\n```'
    for match in re.finditer(pattern3, text, re.DOTALL):
        tool_name, args_str = match.group(1), match.group(2).strip()
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}
        if available_tool_names is None or tool_name in available_tool_names:
            parsed_calls.append(_make_tool_call(tool_name, args))
            logger.info(f"文本工具调用解析(模式3): {tool_name}({args})")

    # 模式4: 独立行的 tool_name(key="value", key2=123) - 仅匹配已知工具名
    # 注意：此模式是启发式匹配，容易误匹配 LLM 解释性文本中提到的工具名。
    # 因此要求参数非空，过滤掉 tool_name() 这种空参数的假调用。
    if available_tool_names:
        pattern4 = r'^\s*(\w+)\s*\((.*?)\)\s*$'
        for line in text.split('\n'):
            line = line.strip()
            match = re.match(pattern4, line)
            if match:
                tool_name, args_str = match.group(1), match.group(2).strip()
                if tool_name in available_tool_names:
                    # 跳过空参数调用：tool_name() 通常是 LLM 在解释性文本中
                    # 提到工具名，而非真正的工具调用，容易产生假的空工具调用
                    if not args_str:
                        logger.debug(f"文本工具调用解析(模式4)跳过空参数调用: {tool_name}()")
                        continue
                    args = _parse_args_string(args_str)
                    # 解析后参数仍为空，也跳过（无法提取有效参数）
                    if not args:
                        logger.debug(f"文本工具调用解析(模式4)跳过无法解析参数的调用: {tool_name}({args_str})")
                        continue
                    # 检查是否已被前面的模式匹配过（避免重复）
                    if not any(c["function"]["name"] == tool_name for c in parsed_calls):
                        parsed_calls.append(_make_tool_call(tool_name, args))
                        logger.info(f"文本工具调用解析(模式4): {tool_name}({args})")

    return parsed_calls


def _parse_args_string(args_str: str) -> Dict[str, Any]:
    """解析工具参数字符串为字典。

    支持格式：
    - key="value", key2=123
    - key='value', key2=True
    - 空字符串 -> {}
    - JSON 字符串
    """
    if not args_str:
        return {}

    # 尝试作为 JSON 解析
    args_str = args_str.strip()
    if args_str.startswith('{'):
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:
            pass

    # 解析 key=value 对
    result = {}
    # 匹配 key="value" 或 key='value' 或 key=123 或 key=True/False/None
    pattern = r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\w+)'
    for match in re.finditer(pattern, args_str):
        key = match.group(1)
        value = match.group(2)

        # 去掉引号
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        elif value.lower() == 'true':
            value = True
        elif value.lower() == 'false':
            value = False
        elif value.lower() == 'none':
            value = None
        else:
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass  # 保持字符串

        result[key] = value

    return result


def _make_tool_call(tool_name: str, args: Dict[str, Any]) -> Dict:
    """创建标准格式的工具调用对象"""
    call_id = f"call_{uuid.uuid4().hex[:8]}"
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(args, ensure_ascii=False) if args else "{}",
        },
    }


def is_empty_tool_args(tool_call: Dict) -> bool:
    """判断工具调用的参数是否为空。

    兼容两种 arguments 格式：
    - 字符串（vLLM/OpenAI 标准）："{}" 或 "" 视为空
    - 对象（Ollama 格式）：{} 视为空

    Args:
        tool_call: 工具调用对象，格式为 {"function": {"name": ..., "arguments": ...}}

    Returns:
        True 如果参数为空，False 否则
    """
    args = tool_call.get("function", {}).get("arguments")
    if args is None:
        return True
    if isinstance(args, str):
        return args.strip() in ("", "{}")
    if isinstance(args, dict):
        return len(args) == 0
    return False


def strip_text_tool_calls(text: str) -> str:
    """从文本中移除工具调用标记，只保留纯文本内容"""
    if not text:
        return text

    # 移除 <execute_tool>...</execute_tool> 和 <tool_call>...</tool_call>
    text = re.sub(r'<(?:execute_tool|tool_call)>.*?</(?:execute_tool|tool_call)>', '', text, flags=re.DOTALL)
    # 移除 [调用工具: ...]
    text = re.sub(r'\[调用工具[：:].*?\]', '', text, flags=re.DOTALL)
    # 移除 ```tool\n...\n```
    text = re.sub(r'```tool\s*\n.*?\n```', '', text, flags=re.DOTALL)
    # 移除 "(假设工具执行成功...)" 之类的模拟数据标记
    text = re.sub(r'\(假设工具执行成功.*?\)', '', text, flags=re.DOTALL)
    # 移除 "[调用工具: xxx()]" 后跟的模拟结果标记
    text = re.sub(r'\[调用工具[：:].*?\]\s*\(.*?\)', '', text, flags=re.DOTALL)

    return text.strip()


class LLMTools:
    def __init__(self, llm_client):
        self.client = llm_client

    def format_tools_for_llm(self, tools: List[Dict]) -> List[Dict]:
        formatted = []
        for tool in tools:
            formatted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "parameters": tool.get("parameters", {}),
                    },
                }
            )
        return formatted

    def parse_tool_calls(self, response_message: Dict) -> List[Dict]:
        tool_calls = response_message.get("tool_calls", [])
        parsed = []

        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                parsed.append(
                    {
                        "id": tool_call.get("id", ""),
                        "type": tool_call.get("type", "function"),
                        "function": {
                            "name": tool_call.get("function", {}).get("name", ""),
                            "arguments": tool_call.get("function", {}).get("arguments", {}),
                        },
                    }
                )

        return parsed

    def create_tool_result_message(self, tool_call_id: str, tool_name: str, result: str) -> Dict:
        return {"role": "tool", "content": result, "tool_call_id": tool_call_id, "name": tool_name}

    async def execute_tools(self, tool_calls: List[Dict], tool_registry) -> List[Dict]:
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name", "")
            arguments = tool_call.get("function", {}).get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            tool_call_id = tool_call.get("id", "")

            # 必须用异步版本，避免阻塞事件循环——见变更文档 20260714_模块0_修复async上下文同步工具调用死锁
            result = await tool_registry.call_tool_async(tool_name, arguments)

            message = self.create_tool_result_message(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                result=json.dumps(result, ensure_ascii=False),
            )

            results.append(message)

        return results

    async def chat_with_tools(
        self, messages: List[Dict], tools: List[Dict], tool_registry, max_iterations: int = 5
    ) -> Dict:
        current_messages = messages.copy()
        iterations = 0

        while iterations < max_iterations:
            response = await self.client.chat(
                messages=current_messages,
                tools=self.format_tools_for_llm(tools) if tools else None,
            )

            if response.finish_reason == "error":
                return {"content": response.content, "error": "LLM调用失败"}

            response_message = {"role": "assistant", "content": response.content, "tool_calls": response.tool_calls}

            tool_calls = self.parse_tool_calls(response_message)

            if not tool_calls:
                return {"content": response.content, "tool_calls": []}

            current_messages.append(response_message)

            tool_results = await self.execute_tools(tool_calls, tool_registry)
            current_messages.extend(tool_results)

            iterations += 1

        return {
            "content": response.content,
            "tool_calls": tool_calls,
            "warning": "达到最大迭代次数",
        }
