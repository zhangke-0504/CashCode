from __future__ import annotations

import json
from typing import Any

from ..agent.tools.base import Tool
from .catalog import sanitize_skill_error
from .loader import parse_skill_text, validate_name
from .models import (
    SkillConflictError,
    SkillError,
    SkillPermissionError,
    SkillPublicationError,
    SkillSource,
)
from .store import SkillStore

MAX_AUTHORING_REASON_CHARS = 500
MAX_AUTHORING_SUPPORT_FILES = 64
MAX_AUTHORING_ERROR_CHARS = 240


class AgentSkillManageTool(Tool):
    """通过共享 SkillStore 创建由 Agent 持有的 Skill。"""

    def __init__(self, store: SkillStore) -> None:
        self.store = store

    @property
    def name(self) -> str:
        return "agent_skill_manage"

    @property
    def description(self) -> str:
        return (
            "Create a validated Agent-owned Skill for an explicit user authoring request. "
            "The name argument and frontmatter name must match "
            "^[a-z0-9][a-z0-9._-]{0,63}$. Put any localized label in display_name "
            "inside SKILL.md. On validation_error, correct the content and retry this tool; "
            "never fall back to direct files, shell, or HTTP. Treat success=true as the "
            "only creation confirmation."
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create"],
                    "description": "当前只支持 create。",
                },
                "name": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9._-]{0,63}$",
                    "description": "与目录和 frontmatter 一致的 canonical slug。",
                },
                "content": {
                    "type": "string",
                    "description": "包含 YAML frontmatter 与正文的完整 SKILL.md。",
                },
                "support_files": {
                    "type": "object",
                    "maxProperties": MAX_AUTHORING_SUPPORT_FILES,
                    "additionalProperties": {"type": "string"},
                    "description": "可选的包内文本支持文件。",
                },
                "reason": {
                    "type": "string",
                    "maxLength": MAX_AUTHORING_REASON_CHARS,
                    "description": "简短的创建原因，用于审计。",
                },
            },
            "required": ["action", "name", "content"],
            "additionalProperties": False,
        }

    def _error(self, code: str, detail: str) -> str:
        roots = self.store.catalog.roots.values()
        return json.dumps(
            {
                "success": False,
                "action": "create",
                "code": code,
                "detail": sanitize_skill_error(
                    detail, roots, limit=MAX_AUTHORING_ERROR_CHARS
                ),
            },
            ensure_ascii=False,
        )

    async def execute(
        self,
        action: str = "",
        name: str = "",
        content: str = "",
        support_files: dict[str, str] | None = None,
        reason: str = "",
        **_: Any,
    ) -> str:
        if action != "create":
            return self._error("unsupported_action", "action must be create")
        if not isinstance(reason, str) or len(reason.strip()) > MAX_AUTHORING_REASON_CHARS:
            return self._error(
                "validation_error",
                f"reason must be at most {MAX_AUTHORING_REASON_CHARS} characters",
            )
        if support_files is not None and (
            not isinstance(support_files, dict)
            or len(support_files) > MAX_AUTHORING_SUPPORT_FILES
            or any(
                not isinstance(path, str) or not isinstance(value, str)
                for path, value in support_files.items()
            )
        ):
            return self._error(
                "validation_error",
                f"support_files must contain at most {MAX_AUTHORING_SUPPORT_FILES} text files",
            )
        try:
            canonical_name = validate_name(name)
            _, _, expected_hash = parse_skill_text(
                content, expected_name=canonical_name
            )
            self.store.create(
                canonical_name,
                content,
                source=SkillSource.AGENT,
                support_files=support_files,
                enabled=True,
                audit_reason=reason.strip() or None,
            )
            record = self.store.catalog.get(canonical_name)
            if (
                record is None
                or record.source is not SkillSource.AGENT
                or record.content_hash != expected_hash
            ):
                raise SkillPublicationError(
                    "created Skill was not published to the live catalog"
                )
            return json.dumps(
                {
                    "success": True,
                    "action": "create",
                    "name": record.name,
                    "display_name": record.display_name,
                    "hash": record.content_hash,
                    "source": record.source.value,
                    "enabled": record.enabled,
                },
                ensure_ascii=False,
            )
        except SkillConflictError as exc:
            return self._error("conflict", str(exc))
        except SkillPermissionError as exc:
            return self._error("permission_denied", str(exc))
        except SkillPublicationError as exc:
            return self._error("publication_failed", str(exc))
        except SkillError as exc:
            return self._error("validation_error", str(exc))
        except PermissionError as exc:
            return self._error("permission_denied", str(exc))
        except Exception:
            return self._error(
                "publication_failed", "Skill publication failed unexpectedly"
            )
