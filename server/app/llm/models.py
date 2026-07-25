"""Typed credential-only LLM settings with secret-safe representations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, cast
from urllib.parse import urlsplit, urlunsplit

ProviderName = Literal["openai_compatible", "ollama"]
PROVIDERS = frozenset({"openai_compatible", "ollama"})
SETTINGS_VERSION = 2
DEFAULT_OPENAI_BASE_URL = "https://api.deepseek.com"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_PLACEHOLDER_KEY = "ollama-local"


class LLMSettingsError(Exception):
    """Base exception for safe, user-facing LLM settings failures."""


class LLMSettingsValidationError(LLMSettingsError):
    """Raised when settings are structurally or semantically invalid."""


class LLMNotConfiguredError(LLMSettingsError):
    """Raised when model work starts without a configured selected provider."""

    def __init__(self, provider: str | None = None) -> None:
        detail = f"（{provider}）" if provider else ""
        super().__init__(f"LLM 未配置{detail}，请打开 设置 > LLM 设置 完成连接配置。")


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise LLMSettingsValidationError(f"{field_name} must be an object")
    return value


def _text(value: Any, field_name: str, *, limit: int, allow_empty: bool = True) -> str:
    if value is None and allow_empty:
        return ""
    if not isinstance(value, str):
        raise LLMSettingsValidationError(f"{field_name} must be a string")
    result = value.strip()
    if not result and not allow_empty:
        raise LLMSettingsValidationError(f"{field_name} is required")
    if len(result) > limit:
        raise LLMSettingsValidationError(f"{field_name} is too long")
    return result


def normalize_model(value: Any) -> str:
    return _text(value, "model", limit=256, allow_empty=False)


def normalize_provider(value: Any) -> ProviderName:
    if not isinstance(value, str) or value not in PROVIDERS:
        raise LLMSettingsValidationError("provider is invalid")
    return cast(ProviderName, value)


def normalize_http_url(value: Any, field_name: str, *, allow_empty: bool = True) -> str:
    result = _text(value, field_name, limit=2048, allow_empty=allow_empty)
    if not result:
        return ""
    parsed = urlsplit(result)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise LLMSettingsValidationError(f"{field_name} must be an http or https URL")
    if parsed.username or parsed.password:
        raise LLMSettingsValidationError(f"{field_name} must not contain credentials")
    if parsed.query or parsed.fragment:
        raise LLMSettingsValidationError(f"{field_name} must not contain query or fragment")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def normalize_ollama_url(value: Any, *, allow_empty: bool = True) -> str:
    result = normalize_http_url(value, "ollama.base_url", allow_empty=allow_empty)
    if not result:
        return ""
    parsed = urlsplit(result)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProfile:
    base_url: str = ""
    api_key: str = field(default="", repr=False)

    @classmethod
    def create(cls, *, base_url: Any = "", api_key: Any = "") -> "OpenAICompatibleProfile":
        return cls(
            base_url=normalize_http_url(base_url, "openai_compatible.base_url"),
            api_key=_text(api_key, "openai_compatible.api_key", limit=16_384),
        )

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.api_key)


@dataclass(frozen=True, slots=True)
class OllamaProfile:
    base_url: str = ""

    @classmethod
    def create(cls, *, base_url: Any = "") -> "OllamaProfile":
        return cls(base_url=normalize_ollama_url(base_url))

    @property
    def ready(self) -> bool:
        return bool(self.base_url)

    @property
    def api_base_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1"


@dataclass(frozen=True, slots=True)
class RuntimeProviderConfig:
    provider: ProviderName
    base_url: str
    api_key: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LLMSettings:
    version: int = SETTINGS_VERSION
    openai_compatible: OpenAICompatibleProfile = field(default_factory=OpenAICompatibleProfile)
    ollama: OllamaProfile = field(default_factory=OllamaProfile)

    @classmethod
    def create(
        cls,
        *,
        openai_compatible: OpenAICompatibleProfile | None = None,
        ollama: OllamaProfile | None = None,
    ) -> "LLMSettings":
        return cls(
            openai_compatible=openai_compatible or OpenAICompatibleProfile(),
            ollama=ollama or OllamaProfile(),
        )

    @classmethod
    def from_storage(cls, value: Any) -> "LLMSettings":
        root = _mapping(value, "settings")
        version = root.get("version")
        if version not in {1, SETTINGS_VERSION}:
            raise LLMSettingsValidationError("unsupported LLM settings version")
        openai = _mapping(root.get("openai_compatible"), "openai_compatible")
        ollama = _mapping(root.get("ollama"), "ollama")
        return cls.create(
            openai_compatible=OpenAICompatibleProfile.create(
                base_url=openai.get("base_url", ""),
                api_key=openai.get("api_key", ""),
            ),
            ollama=OllamaProfile.create(base_url=ollama.get("base_url", "")),
        )

    @property
    def configured(self) -> bool:
        return self.openai_compatible.ready or self.ollama.ready

    def validate_persistable(self) -> None:
        if not self.configured:
            raise LLMSettingsValidationError("at least one provider connection is required")

    def runtime_config(self, provider: ProviderName) -> RuntimeProviderConfig:
        if provider == "openai_compatible" and self.openai_compatible.ready:
            return RuntimeProviderConfig(
                provider=provider,
                base_url=self.openai_compatible.base_url,
                api_key=self.openai_compatible.api_key,
            )
        if provider == "ollama" and self.ollama.ready:
            return RuntimeProviderConfig(
                provider=provider,
                base_url=self.ollama.api_base_url,
                api_key=OLLAMA_PLACEHOLDER_KEY,
            )
        raise LLMNotConfiguredError(provider)

    def runtime_configs(self) -> dict[ProviderName, RuntimeProviderConfig]:
        configs: dict[ProviderName, RuntimeProviderConfig] = {}
        for provider in ("openai_compatible", "ollama"):
            try:
                configs[provider] = self.runtime_config(provider)
            except LLMNotConfiguredError:
                pass
        return configs

    def to_storage(self) -> dict[str, Any]:
        return {
            "version": SETTINGS_VERSION,
            "openai_compatible": {
                "base_url": self.openai_compatible.base_url,
                "api_key": self.openai_compatible.api_key,
            },
            "ollama": {"base_url": self.ollama.base_url},
        }

    def to_public(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "openai_compatible": {
                "base_url": self.openai_compatible.base_url,
                "ready": self.openai_compatible.ready,
                "api_key_configured": bool(self.openai_compatible.api_key),
            },
            "ollama": {
                "base_url": self.ollama.base_url,
                "ready": self.ollama.ready,
            },
        }


def empty_public_settings() -> dict[str, Any]:
    return LLMSettings().to_public()
