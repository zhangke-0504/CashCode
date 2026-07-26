from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.llm_settings import router
from app.llm.runtime import LLMRuntime
from app.llm.service import LLMSettingsService
from app.llm.store import LLMSettingsStorageError, LLMSettingsStore

ALLOWED_ORIGIN = "http://127.0.0.1:5173"


class FakeClient:
    def __init__(self, error: Exception | None = None, model_ids=None):
        self.error = error
        self.model_ids = list(model_ids or ["model-a", "model-b"])
        self.calls = []
        self.closed = False
        self.models = SimpleNamespace(list=self.list_models)

    async def list_models(self):
        self.calls.append("models.list")
        if self.error:
            raise self.error
        return SimpleNamespace(data=[SimpleNamespace(id=value) for value in self.model_ids])

    async def close(self):
        self.closed = True


def api_payload(*, key="fixture-key", clear=False, ollama=True):
    return {
        "openai_compatible": {
            "base_url": "https://provider.example/v1",
            "api_key": key,
            "clear_api_key": clear,
        },
        "ollama": {
            "base_url": "http://127.0.0.1:11434" if ollama else "",
        },
    }


def connection_payload(provider="openai_compatible", **kwargs):
    return {"provider": provider, **api_payload(**kwargs)}


def make_client(tmp_path, *, errors=None):
    clients = []
    queued_errors = list(errors or [])

    def factory(_config):
        client = FakeClient(queued_errors.pop(0) if queued_errors else None)
        clients.append(client)
        return client

    runtime = LLMRuntime(client_factory=factory)
    store = LLMSettingsStore(tmp_path / "config" / "settings" / "llm.json")
    service = LLMSettingsService(
        store,
        runtime,
        allowed_origins={ALLOWED_ORIGIN},
        probe_timeout=0.5,
    )
    app = FastAPI()
    app.state.llm_settings_service = service
    app.include_router(router, prefix="/api")
    return TestClient(app), service, runtime, store, clients


def test_api_first_save_masks_key_and_blank_update_retains_it(tmp_path):
    client, _service, _runtime, store, _clients = make_client(tmp_path)
    assert client.get("/api/settings/llm").json()["configured"] is False

    saved = client.put(
        "/api/settings/llm", headers={"Origin": ALLOWED_ORIGIN}, json=api_payload()
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["openai_compatible"]["api_key_configured"] is True
    assert body["openai_compatible"]["ready"] is True
    assert "api_key" not in body["openai_compatible"]
    assert "active_provider" not in body
    assert "model" not in str(body)
    assert store.path.exists()

    retained_payload = api_payload(key="")
    retained_payload["openai_compatible"]["base_url"] = "https://changed.example/v1"
    retained = client.put(
        "/api/settings/llm", headers={"Origin": ALLOWED_ORIGIN}, json=retained_payload
    )
    assert retained.status_code == 200
    assert retained.json()["openai_compatible"]["base_url"] == "https://changed.example/v1"
    assert retained.json()["openai_compatible"]["api_key_configured"] is True
    assert bool(store.load().openai_compatible.api_key) is True  # type: ignore[union-attr]


def test_api_can_clear_key_when_ollama_remains_ready(tmp_path):
    client, _service, _runtime, store, _clients = make_client(tmp_path)
    client.put("/api/settings/llm", headers={"Origin": ALLOWED_ORIGIN}, json=api_payload())

    cleared = client.put(
        "/api/settings/llm",
        headers={"Origin": ALLOWED_ORIGIN},
        json=api_payload(key="", clear=True),
    )
    assert cleared.status_code == 200
    assert cleared.json()["openai_compatible"]["ready"] is False
    assert cleared.json()["openai_compatible"]["api_key_configured"] is False
    assert cleared.json()["ollama"]["ready"] is True
    assert not store.load().openai_compatible.api_key  # type: ignore[union-attr]


def test_connection_probe_lists_models_without_persisting_draft(tmp_path):
    client, _service, _runtime, store, clients = make_client(tmp_path)
    client.put("/api/settings/llm", headers={"Origin": ALLOWED_ORIGIN}, json=api_payload())
    original = store.path.read_bytes()

    response = client.post(
        "/api/settings/llm/test",
        headers={"Origin": ALLOWED_ORIGIN},
        json=connection_payload("ollama", key=""),
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "ollama"
    assert response.json()["model_count"] == 2
    assert store.path.read_bytes() == original
    assert clients[-1].closed is True
    assert clients[-1].calls == ["models.list"]


def test_model_discovery_returns_models_and_provider_status(tmp_path):
    client, _service, _runtime, _store, _clients = make_client(tmp_path)
    client.put("/api/settings/llm", headers={"Origin": ALLOWED_ORIGIN}, json=api_payload())

    response = client.get(
        "/api/settings/llm/models", headers={"Origin": ALLOWED_ORIGIN}
    )
    assert response.status_code == 200
    body = response.json()
    assert {item["provider"] for item in body["models"]} == {"openai_compatible", "ollama"}
    assert body["providers"]["openai_compatible"] == {"ready": True, "error": None}


def test_probe_failure_is_sanitized_and_untrusted_origin_is_rejected(tmp_path):
    client, _service, _runtime, _store, clients = make_client(
        tmp_path, errors=[RuntimeError("api_key=fixture-key must never escape")]
    )
    payload = connection_payload()

    blocked = client.post(
        "/api/settings/llm/test",
        headers={"Origin": "https://untrusted.example"},
        json=payload,
    )
    assert blocked.status_code == 403
    assert clients == []

    failed = client.post(
        "/api/settings/llm/test", headers={"Origin": ALLOWED_ORIGIN}, json=payload
    )
    assert failed.status_code == 400
    assert "fixture-key" not in failed.text
    assert clients[-1].closed is True


def test_untrusted_origin_cannot_discover_models(tmp_path):
    client, _service, _runtime, _store, clients = make_client(tmp_path)
    blocked = client.get(
        "/api/settings/llm/models", headers={"Origin": "https://untrusted.example"}
    )
    assert blocked.status_code == 403
    assert clients == []


@pytest.mark.asyncio
async def test_failed_write_preserves_runtime_and_public_state(tmp_path, monkeypatch):
    _client, service, runtime, _store, _clients = make_client(tmp_path)
    await service.update(api_payload())

    def fail_save(_settings):
        raise LLMSettingsStorageError("fixture write failure")

    monkeypatch.setattr(service.store, "save", fail_save)
    changed = api_payload()
    changed["openai_compatible"]["base_url"] = "https://changed.example"
    with pytest.raises(LLMSettingsStorageError):
        await service.update(changed)

    assert service.get_public()["openai_compatible"]["base_url"] == "https://provider.example/v1"
    async with runtime.acquire("openai_compatible", "model-a") as snapshot:
        assert snapshot.provider == "openai_compatible"
