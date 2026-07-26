# -*- coding: utf-8 -*-
"""临时测试脚本：验证 MCP 连接 + 工具调用。

运行方式（在项目根目录）：
    python test_mcp.py
"""
import asyncio
import sys

sys.path.insert(0, "server")

from app.agent.tools.mcp import establish_mcp_sessions, load_mcp_tools
from app.agent.tools.registry import ToolRegistry


async def main() -> None:
    servers = {
        "weather": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["mcp_servers/weather/server.py"],
        }
    }

    print("Connecting to weather MCP server...")
    handles = await establish_mcp_sessions(servers)

    if "weather" not in handles:
        print("FAIL: could not connect to weather server")
        return

    registry = ToolRegistry()
    await load_mcp_tools(handles, registry)

    print(f"Registered tools: {registry.tool_names}")

    # 调用 get_weather
    result = await registry.execute("mcp_weather_get_weather", {"city": "北京"})
    print(f"get_weather('北京') → {result}")

    # 调用 get_forecast
    result2 = await registry.execute("mcp_weather_get_forecast", {"city": "上海", "days": 3})
    print(f"get_forecast('上海', 3) →\n{result2}")

    # 关闭连接
    for handle in handles.values():
        await handle.aclose()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
