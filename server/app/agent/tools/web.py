"""Web tools: WebFetchTool (抓取网页) and WebSearchTool (DuckDuckGo 搜索).

参考 spore ``core.agent.tools.web``，简化版：
- 去掉代理、多媒体处理、prompt injection 检测等复杂机制
- WebFetch：httpx GET → strip HTML → 截断 3000 字符
- WebSearch：DuckDuckGo Instant Answer API，无需 API key
"""
from __future__ import annotations

import html
import re
from typing import Any

import httpx

from .base import Tool

_USER_AGENT = "Mozilla/5.0 (compatible; CashCode/1.0)"
_FETCH_TIMEOUT = 15.0
_FETCH_MAX_CHARS = 3000
_SEARCH_MAX_RESULTS = 10


def _strip_html(text: str) -> str:
    """Remove script/style blocks, all HTML tags, decode entities."""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class WebFetchTool(Tool):
    """抓取指定 URL 的网页内容（纯文本），返回前3000字符。"""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "获取指定 URL 的网页内容。用于查看文档、文章、GitHub issue、API 说明等。"
            "返回纯文本内容（HTML 标签已去除），最多 3000 字符。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取内容的完整 URL（包含 https://）",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, **kwargs: Any) -> str:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                timeout=_FETCH_TIMEOUT,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.TimeoutException:
            return f"获取 {url} 超时（{_FETCH_TIMEOUT}s）"
        except httpx.HTTPStatusError as e:
            return f"HTTP 错误 {e.response.status_code}：{url}"
        except Exception as e:
            return f"获取 {url} 失败：{e}"

        text = _strip_html(resp.text)
        if len(text) > _FETCH_MAX_CHARS:
            text = text[:_FETCH_MAX_CHARS] + f"\n\n[内容已截断，共 {len(text)} 字符]"
        return f"[来自 {url}]\n\n{text}"


class WebSearchTool(Tool):
    """使用 DuckDuckGo Instant Answer API 搜索网页（无需 API key）。"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "使用 DuckDuckGo 搜索网页。适用于查找信息、了解最新动态等。"
            "返回搜索摘要和相关条目。如需查看具体页面内容，再用 web_fetch。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, **kwargs: Any) -> str:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                timeout=10.0,
            ) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return f"搜索失败：{e}"

        lines: list[str] = [f"搜索：{query}\n"]

        abstract = (data.get("Abstract") or "").strip()
        if abstract:
            source = data.get("AbstractSource", "")
            source_url = data.get("AbstractURL", "")
            lines.append(f"**摘要**（{source}）：{abstract}")
            if source_url:
                lines.append(f"来源：{source_url}")
            lines.append("")

        topics = data.get("RelatedTopics") or []
        count = 0
        for topic in topics:
            if count >= _SEARCH_MAX_RESULTS:
                break
            if isinstance(topic, dict) and topic.get("Text"):
                text = topic["Text"].strip()
                url = topic.get("FirstURL", "")
                lines.append(f"- {text}")
                if url:
                    lines.append(f"  {url}")
                count += 1
            elif isinstance(topic, dict) and topic.get("Topics"):
                # nested topic group
                for sub in topic.get("Topics", []):
                    if count >= _SEARCH_MAX_RESULTS:
                        break
                    if isinstance(sub, dict) and sub.get("Text"):
                        text = sub["Text"].strip()
                        url = sub.get("FirstURL", "")
                        lines.append(f"- {text}")
                        if url:
                            lines.append(f"  {url}")
                        count += 1

        if count == 0 and not abstract:
            return (
                f"未找到「{query}」的 DuckDuckGo 摘要结果。\n"
                "建议：使用 web_fetch 访问具体搜索结果页面，"
                "例如 https://duckduckgo.com/?q=" + query.replace(" ", "+")
            )

        return "\n".join(lines)
