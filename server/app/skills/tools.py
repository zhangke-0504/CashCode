from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..agent.tools.base import Tool
from ..agent.tools.registry import ToolRegistry
from ..agent.tools.result import ToolExecutionResult
from ..agent.tools.tool_search import get_activated_set
from .activation import current_skill_context
from .catalog import SkillCatalog
from .loader import MAX_SUPPORT_BYTES, safe_child, validate_support_path
from .models import Availability, SkillError

PrepareCallback = Callable[[str], Awaitable[bool]]
EXPLICIT_RE = re.compile(r"^@([a-z0-9][a-z0-9._-]{0,63})(?:\s+|$)")


def parse_explicit_skill(content: str) -> tuple[str | None, str]:
    match = EXPLICIT_RE.match(content)
    if not match:
        return None, content
    return match.group(1), content[match.end():].lstrip()


class SkillSearchTool(Tool):
    def __init__(self, catalog: SkillCatalog) -> None:
        self.catalog = catalog

    @property
    def name(self) -> str:
        return "skill_search"

    @property
    def description(self) -> str:
        return (
            "Search installed local Skills by natural-language intent. Returns only "
            "bounded metadata. Call skill_load with an exact name to read instructions."
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Workflow or capability to find"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
            "required": ["query"],
        }

    async def execute(self, query: str = "", limit: int = 8, **_: Any) -> str:
        if not query.strip():
            return json.dumps({"skills": [], "error": "query is required"})
        rows = []
        for score, record in self.catalog.search(query, limit=min(int(limit), 20)):
            item = record.to_dict()
            item["score"] = round(score, 4)
            item.pop("requires", None)
            item.pop("optional", None)
            rows.append(item)
        return json.dumps({"query": query, "skills": rows}, ensure_ascii=False)


class SkillLoadTool(Tool):
    def __init__(
        self,
        catalog: SkillCatalog,
        registry: ToolRegistry,
        prepare_mcp: PrepareCallback,
    ) -> None:
        self.catalog = catalog
        self.registry = registry
        self.prepare_mcp = prepare_mcp

    @property
    def name(self) -> str:
        return "skill_load"

    @property
    def description(self) -> str:
        return (
            "Load one installed Skill by exact name after skill_search. Full instructions "
            "are available only in the current turn and must be reloaded in later turns."
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Exact installed Skill name"}},
            "required": ["name"],
        }

    async def execute(self, name: str = "", **_: Any) -> ToolExecutionResult:
        exact = (name or "").strip()
        record = self.catalog.get(exact)
        if record is None:
            suggestions = [row.name for _, row in self.catalog.search(exact, 3)]
            return ToolExecutionResult.coerce(json.dumps({
                "error": "skill_not_found", "name": exact, "suggestions": suggestions
            }))
        if not record.enabled or record.availability is Availability.DISABLED:
            return ToolExecutionResult.coerce(json.dumps({"error": "skill_disabled", "name": exact}))
        if record.availability is Availability.MISSING_DEPENDENCY:
            # 已配置的必需 MCP 会在下方准备；其他依赖缺失时该 Skill 不可用。
            non_mcp = [item for item in record.missing if not item.startswith("mcp:")]
            if non_mcp:
                return ToolExecutionResult.coerce(json.dumps({
                    "error": "missing_dependency", "name": exact, "missing": non_mcp
                }))

        for tool_name in record.manifest.requires.tools:
            if not tool_name.startswith("mcp_") and not self.registry.has(tool_name):
                return ToolExecutionResult.coerce(json.dumps({
                    "error": "missing_dependency", "name": exact, "missing": [f"tool:{tool_name}"]
                }))
        for server_name in record.manifest.requires.mcp_servers:
            if not await self.prepare_mcp(server_name):
                return ToolExecutionResult.coerce(json.dumps({
                    "error": "mcp_prepare_failed", "name": exact, "server": server_name
                }))

        active_tools = get_activated_set()
        if active_tools is not None:
            declared = set(record.manifest.requires.tools)
            for server_name in record.manifest.requires.mcp_servers:
                prefix = f"mcp_{server_name}_"
                declared.update(tool for tool in self.registry.tool_names if tool.startswith(prefix))
            for tool_name in declared:
                if self.registry.has(tool_name) and tool_name.startswith("mcp_"):
                    active_tools.activate(tool_name)

        try:
            current_record, body = self.catalog.load_body(exact)
        except SkillError as exc:
            return ToolExecutionResult.coerce(json.dumps({"error": "invalid_skill", "detail": str(exc)}))

        context = current_skill_context()
        key = (current_record.name, current_record.content_hash)
        receipt = (
            f"[Skill loaded: {current_record.name}@v{current_record.manifest.version} "
            f"sha256:{current_record.content_hash}]"
        )
        if context is not None and key in context.loaded:
            return ToolExecutionResult(
                model_content=f"{receipt} already_loaded=true",
                public_content=f"Skill already loaded: {current_record.name}",
                persisted_content=f"{receipt} already_loaded=true",
                ephemeral=True,
            )
        if context is not None:
            context.loaded.add(key)
            context.activated.activate(current_record)
        optional = {
            "tools": list(current_record.manifest.optional.tools),
            "mcp_servers": list(current_record.manifest.optional.mcp_servers),
        }
        model_content = (
            f"{receipt}\n"
            f"Skill package root: {current_record.path}\n"
            f"Optional dependencies (not started): {json.dumps(optional)}\n\n"
            f"{body}"
        )
        return ToolExecutionResult(
            model_content=model_content,
            public_content=f"Loaded Skill: {current_record.name}",
            persisted_content=receipt,
            ephemeral=True,
        )


class SkillReadResourceTool(Tool):
    def __init__(self, catalog: SkillCatalog) -> None:
        self.catalog = catalog

    @property
    def name(self) -> str:
        return "skill_read_resource"

    @property
    def description(self) -> str:
        return "Read a validated supporting file from a Skill already loaded in this turn."

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "path": {"type": "string", "description": "Path under references/templates/scripts/assets"},
            },
            "required": ["name", "path"],
        }

    async def execute(self, name: str, path: str, **_: Any) -> ToolExecutionResult:
        record = self.catalog.get(name)
        context = current_skill_context()
        if record is None or context is None or (name, record.content_hash) not in context.loaded:
            return ToolExecutionResult.coerce("Error: load the Skill before reading its resources")
        try:
            relative = validate_support_path(path)
            target = safe_child(record.path, relative)
        except SkillError as exc:
            return ToolExecutionResult.coerce(f"Error: {exc}")
        if not target.is_file() or target.stat().st_size > MAX_SUPPORT_BYTES:
            return ToolExecutionResult.coerce("Error: resource not found or too large")
        content = target.read_text(encoding="utf-8")
        receipt = f"[Skill resource read: {name}/{relative.as_posix()}]"
        return ToolExecutionResult(
            model_content=f"{receipt}\n\n{content}",
            public_content=receipt,
            persisted_content=receipt,
            ephemeral=True,
        )


def render_activated_skill_summary(catalog: SkillCatalog, activated: Any, max_chars: int = 1800) -> str:
    lines = [
        "## Recently activated Skills",
        "These are hints only. Call skill_load with the exact name before relying on full instructions.",
    ]
    for name, item in activated.items():
        record = catalog.get(name)
        if record is None or not record.enabled:
            continue
        stale = record.content_hash != item.get("hash")
        suffix = " (stale; reload required)" if stale else ""
        line = f"- {name}: {str(item.get('description', ''))[:160]}{suffix}"
        if sum(len(row) + 1 for row in lines) + len(line) > max_chars:
            break
        lines.append(line)
    return "\n".join(lines) if len(lines) > 2 else ""
