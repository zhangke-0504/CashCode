from __future__ import annotations

import json
import os
import stat

import pytest

from app.llm.models import (
    LLMSettings,
    LLMSettingsValidationError,
    OllamaProfile,
    OpenAICompatibleProfile,
)
from app.llm.paths import resolve_llm_settings_path
from app.llm.store import LLMSettingsStorageError, LLMSettingsStore


def api_settings(key: str = "fixture-key") -> LLMSettings:
    return LLMSettings.create(
        openai_compatible=OpenAICompatibleProfile.create(
            base_url="https://provider.example/v1/",
            api_key=key,
        ),
        ollama=OllamaProfile.create(base_url="http://127.0.0.1:11434/v1"),
    )


def test_profiles_normalize_urls_and_hide_secrets_from_repr():
    settings = api_settings()

    assert settings.openai_compatible.base_url == "https://provider.example/v1"
    assert settings.ollama.api_base_url == "http://127.0.0.1:11434/v1"
    assert "fixture-key" not in repr(settings)
    assert settings.to_public()["openai_compatible"] == {
        "base_url": "https://provider.example/v1",
        "ready": True,
        "api_key_configured": True,
    }
    assert "active_provider" not in settings.to_public()
    assert "model" not in str(settings.to_storage())


def test_at_least_one_connection_must_be_ready_before_persistence(tmp_path):
    store = LLMSettingsStore(tmp_path / "settings" / "llm.json")
    with pytest.raises(LLMSettingsValidationError):
        store.save(LLMSettings())
    assert not store.path.exists()


def test_default_windows_path_is_user_local_and_override_is_injectable(tmp_path):
    path = resolve_llm_settings_path(
        environ={"LOCALAPPDATA": str(tmp_path / "local")},
        platform_name="win32",
        home=tmp_path / "home",
    )
    override = resolve_llm_settings_path(tmp_path / "override")

    assert path == (tmp_path / "local" / "CashCode" / "settings" / "llm.json").resolve()
    assert override == (tmp_path / "override" / "settings" / "llm.json").resolve()


def test_first_valid_save_creates_and_loads_versioned_file(tmp_path):
    path = tmp_path / "config" / "settings" / "llm.json"
    store = LLMSettingsStore(path)
    assert store.load() is None

    store.save(api_settings())
    loaded = store.load()

    assert loaded == api_settings()
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_version_one_file_preserves_credentials_and_discards_selection(tmp_path):
    path = tmp_path / "settings" / "llm.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "version": 1,
        "active_provider": "openai_compatible",
        "openai_compatible": {
            "base_url": "https://legacy.example",
            "model": "legacy-model",
            "api_key": "legacy-fixture",
        },
        "ollama": {"base_url": "http://127.0.0.1:11434", "model": "qwen3"},
    }), encoding="utf-8")

    store = LLMSettingsStore(path)
    settings = store.load()
    assert settings is not None
    assert settings.openai_compatible.api_key == "legacy-fixture"
    assert settings.openai_compatible.base_url == "https://legacy.example"
    assert not hasattr(settings.openai_compatible, "model")

    store.save(settings)
    rewritten = json.loads(path.read_text(encoding="utf-8"))
    assert rewritten["version"] == 2
    assert "active_provider" not in rewritten
    assert "model" not in str(rewritten)


def test_corrupted_file_reports_sanitized_error(tmp_path):
    path = tmp_path / "settings" / "llm.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(LLMSettingsStorageError, match="unable to read") as caught:
        LLMSettingsStore(path).load()

    assert "not-json" not in str(caught.value)


def test_failed_atomic_replace_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "settings" / "llm.json"
    store = LLMSettingsStore(path)
    store.save(api_settings("first-key"))
    original = path.read_bytes()

    def fail_replace(_source, _destination):
        raise OSError("fixture replace failure")

    monkeypatch.setattr("app.llm.store.os.replace", fail_replace)
    with pytest.raises(LLMSettingsStorageError):
        store.save(api_settings("second-key"))

    assert path.read_bytes() == original


def test_legacy_environment_migrates_credentials_once_and_file_wins(tmp_path):
    store = LLMSettingsStore(tmp_path / "settings" / "llm.json")
    migrated, did_migrate = store.load_or_migrate({
        "DEEPSEEK_API_KEY": "legacy-fixture",
        "DEEPSEEK_API_BASE": "https://legacy.example",
        "DEEPSEEK_MODEL": "legacy-model",
    })

    assert did_migrate is True
    assert migrated is not None
    assert migrated.openai_compatible.api_key == "legacy-fixture"
    assert "legacy-model" not in store.path.read_text(encoding="utf-8")

    loaded, did_migrate_again = store.load_or_migrate({
        "DEEPSEEK_API_KEY": "changed-fixture",
        "DEEPSEEK_MODEL": "changed-model",
    })
    assert did_migrate_again is False
    assert loaded == migrated


def test_missing_legacy_key_stays_unconfigured_without_file(tmp_path):
    path = tmp_path / "settings" / "llm.json"
    settings, migrated = LLMSettingsStore(path).load_or_migrate({})

    assert settings is None
    assert migrated is False
    assert not path.exists()
