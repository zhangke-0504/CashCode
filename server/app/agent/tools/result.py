"""面向模型、前端和持久化历史的工具结果投影。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    model_content: str
    public_content: str | None = None
    persisted_content: str | None = None
    ephemeral: bool = False

    @property
    def public(self) -> str:
        return self.public_content if self.public_content is not None else self.model_content

    @property
    def persisted(self) -> str:
        return self.persisted_content if self.persisted_content is not None else self.model_content

    @classmethod
    def coerce(cls, value: Any) -> "ToolExecutionResult":
        if isinstance(value, cls):
            return value
        text = str(value)
        return cls(model_content=text, public_content=text, persisted_content=text)
