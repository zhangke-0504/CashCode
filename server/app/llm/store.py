"""Atomic persistence and one-time migration for LLM settings."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Mapping

from .models import (
    DEFAULT_OPENAI_BASE_URL,
    LLMSettings,
    LLMSettingsError,
    OpenAICompatibleProfile,
)


class LLMSettingsStorageError(LLMSettingsError):
    """Raised for sanitized settings-file I/O or decoding failures."""


class LLMSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def load(self) -> LLMSettings | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return LLMSettings.from_storage(raw)
        except LLMSettingsError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMSettingsStorageError("unable to read the LLM settings file") from exc

    def load_or_migrate(self, environ: Mapping[str, str] | None = None) -> tuple[LLMSettings | None, bool]:
        if self.path.exists():
            return self.load(), False
        env = os.environ if environ is None else environ
        api_key = env.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None, False
        settings = LLMSettings.create(openai_compatible=OpenAICompatibleProfile.create(
            base_url=env.get("DEEPSEEK_API_BASE", DEFAULT_OPENAI_BASE_URL),
            api_key=api_key,
        ))
        self.save(settings)
        return settings, True

    def save(self, settings: LLMSettings) -> None:
        settings.validate_persistable()
        payload = json.dumps(
            settings.to_storage(), ensure_ascii=False, indent=2
        ) + "\n"
        temp = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._restrict_permissions(self.path.parent, 0o700)
            descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._restrict_permissions(temp, 0o600)
            os.replace(temp, self.path)
            self._restrict_permissions(self.path, 0o600)
        except OSError as exc:
            raise LLMSettingsStorageError("unable to save the LLM settings file") from exc
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        try:
            os.chmod(path, mode)
        except OSError:
            # Windows and managed filesystems may not expose POSIX modes.
            pass
