"""Application service for credentials, model discovery, and connection probes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

from .models import (
    LLMSettings,
    LLMSettingsError,
    LLMSettingsValidationError,
    OllamaProfile,
    OpenAICompatibleProfile,
    ProviderName,
    RuntimeProviderConfig,
    empty_public_settings,
    normalize_provider,
)
from .runtime import LLMRuntime
from .store import LLMSettingsStorageError, LLMSettingsStore

logger = logging.getLogger(__name__)


class LLMConnectionTestError(LLMSettingsError):
    """Sanitized provider probe failure."""


class LLMSettingsService:
    def __init__(
        self,
        store: LLMSettingsStore,
        runtime: LLMRuntime,
        *,
        allowed_origins: set[str] | None = None,
        probe_timeout: float = 15.0,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.allowed_origins = allowed_origins or set()
        self.probe_timeout = probe_timeout
        self._current: LLMSettings | None = None
        self._load_error: LLMSettingsError | None = None
        self._lock = asyncio.Lock()

    async def initialize(self, environ: Mapping[str, str] | None = None) -> None:
        async with self._lock:
            try:
                settings, migrated = self.store.load_or_migrate(environ)
                self._load_error = None
            except LLMSettingsError as exc:
                self._load_error = exc
                self._current = None
                logger.error("LLM settings could not be loaded: %s", exc)
                return
            if settings is None:
                self._current = None
                return
            await self.runtime.install(settings)
            self._current = settings
            if migrated:
                logger.info("Migrated legacy DeepSeek credentials to the local settings store")

    def get_public(self) -> dict[str, Any]:
        if self._load_error is not None:
            raise LLMSettingsStorageError(
                "the LLM settings file is invalid or unreadable"
            ) from self._load_error
        return self._current.to_public() if self._current else empty_public_settings()

    def is_origin_allowed(self, origin: str | None) -> bool:
        return not origin or origin in self.allowed_origins

    async def update(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        async with self._lock:
            settings = self._build_candidate(payload)
            settings.validate_persistable()
            candidates = self.runtime.create_clients(settings)
            try:
                self.store.save(settings)
            except Exception:
                for client in candidates.values():
                    await self.runtime.close_client(client)
                raise
            await self.runtime.install(settings, clients=candidates)
            self._current = settings
            self._load_error = None
            return settings.to_public()

    async def test_connection(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        provider = normalize_provider(payload.get("provider"))
        settings = self._build_candidate(payload)
        config = settings.runtime_config(provider)
        candidate = self.runtime.create_client(config)
        try:
            models = await self._list_models(candidate)
        except Exception as exc:
            logger.warning("LLM connection test failed (%s)", type(exc).__name__)
            raise LLMConnectionTestError(self._connection_error_message(exc)) from exc
        finally:
            await self.runtime.close_client(candidate)
        return {
            "success": True,
            "provider": provider,
            "model_count": len(models),
            "message": f"连接成功，发现 {len(models)} 个模型",
        }

    async def discover_models(self) -> dict[str, Any]:
        if self._load_error is not None:
            self.get_public()
        settings = self._current
        configs = settings.runtime_configs() if settings else {}

        async def discover(provider: ProviderName, config: RuntimeProviderConfig) -> tuple[ProviderName, list[str], str | None]:
            candidate = self.runtime.create_client(config)
            try:
                return provider, await self._list_models(candidate), None
            except Exception as exc:
                logger.warning("LLM model discovery failed for %s (%s)", provider, type(exc).__name__)
                return provider, [], self._connection_error_message(exc)
            finally:
                await self.runtime.close_client(candidate)

        results = await asyncio.gather(*(
            discover(provider, config) for provider, config in configs.items()
        ))
        models: list[dict[str, str]] = []
        providers: dict[str, dict[str, Any]] = {
            provider: {
                "ready": provider in configs,
                "error": None,
            }
            for provider in ("openai_compatible", "ollama")
        }
        for provider, ids, error in results:
            providers[provider]["error"] = error
            models.extend({"provider": provider, "id": model_id} for model_id in ids)
        return {"models": models, "providers": providers}

    async def _list_models(self, client: Any) -> list[str]:
        response = await asyncio.wait_for(client.models.list(), timeout=self.probe_timeout)
        values: list[str] = []
        seen: set[str] = set()
        for item in getattr(response, "data", [])[:500]:
            model_id = getattr(item, "id", None)
            if isinstance(model_id, str):
                model_id = model_id.strip()
                if model_id and len(model_id) <= 256 and model_id not in seen:
                    seen.add(model_id)
                    values.append(model_id)
        return sorted(values, key=str.casefold)

    def _build_candidate(self, payload: Mapping[str, Any]) -> LLMSettings:
        openai_data = payload.get("openai_compatible") or {}
        ollama_data = payload.get("ollama") or {}
        if not isinstance(openai_data, Mapping) or not isinstance(ollama_data, Mapping):
            raise LLMSettingsValidationError("provider profiles must be objects")

        incoming_key = openai_data.get("api_key")
        clear_key = bool(openai_data.get("clear_api_key", False))
        if clear_key and isinstance(incoming_key, str) and incoming_key.strip():
            raise LLMSettingsValidationError(
                "api_key and clear_api_key cannot be submitted together"
            )
        current_key = self._current.openai_compatible.api_key if self._current else ""
        if clear_key:
            effective_key = ""
        elif isinstance(incoming_key, str) and incoming_key.strip():
            effective_key = incoming_key
        else:
            effective_key = current_key

        return LLMSettings.create(
            openai_compatible=OpenAICompatibleProfile.create(
                base_url=openai_data.get("base_url", ""),
                api_key=effective_key,
            ),
            ollama=OllamaProfile.create(base_url=ollama_data.get("base_url", "")),
        )

    @staticmethod
    def _connection_error_message(exc: Exception) -> str:
        name = type(exc).__name__.lower()
        value = str(exc).lower()
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeout" in name:
            return "连接超时，请检查服务地址和网络。"
        if "authentication" in name or "permission" in name or "401" in value or "403" in value:
            return "认证失败，请检查 API Key。"
        if "connection" in name or "connect" in value:
            return "无法连接到模型服务，请检查服务地址。"
        if "ratelimit" in name or "429" in value:
            return "模型服务繁忙，请稍后重试。"
        return "连接失败，请检查提供方配置。"
