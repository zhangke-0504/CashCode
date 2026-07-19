# -*- coding: utf-8 -*-
"""Calculator SSE MCP server.

SSE 传输示例：与 stdio server 的最大区别是这是一个独立运行的 HTTP 服务。
需要在单独的终端启动：python mcp_servers/calculator/server.py

然后 CashCode 通过 mcp_prepare("calculator") 连接 http://127.0.0.1:8090/sse
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("calculator", host="127.0.0.1", port=8090)

# 支持的单位换算
_CONVERSIONS: dict[tuple[str, str], float] = {
    ("km", "miles"): 0.621371,
    ("miles", "km"): 1.60934,
    ("kg", "lb"):    2.20462,
    ("lb", "kg"):    0.453592,
    ("m", "ft"):     3.28084,
    ("ft", "m"):     0.3048,
    ("l", "gallon"): 0.264172,
    ("gallon", "l"): 3.78541,
}

# 温度单位特殊处理
_TEMP_CONVERSIONS: dict[tuple[str, str], object] = {
    ("c", "f"):    lambda v: v * 9 / 5 + 32,
    ("celsius", "fahrenheit"): lambda v: v * 9 / 5 + 32,
    ("f", "c"):    lambda v: (v - 32) * 5 / 9,
    ("fahrenheit", "celsius"): lambda v: (v - 32) * 5 / 9,
}


@mcp.tool()
def calculate(expression: str) -> str:
    """计算数学表达式，如 '2 + 3 * 4' 或 '(100 - 32) * 5 / 9'。
    支持：+、-、*、/、**、() 等基本运算。
    """
    # 安全白名单：只允许数字和基本运算符
    import re
    allowed = re.sub(r'[0-9\s\+\-\*\/\.\(\)\*\*]', '', expression)
    if allowed:
        return f"不支持的字符：{allowed!r}。只支持数字和 +-*/()** 运算符。"
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        return str(result)
    except ZeroDivisionError:
        return "错误：除以零"
    except Exception as exc:
        return f"计算错误：{exc}"


@mcp.tool()
def convert_unit(value: float, from_unit: str, to_unit: str) -> str:
    """单位换算。支持：
    - 长度：km ↔ miles, m ↔ ft
    - 重量：kg ↔ lb
    - 体积：l ↔ gallon
    - 温度：C ↔ F（celsius ↔ fahrenheit）
    """
    f = from_unit.strip().lower()
    t = to_unit.strip().lower()

    # 温度
    fn = _TEMP_CONVERSIONS.get((f, t))
    if fn is not None:
        result = fn(value)
        return f"{value} {from_unit} = {result:.4f} {to_unit}"

    # 其他单位
    factor = _CONVERSIONS.get((f, t))
    if factor is not None:
        result = value * factor
        return f"{value} {from_unit} = {result:.4f} {to_unit}"

    supported = ", ".join(f"{a}↔{b}" for a, b in _CONVERSIONS if a < b)
    return f"不支持的单位换算：{from_unit} → {to_unit}。支持：{supported}，以及摄氏度↔华氏度"


if __name__ == "__main__":
    print("Calculator SSE MCP server starting on http://127.0.0.1:8090/sse")
    print("Press Ctrl+C to stop")
    mcp.run(transport="sse")
