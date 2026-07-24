# -*- coding: utf-8 -*-
"""通过 SSE 传输的最小 MCP 测试服务。"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test_sse_mcp", host="127.0.0.1", port=8090)


@mcp.tool()
def say_hello() -> str:
    """返回固定问候语，用于验证 SSE MCP 工具调用。"""
    return "Hello, Cash"


if __name__ == "__main__":
    print("SSE 测试 MCP 已启动：http://127.0.0.1:8090/sse")
    print("按 Ctrl+C 停止服务")
    mcp.run(transport="sse")
