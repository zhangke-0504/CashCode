from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SkillSource(str, Enum):
    BUILTIN = "builtin"
    USER = "user"
    AGENT = "agent"


class Availability(str, Enum):
    AVAILABLE = "available"
    MISSING_DEPENDENCY = "missing_dependency"
    DISABLED = "disabled"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class DependencySet:
    tools: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()
    bins: tuple[str, ...] = ()
    env: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillManifest:
    name: str
    description: str
    version: int = 1
    tags: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    always: bool = False
    requires: DependencySet = field(default_factory=DependencySet)
    optional: DependencySet = field(default_factory=DependencySet)


@dataclass(slots=True)
class SkillRecord:
    manifest: SkillManifest
    source: SkillSource
    path: Path
    content_hash: str
    enabled: bool = True
    availability: Availability = Availability.AVAILABLE
    missing: list[str] = field(default_factory=list)
    shadowed_sources: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.manifest.name

    def to_dict(self, *, include_path: bool = False) -> dict[str, Any]:
        data = {
            "name": self.name,
            "description": self.manifest.description,
            "version": self.manifest.version,
            "tags": list(self.manifest.tags),
            "triggers": list(self.manifest.triggers),
            "always": self.manifest.always,
            "source": self.source.value,
            "enabled": self.enabled,
            "availability": self.availability.value,
            "missing": list(self.missing),
            "hash": self.content_hash,
            "shadowed_sources": list(self.shadowed_sources),
            "validation_errors": list(self.validation_errors),
            "requires": asdict(self.manifest.requires),
            "optional": asdict(self.manifest.optional),
            "mutable": self.source is not SkillSource.BUILTIN,
        }
        if include_path:
            data["path"] = str(self.path)
        return data


class SkillError(ValueError):
    pass


class SkillNotFoundError(SkillError):
    pass


class SkillConflictError(SkillError):
    pass


class SkillPermissionError(SkillError):
    pass
