"""校验聊天消息中显式选择的 Skill 与 MCP 元数据。"""

from __future__ import annotations

import re
from typing import Any

from .llm.models import PROVIDERS

MAX_CAPABILITY_SELECTIONS = 8
MAX_SELECTION_LABEL = 100
MAX_MODEL_ID = 256

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MCP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SelectionValidationError(ValueError):
    """选择元数据不满足数量、标识或显示字段约束。"""


def _clean_label(value: Any, field: str) -> str | None:
    """清理可选显示名称，并去除空字符及首尾空白。"""

    if value is None:
        return None
    if not isinstance(value, str):
        raise SelectionValidationError(f"{field} must be a string")
    label = value.replace("\x00", "").strip()
    if not label:
        return None
    if len(label) > MAX_SELECTION_LABEL:
        raise SelectionValidationError(
            f"{field} must be at most {MAX_SELECTION_LABEL} characters"
        )
    return label


def _sanitize_rows(
    raw: Any,
    *,
    field: str,
    identity_field: str,
    pattern: re.Pattern[str],
) -> list[dict[str, str]]:
    """按指定标识字段校验、清理并去重一类选择记录。"""

    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SelectionValidationError(f"{field} must be a list")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise SelectionValidationError(f"{field} entries must be objects")
        identity = item.get(identity_field)
        if not isinstance(identity, str) or not pattern.fullmatch(identity.strip()):
            raise SelectionValidationError(
                f"{field}.{identity_field} is invalid"
            )
        identity = identity.strip()
        if identity in seen:
            continue
        seen.add(identity)
        row = {identity_field: identity}
        label = _clean_label(item.get("label"), f"{field}.label")
        if label:
            row["label"] = label
        rows.append(row)
    return rows


def _sanitize_llm_selection(raw: Any, *, required: bool) -> dict[str, str] | None:
    if raw is None:
        if required:
            raise SelectionValidationError("llm selection is required")
        return None
    if not isinstance(raw, dict):
        raise SelectionValidationError("llm must be an object")
    provider = raw.get("provider")
    model = raw.get("model")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise SelectionValidationError("llm.provider is invalid")
    if not isinstance(model, str):
        raise SelectionValidationError("llm.model must be a string")
    model = model.strip()
    if not model or len(model) > MAX_MODEL_ID or "\x00" in model:
        raise SelectionValidationError("llm.model is invalid")
    return {"provider": provider, "model": model}


def sanitize_selection_metadata(
    raw: Any, *, require_llm: bool = False
) -> dict[str, Any]:
    """把不可信 WebSocket metadata 投影为有界的规范选择结构。"""

    if raw is None:
        if require_llm:
            raise SelectionValidationError("llm selection is required")
        return {}
    if not isinstance(raw, dict):
        raise SelectionValidationError("metadata must be an object")
    skills_raw = raw.get("mentioned_skills")
    mcp_raw = raw.get("selected_mcp_connectors")
    llm = _sanitize_llm_selection(raw.get("llm"), required=require_llm)
    # 在去重前限制原始条目数，防止重复记录绕过请求体上限。
    raw_count = (
        len(skills_raw) if isinstance(skills_raw, list) else 0
    ) + (len(mcp_raw) if isinstance(mcp_raw, list) else 0)
    if raw_count > MAX_CAPABILITY_SELECTIONS:
        raise SelectionValidationError(
            f"at most {MAX_CAPABILITY_SELECTIONS} Skill/MCP selections are allowed"
        )
    skills = _sanitize_rows(
        skills_raw,
        field="mentioned_skills",
        identity_field="name",
        pattern=_SKILL_NAME_RE,
    )
    connectors = _sanitize_rows(
        mcp_raw,
        field="selected_mcp_connectors",
        identity_field="server",
        pattern=_MCP_NAME_RE,
    )
    result: dict[str, Any] = {}
    if skills:
        result["mentioned_skills"] = skills
    if connectors:
        result["selected_mcp_connectors"] = connectors
    if llm:
        result["llm"] = llm
    return result


def safe_persisted_selections(raw: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """为历史持久化生成安全收据；旧数据异常时回退为空选择。"""

    try:
        return sanitize_selection_metadata(
            {
                "mentioned_skills": raw.get("mentioned_skills"),
                "selected_mcp_connectors": raw.get("selected_mcp_connectors"),
            }
        )
    except SelectionValidationError:
        return {}
