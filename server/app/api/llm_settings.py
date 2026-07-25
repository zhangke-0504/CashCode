"""Masked local LLM connection settings and model discovery API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from ..llm.models import LLMSettingsValidationError
from ..llm.service import LLMConnectionTestError, LLMSettingsService
from ..llm.store import LLMSettingsStorageError

router = APIRouter(prefix="/settings/llm", tags=["llm-settings"])


class OpenAICompatibleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = ""
    api_key: str | None = None
    clear_api_key: bool = False


class OllamaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = ""


class LLMSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    openai_compatible: OpenAICompatibleInput
    ollama: OllamaInput


class LLMConnectionTestRequest(LLMSettingsUpdateRequest):
    provider: Literal["openai_compatible", "ollama"]


def _service(request: Request) -> LLMSettingsService:
    value = getattr(request.app.state, "llm_settings_service", None)
    if value is None:
        raise HTTPException(status_code=503, detail="LLM settings service is unavailable")
    return value


def _require_allowed_origin(request: Request, service: LLMSettingsService) -> None:
    if not service.is_origin_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="Origin is not allowed")


def _raise_settings_error(exc: Exception) -> None:
    if isinstance(exc, LLMSettingsValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, LLMSettingsStorageError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, LLMConnectionTestError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("")
async def get_llm_settings(request: Request) -> dict:
    try:
        return _service(request).get_public()
    except Exception as exc:
        _raise_settings_error(exc)


@router.put("")
async def update_llm_settings(request: Request, body: LLMSettingsUpdateRequest) -> dict:
    service = _service(request)
    _require_allowed_origin(request, service)
    try:
        return await service.update(body.model_dump())
    except Exception as exc:
        _raise_settings_error(exc)


@router.post("/test")
async def test_llm_connection(request: Request, body: LLMConnectionTestRequest) -> dict:
    service = _service(request)
    _require_allowed_origin(request, service)
    try:
        return await service.test_connection(body.model_dump())
    except Exception as exc:
        _raise_settings_error(exc)


@router.get("/models")
async def discover_llm_models(request: Request) -> dict:
    service = _service(request)
    _require_allowed_origin(request, service)
    try:
        return await service.discover_models()
    except Exception as exc:
        _raise_settings_error(exc)
