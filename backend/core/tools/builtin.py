"""
内置工具 - 提供基础功能工具
"""
import json
import math
from datetime import datetime
from typing import Dict, Any, Optional

from .registry import tool_registry


def register_builtin_tools():
    """注册所有内置工具"""
    
    # 计算器工具
    tool_registry.register(
        name="calculator",
        description="执行数学计算，支持基本运算、三角函数、对数等",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，例如: 1 + 2, sin(3.14), sqrt(16)"
                }
            },
            "required": ["expression"]
        },
        function=calculator,
        category="math",
        tags=["math", "calculation"],
        examples=[
            "计算 15 * 23",
            "求 sin(30度)",
            "sqrt(256) 等于多少"
        ]
    )
    
    # 日期时间工具
    tool_registry.register(
        name="datetime",
        description="获取当前日期和时间信息",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "日期格式，例如: YYYY-MM-DD, HH:mm:ss",
                    "default": "YYYY-MM-DD HH:mm:ss"
                },
                "timezone": {
                    "type": "string",
                    "description": "时区，例如: UTC, Asia/Shanghai",
                    "default": "local"
                }
            }
        },
        function=get_datetime,
        category="time",
        tags=["time", "date"],
        examples=[
            "现在几点了？",
            "今天的日期是？",
            "当前UTC时间"
        ]
    )
    
    # 随机数生成器
    tool_registry.register(
        name="random",
        description="生成随机数",
        parameters={
            "type": "object",
            "properties": {
                "min": {
                    "type": "number",
                    "description": "最小值",
                    "default": 0
                },
                "max": {
                    "type": "number",
                    "description": "最大值",
                    "default": 100
                },
                "type": {
                    "type": "string",
                    "enum": ["int", "float"],
                    "description": "随机数类型",
                    "default": "int"
                }
            }
        },
        function=generate_random,
        category="utility",
        tags=["random", "utility"]
    )
    
    # JSON 格式化工具
    tool_registry.register(
        name="json_format",
        description="格式化 JSON 字符串",
        parameters={
            "type": "object",
            "properties": {
                "json_string": {
                    "type": "string",
                    "description": "要格式化的 JSON 字符串"
                },
                "indent": {
                    "type": "integer",
                    "description": "缩进空格数",
                    "default": 2
                }
            },
            "required": ["json_string"]
        },
        function=format_json,
        category="utility",
        tags=["json", "format"]
    )


def calculator(expression: str) -> Dict[str, Any]:
    """计算器工具"""
    try:
        allowed_names = {
            "abs": abs,
            "round": round,
            "max": max,
            "min": min,
            "sum": sum,
            "pow": pow,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "floor": math.floor,
            "ceil": math.ceil,
            "pi": math.pi,
            "e": math.e,
        }
        
        expr = expression.replace("^", "**")
        result = eval(expr, {"__builtins__": {}}, allowed_names)
        
        return {
            "expression": expression,
            "result": result,
            "type": type(result).__name__
        }
    except Exception as e:
        return {
            "error": f"计算错误: {str(e)}"
        }


def get_datetime(format: str = "YYYY-MM-DD HH:mm:ss", timezone: str = "local") -> Dict[str, Any]:
    """获取当前日期时间"""
    try:
        now = datetime.now()
        
        format_str = format
        format_str = format_str.replace("YYYY", "%Y")
        format_str = format_str.replace("MM", "%m")
        format_str = format_str.replace("DD", "%d")
        format_str = format_str.replace("HH", "%H")
        format_str = format_str.replace("mm", "%M")
        format_str = format_str.replace("ss", "%S")
        
        formatted = now.strftime(format_str)
        
        return {
            "datetime": formatted,
            "timestamp": now.timestamp(),
            "iso": now.isoformat(),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.strftime("%A"),
            "timezone": timezone
        }
    except Exception as e:
        return {
            "error": f"获取时间错误: {str(e)}"
        }


def generate_random(min: float = 0, max: float = 100, type: str = "int") -> Dict[str, Any]:
    """生成随机数"""
    import random
    
    if type == "int":
        result = random.randint(int(min), int(max))
    else:
        result = random.uniform(min, max)
    
    return {
        "value": result,
        "type": type,
        "range": [min, max]
    }


def format_json(json_string: str, indent: int = 2) -> Dict[str, Any]:
    """格式化 JSON"""
    try:
        data = json.loads(json_string)
        formatted = json.dumps(data, ensure_ascii=False, indent=indent)
        return {
            "formatted": formatted,
            "valid": True,
            "type": type(data).__name__
        }
    except json.JSONDecodeError as e:
        return {
            "error": f"JSON 解析错误: {str(e)}",
            "valid": False
        }
    except Exception as e:
        return {
            "error": f"格式化错误: {str(e)}",
            "valid": False
        }
