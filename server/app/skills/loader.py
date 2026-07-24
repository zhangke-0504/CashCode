from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .models import DependencySet, SkillError, SkillManifest

SKILL_FILE = "SKILL.md"
META_FILE = "_meta.json"
ALLOWED_ROOT_ENTRIES = {SKILL_FILE, META_FILE, "references", "templates", "scripts", "assets"}
ALLOWED_SUPPORT_DIRS = {"references", "templates", "scripts", "assets"}
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)
MAX_SKILL_BYTES = 80_000
MAX_SUPPORT_BYTES = 200_000


def validate_name(name: str) -> str:
    value = str(name or "").strip()
    if not SKILL_NAME_RE.fullmatch(value):
        raise SkillError("invalid Skill name; use lowercase letters, numbers, dots, underscores, and hyphens")
    return value


def safe_child(root: Path, relative: str | Path) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise SkillError("path must be relative and cannot contain '..'")
    resolved_root = root.resolve()
    resolved = (resolved_root / rel).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise SkillError("path escapes the Skill root") from exc
    return resolved


def validate_support_path(path: str) -> Path:
    normalized = str(path or "").strip().replace("\\", "/")
    rel = Path(normalized)
    if rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 2:
        raise SkillError("support path must be package-relative")
    if rel.parts[0] not in ALLOWED_SUPPORT_DIRS:
        raise SkillError("support path must be under references, templates, scripts, or assets")
    return rel


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise SkillError(f"{field} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _dependencies(value: Any, field: str) -> DependencySet:
    if value is None:
        return DependencySet()
    if not isinstance(value, dict):
        raise SkillError(f"{field} must be a mapping")
    return DependencySet(
        tools=_string_list(value.get("tools"), f"{field}.tools"),
        mcp_servers=_string_list(value.get("mcp_servers"), f"{field}.mcp_servers"),
        bins=_string_list(value.get("bins"), f"{field}.bins"),
        env=_string_list(value.get("env"), f"{field}.env"),
    )


def parse_skill_text(content: str, *, expected_name: str | None = None) -> tuple[SkillManifest, str, str]:
    if not isinstance(content, str) or not content.strip():
        raise SkillError("SKILL.md cannot be empty")
    if len(content.encode("utf-8")) > MAX_SKILL_BYTES:
        raise SkillError("SKILL.md is too large")
    match = FRONTMATTER_RE.match(content)
    if not match:
        raise SkillError("SKILL.md must start with YAML frontmatter")
    try:
        raw = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(raw, dict):
        raise SkillError("frontmatter must be a mapping")
    name_raw = raw.get("name")
    description_raw = raw.get("description")
    if not isinstance(name_raw, str) or not isinstance(description_raw, str):
        raise SkillError("name and description must be strings")
    name = validate_name(name_raw)
    if expected_name is not None and name != expected_name:
        raise SkillError("frontmatter name must match the package directory")
    description = description_raw.strip()
    if not description:
        raise SkillError("description cannot be empty")
    body = content[match.end():].strip()
    if not body:
        raise SkillError("SKILL.md body cannot be empty")
    version = raw.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SkillError("version must be a positive integer")
    always = raw.get("always", False)
    if not isinstance(always, bool):
        raise SkillError("always must be a boolean")
    manifest = SkillManifest(
        name=name,
        description=description,
        version=version,
        tags=_string_list(raw.get("tags"), "tags"),
        triggers=_string_list(raw.get("triggers"), "triggers"),
        always=always,
        requires=_dependencies(raw.get("requires"), "requires"),
        optional=_dependencies(raw.get("optional"), "optional"),
    )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return manifest, body, digest


def read_skill_package(
    skill_dir: Path, *, expected_name: str | None = None
) -> tuple[SkillManifest, str, str, dict[str, Any]]:
    if not skill_dir.is_dir():
        raise SkillError("Skill package is not a directory")
    for child in skill_dir.iterdir():
        if child.name not in ALLOWED_ROOT_ENTRIES:
            raise SkillError(f"unsupported package entry: {child.name}")
        if child.is_symlink():
            try:
                child.resolve().relative_to(skill_dir.resolve())
            except ValueError as exc:
                raise SkillError(f"symlink escapes package: {child.name}") from exc
    path = safe_child(skill_dir, SKILL_FILE)
    if not path.is_file():
        raise SkillError("SKILL.md not found")
    if path.stat().st_size > MAX_SKILL_BYTES:
        raise SkillError("SKILL.md is too large")
    content = path.read_text(encoding="utf-8")
    manifest, body, digest = parse_skill_text(
        content, expected_name=expected_name or skill_dir.name
    )
    meta: dict[str, Any] = {}
    meta_path = skill_dir / META_FILE
    if meta_path.is_file():
        try:
            parsed = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                meta = parsed
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise SkillError("invalid _meta.json")
    for directory_name in ALLOWED_SUPPORT_DIRS:
        directory = skill_dir / directory_name
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise SkillError(f"{directory_name} must be a directory")
        for file in directory.rglob("*"):
            if file.is_symlink():
                try:
                    file.resolve().relative_to(skill_dir.resolve())
                except ValueError as exc:
                    raise SkillError(f"symlink escapes package: {file}") from exc
            if file.is_file() and file.stat().st_size > MAX_SUPPORT_BYTES:
                raise SkillError(f"supporting file is too large: {file.relative_to(skill_dir)}")
    return manifest, body, digest, meta
