# CXFC 测试工具预置工具定义与执行处理器
"""预置工具集：提供计算器、字符串反转、时间查询、回声四个测试工具。

每个工具包含：
- 定义（name / description / parameters JSON Schema）：暴露给主系统
- 处理器（handler）：当主系统通过 POST /call 调用时实际执行
"""
import datetime
import math
from typing import Any, Dict, List


def _tool_calculator(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """简易计算器：支持加减乘除、幂运算、开方。"""
    op = str(arguments.get("operation", "")).strip()
    a = arguments.get("a")
    b = arguments.get("b")

    try:
        a = float(a) if a is not None else None
        b = float(b) if b is not None else None
    except (TypeError, ValueError) as e:
        return {"success": False, "error": f"参数类型错误: {e}"}

    if op == "add":
        if a is None or b is None:
            return {"success": False, "error": "add 操作需要 a 和 b 两个参数"}
        return {"success": True, "result": a + b}
    if op == "subtract":
        if a is None or b is None:
            return {"success": False, "error": "subtract 操作需要 a 和 b 两个参数"}
        return {"success": True, "result": a - b}
    if op == "multiply":
        if a is None or b is None:
            return {"success": False, "error": "multiply 操作需要 a 和 b 两个参数"}
        return {"success": True, "result": a * b}
    if op == "divide":
        if a is None or b is None:
            return {"success": False, "error": "divide 操作需要 a 和 b 两个参数"}
        if b == 0:
            return {"success": False, "error": "除数不能为 0"}
        return {"success": True, "result": a / b}
    if op == "power":
        if a is None or b is None:
            return {"success": False, "error": "power 操作需要 a 和 b 两个参数"}
        return {"success": True, "result": math.pow(a, b)}
    if op == "sqrt":
        if a is None:
            return {"success": False, "error": "sqrt 操作需要 a 参数"}
        if a < 0:
            return {"success": False, "error": "不能对负数开平方"}
        return {"success": True, "result": math.sqrt(a)}

    return {"success": False, "error": f"不支持的操作: {op}"}


def _tool_string_reverse(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """字符串反转：返回输入字符串的逆序。"""
    text = arguments.get("text", "")
    if not isinstance(text, str):
        return {"success": False, "error": "text 参数必须是字符串"}
    return {"success": True, "result": text[::-1], "length": len(text)}


def _tool_time_query(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """时间查询：返回当前时间或格式化指定时间。"""
    fmt = arguments.get("format", "%Y-%m-%d %H:%M:%S")
    if not isinstance(fmt, str):
        return {"success": False, "error": "format 参数必须是字符串"}
    now = datetime.datetime.now()
    try:
        return {
            "success": True,
            "result": now.strftime(fmt),
            "iso8601": now.isoformat(),
            "timestamp": now.timestamp(),
            "weekday": now.strftime("%A"),
        }
    except Exception as e:
        return {"success": False, "error": f"时间格式化失败: {e}"}


def _tool_echo(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """回声工具：原样返回输入内容，用于验证调用链路。"""
    message = arguments.get("message", "")
    return {
        "success": True,
        "result": message,
        "received_at": datetime.datetime.now().isoformat(),
        "echo_type": type(message).__name__,
    }


# 工具定义（JSON Schema 格式，供主系统注册时使用）
PRESET_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "calculator",
        "description": "简易计算器，支持 add/subtract/multiply/divide/power/sqrt 操作",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide", "power", "sqrt"],
                    "description": "要执行的运算",
                },
                "a": {"type": "number", "description": "第一个操作数"},
                "b": {"type": "number", "description": "第二个操作数（sqrt 不需要）"},
            },
            "required": ["operation", "a"],
        },
    },
    {
        "name": "string_reverse",
        "description": "字符串反转工具，返回输入字符串的逆序",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要反转的字符串"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "time_query",
        "description": "时间查询工具，返回当前时间，支持自定义格式化",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "strftime 格式字符串，默认 '%Y-%m-%d %H:%M:%S'",
                    "default": "%Y-%m-%d %H:%M:%S",
                },
            },
            "required": [],
        },
    },
    {
        "name": "echo",
        "description": "回声工具，原样返回输入内容，用于验证调用链路",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要回声的内容",
                },
            },
            "required": ["message"],
        },
    },
]

# 预置 Skills 定义（JSON Schema 格式，供主系统注册时使用）
# 与 tools 定义格式一致：name / description / parameters
PRESET_SKILL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "text_summary",
        "description": "文本摘要：将长文本总结为要点",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要摘要的文本"},
                "max_length": {
                    "type": "integer",
                    "description": "最大摘要长度",
                    "default": 100,
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "translation",
        "description": "翻译：多语言翻译",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要翻译的文本"},
                "target_language": {
                    "type": "string",
                    "description": "目标语言，例如 en/zh/ja/fr",
                },
                "source_language": {
                    "type": "string",
                    "description": "源语言，默认 auto 自动识别",
                    "default": "auto",
                },
            },
            "required": ["text", "target_language"],
        },
    },
    {
        "name": "code_generation",
        "description": "代码生成：根据描述生成代码",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "代码需求描述",
                },
                "language": {
                    "type": "string",
                    "description": "编程语言，例如 python/javascript/java",
                    "default": "python",
                },
                "framework": {
                    "type": "string",
                    "description": "目标框架，可选，例如 flask/react",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "sentiment_analysis",
        "description": "情感分析：分析文本情感倾向",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要分析的文本"},
                "detail_level": {
                    "type": "string",
                    "enum": ["brief", "detailed"],
                    "description": "分析详细程度，brief 仅给出倾向，detailed 给出分数与理由",
                    "default": "brief",
                },
            },
            "required": ["text"],
        },
    },
]

# 工具名 → 处理器映射
TOOL_HANDLERS = {
    "calculator": _tool_calculator,
    "string_reverse": _tool_string_reverse,
    "time_query": _tool_time_query,
    "echo": _tool_echo,
}


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """执行指定工具，返回结果字典。

    Args:
        tool_name: 工具名称
        arguments: 工具参数

    Returns:
        包含 success 字段的结果字典
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {"success": False, "error": f"未知工具: {tool_name}"}
    try:
        return handler(arguments or {})
    except Exception as e:
        return {"success": False, "error": f"工具执行异常: {e}"}


def get_preset_definitions() -> List[Dict[str, Any]]:
    """返回预置工具定义的深拷贝，避免外部修改污染。"""
    import copy

    return copy.deepcopy(PRESET_TOOL_DEFINITIONS)


def list_tool_names() -> List[str]:
    """返回所有预置工具名列表。"""
    return [t["name"] for t in PRESET_TOOL_DEFINITIONS]


def get_preset_skills() -> List[Dict[str, Any]]:
    """返回预置 skills 定义的深拷贝，避免外部修改污染。"""
    import copy

    return copy.deepcopy(PRESET_SKILL_DEFINITIONS)


def list_skill_names() -> List[str]:
    """返回所有预置 skill 名列表。"""
    return [s["name"] for s in PRESET_SKILL_DEFINITIONS]
