"""Generation-based ownership for provider clients and per-turn model leases."""

from __future__ import annotations

import asyncio
import ipaddress
import inspect
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Mapping
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI

from ..logging_config import log_event
from .models import (
    LLMNotConfiguredError,
    LLMSettings,
    ProviderName,
    RuntimeProviderConfig,
    normalize_model,
    normalize_provider,
)

ClientFactory = Callable[[RuntimeProviderConfig], Any]
LLMSelection = tuple[ProviderName, str]
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LLMSnapshot:
    client: Any
    model: str
    provider: ProviderName
    generation: int


@dataclass(slots=True)
class _Generation:
    provider: ProviderName
    client: Any
    generation: int
    leases: int = 0
    retired: bool = False
    closed: bool = False


def _uses_loopback_ollama_transport(config: RuntimeProviderConfig) -> bool:
    if config.provider != "ollama":
        return False
    hostname = urlsplit(config.base_url).hostname
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _default_client_factory(config: RuntimeProviderConfig) -> AsyncOpenAI:
    options: dict[str, Any] = {
        "api_key": config.api_key,
        "base_url": config.base_url,
        "timeout": 60.0,
        "max_retries": 1,
    }
    if _uses_loopback_ollama_transport(config):
        options["http_client"] = httpx.AsyncClient(trust_env=False)
    return AsyncOpenAI(
        **options,
    )


class LLMRuntime:
    def __init__(self, *, client_factory: ClientFactory | None = None) -> None:
        self._client_factory = client_factory or _default_client_factory
        self._lock = asyncio.Lock()
        self._active: dict[ProviderName, _Generation] = {}
        self._retired: dict[int, _Generation] = {}
        self._last_selection: LLMSelection | None = None
        self._next_generation = 1
        self._closed = False

    @classmethod
    def from_client(
        cls,
        client: Any,
        model: str,
        *,
        provider: ProviderName = "openai_compatible",
    ) -> "LLMRuntime":
        runtime = cls()
        generation = _Generation(provider=provider, client=client, generation=1)
        runtime._active[provider] = generation
        runtime._last_selection = (provider, normalize_model(model))
        runtime._next_generation = 2
        return runtime

    @property
    def configured(self) -> bool:
        return bool(self._active) and not self._closed

    @property
    def last_selection(self) -> LLMSelection | None:
        return self._last_selection

    def has_provider(self, provider: str) -> bool:
        return provider in self._active and not self._closed

    def create_client(self, config: RuntimeProviderConfig) -> Any:
        return self._client_factory(config)

    def create_clients(self, settings: LLMSettings) -> dict[ProviderName, Any]:
        return {
            provider: self._client_factory(config)
            for provider, config in settings.runtime_configs().items()
        }

    async def install(
        self,
        settings: LLMSettings,
        *,
        clients: Mapping[ProviderName, Any] | None = None,
    ) -> dict[ProviderName, int]:
        configs = settings.runtime_configs()
        candidates = dict(clients) if clients is not None else self.create_clients(settings)
        if set(candidates) != set(configs):
            log_event(
                logger,
                logging.WARNING,
                "llm.runtime.install_rejected",
                configured_providers=len(configs),
                candidate_providers=len(candidates),
                reason="provider_mismatch",
            )
            for client in candidates.values():
                await self.close_client(client)
            raise ValueError("runtime clients do not match configured providers")

        close_after: list[Any] = []
        installed: dict[ProviderName, int] = {}
        async with self._lock:
            if self._closed:
                close_after.extend(candidates.values())
            else:
                previous = self._active
                next_active: dict[ProviderName, _Generation] = {}
                for provider, client in candidates.items():
                    generation_id = self._next_generation
                    self._next_generation += 1
                    next_active[provider] = _Generation(
                        provider=provider,
                        client=client,
                        generation=generation_id,
                    )
                    installed[provider] = generation_id
                self._active = next_active
                if self._last_selection and self._last_selection[0] not in next_active:
                    self._last_selection = None
                for generation in previous.values():
                    generation.retired = True
                    if generation.leases:
                        self._retired[generation.generation] = generation
                    else:
                        generation.closed = True
                        close_after.append(generation.client)
        for value in close_after:
            await self.close_client(value)
        if self._closed:
            raise RuntimeError("LLM runtime is closed")
        log_event(
            logger,
            logging.INFO,
            "llm.runtime.installed",
            provider_count=len(installed),
            generations=",".join(str(value) for value in sorted(installed.values())),
            retired_clients=len(close_after),
        )
        return installed

    @asynccontextmanager
    async def acquire(self, provider: str, model: str) -> AsyncIterator[LLMSnapshot]:
        normalized_provider = normalize_provider(provider)
        normalized_model = normalize_model(model)
        async with self._lock:
            generation = self._active.get(normalized_provider)
            if self._closed or generation is None:
                raise LLMNotConfiguredError(normalized_provider)
            generation.leases += 1
            self._last_selection = (normalized_provider, normalized_model)
            snapshot = LLMSnapshot(
                client=generation.client,
                model=normalized_model,
                provider=normalized_provider,
                generation=generation.generation,
            )
        log_event(
            logger,
            logging.DEBUG,
            "llm.runtime.lease_acquired",
            provider=normalized_provider,
            model=normalized_model,
            generation=generation.generation,
            active_leases=generation.leases,
        )
        try:
            yield snapshot
        finally:
            await self._release(generation)

    @asynccontextmanager
    async def acquire_last(self) -> AsyncIterator[LLMSnapshot]:
        selection = self._last_selection
        if selection is None:
            raise LLMNotConfiguredError()
        async with self.acquire(*selection) as snapshot:
            yield snapshot

    async def _release(self, generation: _Generation) -> None:
        client: Any | None = None
        async with self._lock:
            generation.leases = max(0, generation.leases - 1)
            if generation.retired and generation.leases == 0 and not generation.closed:
                generation.closed = True
                self._retired.pop(generation.generation, None)
                client = generation.client
        if client is not None:
            await self.close_client(client)

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            generations = [
                generation
                for generation in [*self._active.values(), *self._retired.values()]
                if not generation.closed
            ]
            self._active.clear()
            self._retired.clear()
            self._last_selection = None
            for generation in generations:
                generation.closed = True
        for generation in generations:
            await self.close_client(generation.client)
        log_event(
            logger,
            logging.INFO,
            "llm.runtime.closed",
            client_count=len(generations),
        )

    @staticmethod
    async def close_client(client: Any) -> None:
        close = getattr(client, "close", None) or getattr(client, "aclose", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result
