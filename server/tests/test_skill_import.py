from __future__ import annotations

import io
import json
import stat
import zipfile

import pytest

from app.skills.catalog import SkillCatalog
from app.skills.models import SkillConflictError, SkillError, SkillSource
from app.skills.store import SkillStore


def skill_text(name: str, description: str = "Test workflow", version: int = 1) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"version: {version}\n"
        "tags: [test]\n"
        "---\n\n"
        "# Steps\n\nRun the test workflow.\n"
    )


def archive_bytes(entries: dict[str, bytes | str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, value in entries.items():
            zf.writestr(name, value)
    return output.getvalue()


def write_skill(root, name: str, *, enabled: bool = True) -> None:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(skill_text(name), encoding="utf-8")
    (directory / "_meta.json").write_text(
        json.dumps({"enabled": enabled}), encoding="utf-8"
    )


def make_store(tmp_path) -> SkillStore:
    catalog = SkillCatalog(
        tmp_path / "builtin",
        tmp_path / "data" / "skills" / "user",
        tmp_path / "data" / "skills" / "agent",
    )
    return SkillStore(catalog, tmp_path / "data" / "skill-snapshots")


def test_imports_flat_package_and_preserves_binary_assets(tmp_path):
    store = make_store(tmp_path)
    binary = b"\x00\xff\x01asset"
    revision = store.catalog.revision
    result = store.import_zip(
        archive_bytes(
            {
                "SKILL.md": skill_text("flat-skill"),
                "assets/icon.bin": binary,
                "_meta.json": json.dumps(
                    {"source": "builtin", "enabled": False, "agentCreated": True}
                ),
            }
        )
    )

    record = store.catalog.get("flat-skill")
    assert result["source"] == "user"
    assert record is not None
    assert record.source is SkillSource.USER
    assert record.enabled is True
    assert (record.path / "assets" / "icon.bin").read_bytes() == binary
    meta = json.loads((record.path / "_meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "user"
    assert meta["enabled"] is True
    assert meta["agentCreated"] is False
    assert store.catalog.revision > revision


def test_imports_package_inside_one_wrapper_directory(tmp_path):
    store = make_store(tmp_path)
    result = store.import_zip(
        archive_bytes(
            {
                "release-folder/": b"",
                "release-folder/SKILL.md": skill_text("wrapped-skill"),
                "release-folder/references/guide.md": "Guide",
            }
        )
    )

    assert result["name"] == "wrapped-skill"
    record = store.catalog.get("wrapped-skill")
    assert record is not None
    assert (record.path / "references" / "guide.md").read_text(encoding="utf-8") == "Guide"


@pytest.mark.parametrize("source", list(SkillSource))
def test_import_rejects_name_from_every_source(tmp_path, source):
    store = make_store(tmp_path)
    write_skill(store.catalog.roots[source], "same-name")
    store.catalog.refresh()

    with pytest.raises(SkillConflictError, match="already exists"):
        store.import_zip(archive_bytes({"SKILL.md": skill_text("same-name")}))

    assert not list(store.catalog.roots[SkillSource.USER].glob(".skill-import.*"))


@pytest.mark.parametrize(
    "entries, message",
    [
        ({"../escape/SKILL.md": skill_text("escape")}, "illegal path"),
        (
            {
                "first/SKILL.md": skill_text("first"),
                "second/SKILL.md": skill_text("second"),
            },
            "exactly one top-level",
        ),
        (
            {"SKILL.md": skill_text("bad-root"), "unexpected.txt": "bad"},
            "unsupported package entry",
        ),
        (
            {"SKILL.md": skill_text("oversized"), "assets/large.bin": b"x" * 200_001},
            "too large",
        ),
    ],
)
def test_import_rejects_malicious_or_invalid_archives(tmp_path, entries, message):
    store = make_store(tmp_path)
    with pytest.raises(SkillError, match=message):
        store.import_zip(archive_bytes(entries))

    assert store.catalog.list() == []
    assert not list(store.catalog.roots[SkillSource.USER].glob(".skill-import.*"))


def test_import_rejects_symlink_member(tmp_path):
    store = make_store(tmp_path)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zf:
        zf.writestr("SKILL.md", skill_text("linked"))
        info = zipfile.ZipInfo("scripts/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "../outside")

    with pytest.raises(SkillError, match="symlink"):
        store.import_zip(output.getvalue())

    assert store.catalog.get("linked") is None


def test_import_cleans_up_invalid_package_without_advancing_catalog(tmp_path):
    store = make_store(tmp_path)
    revision = store.catalog.revision
    invalid = "---\nname: invalid\ndescription: Broken\n---\n"

    with pytest.raises(SkillError, match="body cannot be empty"):
        store.import_zip(archive_bytes({"SKILL.md": invalid}))

    assert store.catalog.revision == revision
    assert not any(store.catalog.roots[SkillSource.USER].iterdir())


@pytest.mark.parametrize("source", list(SkillSource))
def test_invalid_physical_directory_blocks_create_and_import(tmp_path, source):
    store = make_store(tmp_path)
    occupied = store.catalog.roots[source] / "occupied-name"
    occupied.mkdir(parents=True)
    (occupied / "SKILL.md").write_text("not a valid Skill", encoding="utf-8")
    store.catalog.refresh()

    with pytest.raises(SkillConflictError, match="already exists"):
        store.create("occupied-name", skill_text("occupied-name"))
    with pytest.raises(SkillConflictError, match="already exists"):
        store.import_zip(
            archive_bytes({"SKILL.md": skill_text("occupied-name")})
        )

    assert (occupied / "SKILL.md").read_text(encoding="utf-8") == "not a valid Skill"
    assert store.catalog.get("occupied-name") is None
