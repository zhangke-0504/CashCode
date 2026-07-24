# -*- coding: utf-8 -*-
"""通过 stdio 传输的最小 MCP 测试服务。"""
import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("test_stdio_mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """返回该测试服务提供的工具定义。"""
    return [
        Tool(
            name="say_hello",
            description="返回固定问候语 Hello, Cash",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """执行测试工具。"""
    if name == "say_hello":
        return [TextContent(type="text", text="Hello, Cash")]
    return [TextContent(type="text", text=f"未知工具：{name}")]


async def main() -> None:
    """启动 stdio MCP 服务并持续处理协议消息。"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
