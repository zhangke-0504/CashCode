from __future__ import annotations

import io
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills import router
from app.skills.catalog import SkillCatalog
from app.skills.models import SkillSource
from app.skills.store import SkillStore


def skill_text(name: str, description: str = "Managed workflow", version: int = 1) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"version: {version}\n"
        "---\n\n"
        "# Workflow\n\nFollow the managed steps.\n"
    )


def archive_bytes(name: str, *, binary: bytes | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_text(name))
        if binary is not None:
            zf.writestr("assets/data.bin", binary)
    return output.getvalue()


def make_client(tmp_path) -> tuple[TestClient, SkillStore]:
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    builtin_skill = builtin / "builtin-skill"
    builtin_skill.mkdir()
    (builtin_skill / "SKILL.md").write_text(
        skill_text("builtin-skill", "Read only"), encoding="utf-8"
    )
    catalog = SkillCatalog(
        builtin,
        tmp_path / "data" / "skills" / "user",
        tmp_path / "data" / "skills" / "agent",
    )
    store = SkillStore(catalog, tmp_path / "data" / "skill-snapshots")
    app = FastAPI()
    app.state.skill_store = store
    app.include_router(router, prefix="/api")
    return TestClient(app), store


def test_import_content_and_conflict_api(tmp_path):
    client, store = make_client(tmp_path)
    binary = b"\x00\x01\xffpayload"
    response = client.post(
        "/api/skills/import",
        files={"file": ("uploaded.zip", archive_bytes("uploaded", binary=binary), "application/zip")},
    )
    assert response.status_code == 201
    assert response.json()["source"] == "user"

    content = client.get("/api/skills/uploaded/content")
    assert content.status_code == 200
    assert content.json()["content"] == skill_text("uploaded")
    assert content.json()["mutable"] is True
    assert "path" not in content.json()

    duplicate = client.post(
        "/api/skills/import",
        files={"file": ("uploaded.zip", archive_bytes("uploaded"), "application/zip")},
    )
    assert duplicate.status_code == 409

    builtin_conflict = client.post(
        "/api/skills/import",
        files={"file": ("builtin.zip", archive_bytes("builtin-skill"), "application/zip")},
    )
    assert builtin_conflict.status_code == 409
    assert (store.catalog.get("uploaded").path / "assets" / "data.bin").read_bytes() == binary


def test_user_and_agent_edits_preserve_assets_and_ownership(tmp_path):
    client, store = make_client(tmp_path)
    user_binary = b"user-asset\x00"
    assert client.post(
        "/api/skills/import",
        files={"file": ("user.zip", archive_bytes("user-skill", binary=user_binary), "application/zip")},
    ).status_code == 201
    agent = store.create(
        "agent-skill",
        skill_text("agent-skill"),
        source=SkillSource.AGENT,
        support_files={"assets/note.txt": "agent-asset"},
    )

    user_content = client.get("/api/skills/user-skill/content").json()
    user_update = client.put(
        "/api/skills/user-skill",
        json={
            "content": skill_text("user-skill", "Updated user", 2),
            "expected_hash": user_content["hash"],
        },
    )
    assert user_update.status_code == 200
    assert user_update.json()["source"] == "user"
    assert (store.catalog.get("user-skill").path / "assets" / "data.bin").read_bytes() == user_binary

    agent_update = client.put(
        "/api/skills/agent-skill",
        json={
            "content": skill_text("agent-skill", "Updated agent", 2),
            "expected_hash": agent["hash"],
        },
    )
    assert agent_update.status_code == 200
    assert agent_update.json()["source"] == "agent"
    assert (store.catalog.get("agent-skill").path / "assets" / "note.txt").read_text(encoding="utf-8") == "agent-asset"
    assert store.versions("user-skill")
    assert store.versions("agent-skill")


def test_edit_validation_stale_hash_lifecycle_and_builtin_protection(tmp_path):
    client, store = make_client(tmp_path)
    created = store.create("managed", skill_text("managed"))

    stale = client.put(
        "/api/skills/managed",
        json={"content": skill_text("managed", "New"), "expected_hash": "stale"},
    )
    assert stale.status_code == 409
    renamed = client.put(
        "/api/skills/managed",
        json={"content": skill_text("other-name"), "expected_hash": created["hash"]},
    )
    assert renamed.status_code == 422

    disabled = client.patch("/api/skills/managed/enabled", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    selectable = client.get("/api/skills?enabled=true&availability=available")
    assert all(item["name"] != "managed" for item in selectable.json()["items"])

    for method, path, payload in (
        ("put", "/api/skills/builtin-skill", {"content": skill_text("builtin-skill")}),
        ("patch", "/api/skills/builtin-skill/enabled", {"enabled": False}),
        ("delete", "/api/skills/builtin-skill", None),
    ):
        response = getattr(client, method)(path, json=payload) if payload is not None else getattr(client, method)(path)
        assert response.status_code == 403

    assert client.delete("/api/skills/managed").status_code == 204
    assert store.catalog.get("managed") is None


def test_upload_and_content_errors_are_bounded(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post(
        "/api/skills/import",
        files={"file": ("skill.txt", b"not zip", "text/plain")},
    ).status_code == 422
    assert client.post(
        "/api/skills/import",
        files={"file": ("skill.zip", b"not zip", "application/zip")},
    ).status_code == 422
    assert client.get("/api/skills/missing/content").status_code == 404
