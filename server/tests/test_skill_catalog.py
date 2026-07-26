from __future__ import annotations

import pytest

from app.skills import catalog as catalog_module
from app.skills.catalog import MAX_INVALID_MESSAGE_CHARS, SkillCatalog
from app.skills.loader import MAX_DISPLAY_NAME_CHARS, parse_skill_text
from app.skills.models import SkillError
from app.skills.store import SkillStore


def skill_text(
    name: str,
    *,
    display_name: str | None = None,
    description: str = "Test workflow",
) -> str:
    display_line = f"display_name: {display_name}\n" if display_name is not None else ""
    return (
        "---\n"
        f"name: {name}\n"
        f"{display_line}"
        f"description: {description}\n"
        "---\n\n"
        "# Steps\n\nRun the workflow.\n"
    )


def make_catalog(tmp_path) -> SkillCatalog:
    return SkillCatalog(
        tmp_path / "builtin",
        tmp_path / "data" / "skills" / "user",
        tmp_path / "data" / "skills" / "agent",
    )


def write_skill(root, directory: str, content: str) -> None:
    skill_dir = root / directory
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_localized_and_fallback_display_names_are_searchable(tmp_path):
    builtin = tmp_path / "builtin"
    write_skill(builtin, "plain-skill", skill_text("plain-skill"))
    write_skill(
        builtin,
        "renzhi-niuqu",
        skill_text("renzhi-niuqu", display_name="认知扭曲"),
    )

    catalog = make_catalog(tmp_path)
    localized = catalog.get("renzhi-niuqu")
    fallback = catalog.get("plain-skill")

    assert localized is not None
    assert localized.to_dict()["display_name"] == "认知扭曲"
    assert fallback is not None
    assert fallback.to_dict()["display_name"] == "plain-skill"
    assert [record.name for _, record in catalog.search("认知扭曲")] == ["renzhi-niuqu"]
    assert catalog.get("认知扭曲") is None


def test_display_name_edit_preserves_canonical_identity_and_path(tmp_path):
    catalog = make_catalog(tmp_path)
    store = SkillStore(catalog, tmp_path / "snapshots")
    created = store.create(
        "renzhi-niuqu",
        skill_text("renzhi-niuqu", display_name="认知扭曲"),
    )
    original_path = catalog.get("renzhi-niuqu").path  # type: ignore[union-attr]

    updated = store.replace(
        "renzhi-niuqu",
        skill_text("renzhi-niuqu", display_name="思维偏差"),
        expected_hash=created["hash"],
    )

    assert updated["name"] == "renzhi-niuqu"
    assert updated["display_name"] == "思维偏差"
    assert catalog.get("renzhi-niuqu").path == original_path  # type: ignore[union-attr]
    assert store.read_content("renzhi-niuqu")["display_name"] == "思维偏差"


@pytest.mark.parametrize(
    "content, message",
    [
        (skill_text("other-name", display_name="认知扭曲"), "match the package directory"),
        (skill_text("renzhi-niuqu", display_name="bad\nlabel"), "frontmatter"),
        (
            skill_text("renzhi-niuqu", display_name="显" * (MAX_DISPLAY_NAME_CHARS + 1)),
            "at most",
        ),
    ],
)
def test_display_name_validation_keeps_canonical_rules(content, message):
    with pytest.raises(SkillError, match=message):
        parse_skill_text(content, expected_name="renzhi-niuqu")


def test_invalid_diagnostics_are_bounded_path_free_and_isolated(tmp_path, monkeypatch):
    builtin = tmp_path / "builtin"
    user = tmp_path / "data" / "skills" / "user"
    write_skill(builtin, "valid-skill", skill_text("valid-skill"))
    write_skill(user, "legacy-invalid", skill_text("wrong-name"))
    original_reader = catalog_module.read_skill_package

    def failing_reader(skill_dir):
        if skill_dir.name == "legacy-invalid":
            raise SkillError(f"failed at {skill_dir / 'private.txt'}: {'x' * 500}")
        return original_reader(skill_dir)

    monkeypatch.setattr(catalog_module, "read_skill_package", failing_reader)
    catalog = make_catalog(tmp_path)

    assert [record.name for record in catalog.list()] == ["valid-skill"]
    assert catalog.get("legacy-invalid") is None
    assert set(catalog.invalid) == {"user:legacy-invalid"}
    message = catalog.invalid["user:legacy-invalid"][0]
    assert str(tmp_path) not in message
    assert "private.txt" not in message
    assert len(message) <= MAX_INVALID_MESSAGE_CHARS

