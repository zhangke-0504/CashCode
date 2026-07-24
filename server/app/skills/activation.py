from __future__ import annotations

import time
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from .models import SkillRecord

ACTIVATED_SKILLS_KEY = "activated_skills"


class ActivatedSkillSet:
    def __init__(self, raw: dict[str, Any], max_size: int = 12) -> None:
        self._raw = raw
        self._max_size = max(1, max_size)
        rows = sorted(
            ((name, value) for name, value in raw.items() if isinstance(name, str) and isinstance(value, dict)),
            key=lambda row: float(row[1].get("last_used", 0)),
        )
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict(rows)

    @classmethod
    def from_session(cls, metadata: dict[str, Any], max_size: int = 12) -> "ActivatedSkillSet":
        raw = metadata.setdefault(ACTIVATED_SKILLS_KEY, {})
        if not isinstance(raw, dict):
            raw = {}
            metadata[ACTIVATED_SKILLS_KEY] = raw
        return cls(raw, max_size)

    def activate(self, record: SkillRecord) -> None:
        item = {
            "description": record.manifest.description[:160],
            "version": record.manifest.version,
            "hash": record.content_hash,
            "last_used": time.time(),
        }
        self._items.pop(record.name, None)
        self._items[record.name] = item
        self._raw[record.name] = item
        while len(self._items) > self._max_size:
            name, _ = self._items.popitem(last=False)
            self._raw.pop(name, None)

    def items(self) -> list[tuple[str, dict[str, Any]]]:
        return list(reversed(self._items.items()))


@dataclass(slots=True)
class TurnSkillContext:
    activated: ActivatedSkillSet
    loaded: set[tuple[str, str]] = field(default_factory=set)


_current: ContextVar[TurnSkillContext | None] = ContextVar("skill_turn_context", default=None)


@contextmanager
def use_skill_context(context: TurnSkillContext) -> Iterator[None]:
    token = _current.set(context)
    try:
        yield
    finally:
        _current.reset(token)


def current_skill_context() -> TurnSkillContext | None:
    return _current.get()
