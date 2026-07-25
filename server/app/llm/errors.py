"""Shared classification for recoverable provider failures."""

from __future__ import annotations

import asyncio

import httpx
from openai import APIConnectionError, APITimeoutError


_EXPECTED_PROVIDER_ERRORS = (
    asyncio.TimeoutError,
    TimeoutError,
    APITimeoutError,
    APIConnectionError,
    httpx.TimeoutException,
    httpx.TransportError,
)


def is_expected_provider_failure(exc: BaseException) -> bool:
    """Return whether an exception represents an ordinary provider outage."""

    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, _EXPECTED_PROVIDER_ERRORS):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False
