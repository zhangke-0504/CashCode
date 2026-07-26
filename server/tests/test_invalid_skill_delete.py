from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.skills import router
from app.skills.catalog import SkillCatalog
from app.skills.models import (
    SkillConflictError,
    SkillError,
    SkillNotFoundError,
    SkillPermissionError,
    SkillSource,
)
from app.skills.store import SkillStore


def valid_skill_text(name: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        "description: Valid workflow\n"
        "---\n\n"
        "# Steps\n\nRun the workflow.\n"
    )


def invalid_skill_text() -> str:
    return (
        "---\n"
        "name: 认知扭曲\n"
        "description: Invalid canonical identity\n"
        "---\n\n"
        "# Steps\n\nRun the workflow.\n"
    )


def make_store(tmp_path) -> SkillStore:
    catalog = SkillCatalog(
        tmp_path / "builtin",
        tmp_path / "data" / "skills" / "user",
        tmp_path / "data" / "skills" / "agent",
    )
    return SkillStore(catalog, tmp_path / "snapshots")


def write_invalid(store: SkillStore, source: SkillSource, name: str = "broken"):
    directory = store.catalog.roots[source] / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(invalid_skill_text(), encoding="utf-8")
    store.catalog.refresh()
    return directory


@pytest.mark.parametrize("source", [SkillSource.USER, SkillSource.AGENT])
def test_invalid_mutable_package_moves_to_snapshot_and_leaves_catalog(
    tmp_path, source
):
    store = make_store(tmp_path)
    target = write_invalid(store, source)

    result = store.delete_invalid(source, "broken")

    snapshot = store.snapshots_root / result["snapshot"]
    assert not target.exists()
    assert snapshot.is_dir()
    assert (snapshot / "SKILL.md").read_text(encoding="utf-8") == invalid_skill_text()
    assert f"{source.value}:broken" not in store.catalog.invalid
    assert store.catalog.get("broken") is None


def test_invalid_builtin_package_cannot_be_deleted(tmp_path):
    store = make_store(tmp_path)
    target = write_invalid(store, SkillSource.BUILTIN)

    with pytest.raises(SkillPermissionError, match="read-only"):
        store.delete_invalid(SkillSource.BUILTIN, "broken")

    assert target.is_dir()


def test_invalid_delete_rechecks_package_and_preserves_repaired_skill(tmp_path):
    store = make_store(tmp_path)
    target = write_invalid(store, SkillSource.USER)
    (target / "SKILL.md").write_text(valid_skill_text("broken"), encoding="utf-8")

    with pytest.raises(SkillConflictError, match="is valid"):
        store.delete_invalid(SkillSource.USER, "broken")

    assert target.is_dir()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == valid_skill_text(
        "broken"
    )


@pytest.mark.parametrize("selector", ["", ".", "..", "../broken", "nested/broken", "nested\\broken"])
def test_invalid_delete_rejects_empty_nested_or_traversal_selectors(
    tmp_path, selector
):
    store = make_store(tmp_path)
    write_invalid(store, SkillSource.USER)

    with pytest.raises(SkillError, match="directory selector"):
        store.delete_invalid(SkillSource.USER, selector)


def test_invalid_delete_rejects_missing_or_stale_target(tmp_path):
    store = make_store(tmp_path)
    target = write_invalid(store, SkillSource.USER)
    (target / "SKILL.md").unlink()
    target.rmdir()

    with pytest.raises(SkillNotFoundError, match="not found"):
        store.delete_invalid(SkillSource.USER, "broken")


def test_invalid_delete_rolls_back_when_catalog_refresh_fails(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    target = write_invalid(store, SkillSource.USER)
    original_refresh = store.catalog.refresh
    refresh_calls = 0

    def fail_first_refresh():
        nonlocal refresh_calls
        refresh_calls += 1
        if refresh_calls == 1:
            raise RuntimeError("refresh failed")
        original_refresh()

    monkeypatch.setattr(store.catalog, "refresh", fail_first_refresh)

    with pytest.raises(RuntimeError, match="refresh failed"):
        store.delete_invalid(SkillSource.USER, "broken")

    assert target.is_dir()
    assert "user:broken" in store.catalog.invalid


def test_invalid_delete_api_removes_diagnostic_and_protects_builtin(tmp_path):
    store = make_store(tmp_path)
    write_invalid(store, SkillSource.USER, "user-broken")
    write_invalid(store, SkillSource.BUILTIN, "builtin-broken")
    app = FastAPI()
    app.state.skill_store = store
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    deleted = client.delete("/api/skills/invalid/user/user-broken")
    protected = client.delete("/api/skills/invalid/builtin/builtin-broken")
    listed = client.get("/api/skills").json()

    assert deleted.status_code == 200
    assert deleted.json()["source"] == "user"
    assert deleted.json()["directory"] == "user-broken"
    assert protected.status_code == 403
    assert "user:user-broken" not in listed["invalid"]
    assert "builtin:builtin-broken" in listed["invalid"]

