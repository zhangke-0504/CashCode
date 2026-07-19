# -*- coding: utf-8 -*-
"""Weather mock MCP server.

提供两个工具：
- get_weather(city): 返回城市当前 mock 天气
- get_forecast(city, days): 返回城市未来 N 天 mock 预报

通过 stdio 传输运行，供 CashCode agent 通过 MCP 协议调用。
用法：python mcp_servers/weather/server.py
"""
import asyncio
import random
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("weather")

# Mock 天气数据
_CONDITIONS = ["晴", "多云", "阴", "小雨", "大风"]
_CITIES = {
    "北京": {"temp_base": 25, "condition": "晴"},
    "上海": {"temp_base": 28, "condition": "多云"},
    "广州": {"temp_base": 32, "condition": "阵雨"},
    "成都": {"temp_base": 22, "condition": "阴"},
    "杭州": {"temp_base": 27, "condition": "晴"},
}


def _get_mock_weather(city: str) -> dict:
    """返回城市 mock 天气数据。"""
    base = _CITIES.get(city, {"temp_base": 20, "condition": "晴"})
    temp = base["temp_base"] + random.randint(-3, 3)
    humidity = random.randint(30, 80)
    return {
        "city": city,
        "condition": base["condition"],
        "temp": temp,
        "humidity": humidity,
    }


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_weather",
            description="获取指定城市的当前天气情况",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如：北京、上海"},
                },
                "required": ["city"],
            },
        ),
        Tool(
            name="get_forecast",
            description="获取指定城市未来 N 天的天气预报",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"},
                    "days": {
                        "type": "integer",
                        "description": "预报天数，1-7",
                        "minimum": 1,
                        "maximum": 7,
                    },
                },
                "required": ["city", "days"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_weather":
        city = arguments.get("city", "未知城市")
        w = _get_mock_weather(city)
        text = (
            f"{w['city']}当前天气：{w['condition']}，"
            f"气温 {w['temp']}°C，湿度 {w['humidity']}%"
        )
        return [TextContent(type="text", text=text)]

    elif name == "get_forecast":
        city = arguments.get("city", "未知城市")
        days = int(arguments.get("days", 3))
        lines = [f"{city} 未来 {days} 天天气预报："]
        for i in range(1, days + 1):
            w = _get_mock_weather(city)
            lines.append(f"  第 {i} 天：{w['condition']}，{w['temp']}°C")
        return [TextContent(type="text", text="\n".join(lines))]

    return [TextContent(type="text", text=f"未知工具：{name}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
