# -*- coding: utf-8 -*-
"""Notes mock MCP server.

提供两个工具：
- create_note(title, content): 创建便签，持久化到 data/ 目录
- list_notes(): 列出所有便签标题

通过 stdio 传输运行，供 CashCode agent 通过 MCP 协议调用。
用法：python mcp_servers/notes/server.py
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("notes")

# 便签存储目录（相对于项目根目录运行）
_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _note_path(title: str) -> Path:
    """将标题转为安全文件名。"""
    safe = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in title)
    safe = safe.strip().replace(" ", "_")[:50]
    return _DATA_DIR / f"{safe}.json"


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_note",
            description="创建一条便签，保存标题和内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "便签标题"},
                    "content": {"type": "string", "description": "便签内容"},
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="list_notes",
            description="列出所有已保存的便签标题",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "create_note":
        title = arguments.get("title", "").strip()
        content = arguments.get("content", "").strip()
        if not title:
            return [TextContent(type="text", text="错误：标题不能为空")]

        path = _note_path(title)
        note = {
            "title": title,
            "content": content,
            "created_at": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
        return [TextContent(type="text", text=f"便签「{title}」已保存")]

    elif name == "list_notes":
        files = sorted(_DATA_DIR.glob("*.json"))
        if not files:
            return [TextContent(type="text", text="暂无便签")]
        titles = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                titles.append(f"- {data.get('title', f.stem)}")
            except Exception:
                titles.append(f"- {f.stem}")
        return [TextContent(type="text", text="所有便签：\n" + "\n".join(titles))]

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
