"""Cross-platform paths for user-local LLM configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


def resolve_config_root(
    override: Path | str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    explicit = override or env.get("CASHCODE_CONFIG_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()

    platform_value = platform_name or sys.platform
    user_home = (home or Path.home()).expanduser()
    if platform_value.startswith("win"):
        parent = env.get("LOCALAPPDATA") or env.get("APPDATA")
        base = Path(parent).expanduser() if parent else user_home / "AppData" / "Local"
        return (base / "CashCode").resolve()
    if platform_value == "darwin":
        return (user_home / "Library" / "Application Support" / "CashCode").resolve()
    xdg = env.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else user_home / ".config"
    return (base / "cashcode").resolve()


def resolve_llm_settings_path(
    override: Path | str | None = None,
    **kwargs: object,
) -> Path:
    return resolve_config_root(override, **kwargs) / "settings" / "llm.json"
