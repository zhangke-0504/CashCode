from __future__ import annotations

import json

import pytest

from app.agent.tools.filesystem import EditFileTool, WriteFileTool
from app.skills.authoring import AgentSkillManageTool
from app.skills.catalog import SkillCatalog
from app.skills.models import SkillError, SkillSource
from app.skills.store import SkillStore


def skill_text(
    name: str,
    *,
    display_name: str | None = None,
    description: str = "Managed workflow",
) -> str:
    display_line = f"display_name: {display_name}\n" if display_name else ""
    return (
        "---\n"
        f"name: {name}\n"
        f"{display_line}"
        f"description: {description}\n"
        "---\n\n"
        "# Steps\n\nFollow the managed workflow.\n"
    )


def make_store(tmp_path) -> SkillStore:
    catalog = SkillCatalog(
        tmp_path / "builtin",
        tmp_path / "data" / "skills" / "user",
        tmp_path / "data" / "skills" / "agent",
    )
    return SkillStore(catalog, tmp_path / "snapshots")


def decode(result: str) -> dict:
    return json.loads(result)


@pytest.mark.asyncio
async def test_managed_tool_creates_visible_agent_skill_with_localized_label(tmp_path):
    store = make_store(tmp_path)
    tool = AgentSkillManageTool(store)

    result = decode(
        await tool.execute(
            action="create",
            name="renzhi-niuqu",
            content=skill_text("renzhi-niuqu", display_name="认知扭曲"),
            support_files={"references/guide.md": "诊断步骤"},
            reason="用户明确要求创建可复用流程",
        )
    )

    assert result["success"] is True
    assert result["name"] == "renzhi-niuqu"
    assert result["display_name"] == "认知扭曲"
    assert result["source"] == "agent"
    assert result["enabled"] is True
    assert "path" not in result
    record = store.catalog.get("renzhi-niuqu")
    assert record is not None
    assert record.source is SkillSource.AGENT
    assert record.content_hash == result["hash"]
    assert (record.path / "references" / "guide.md").read_text(
        encoding="utf-8"
    ) == "诊断步骤"
    metadata = json.loads((record.path / "_meta.json").read_text(encoding="utf-8"))
    assert metadata["source"] == "agent"
    assert metadata["enabled"] is True
    assert metadata["creation_reason"] == "用户明确要求创建可复用流程"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, content",
    [
        ("认知扭曲", skill_text("renzhi-niuqu", display_name="认知扭曲")),
        ("renzhi-niuqu", skill_text("other-name", display_name="认知扭曲")),
    ],
)
async def test_managed_tool_rejects_invalid_or_mismatched_identity(
    tmp_path, name, content
):
    store = make_store(tmp_path)
    result = decode(
        await AgentSkillManageTool(store).execute(
            action="create", name=name, content=content
        )
    )

    assert result["success"] is False
    assert result["code"] == "validation_error"
    assert not any(store.catalog.roots[SkillSource.AGENT].iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("source", list(SkillSource))
async def test_managed_tool_rejects_cross_root_physical_conflicts(
    tmp_path, source
):
    store = make_store(tmp_path)
    occupied = store.catalog.roots[source] / "occupied"
    occupied.mkdir(parents=True)
    (occupied / "SKILL.md").write_text("invalid", encoding="utf-8")
    store.catalog.refresh()

    result = decode(
        await AgentSkillManageTool(store).execute(
            action="create", name="occupied", content=skill_text("occupied")
        )
    )

    assert result["success"] is False
    assert result["code"] == "conflict"
    assert (occupied / "SKILL.md").read_text(encoding="utf-8") == "invalid"


@pytest.mark.asyncio
async def test_managed_tool_rolls_back_publication_failure(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    original_refresh = store.catalog.refresh
    refresh_calls = 0

    def fail_first_refresh():
        nonlocal refresh_calls
        refresh_calls += 1
        if refresh_calls == 1:
            raise OSError(
                f"refresh failed at {store.catalog.roots[SkillSource.AGENT] / 'broken'}"
            )
        original_refresh()

    monkeypatch.setattr(store.catalog, "refresh", fail_first_refresh)
    result = decode(
        await AgentSkillManageTool(store).execute(
            action="create", name="broken", content=skill_text("broken")
        )
    )

    assert result["success"] is False
    assert result["code"] == "publication_failed"
    assert str(tmp_path) not in result["detail"]
    assert not (store.catalog.roots[SkillSource.AGENT] / "broken").exists()
    assert store.catalog.get("broken") is None


@pytest.mark.asyncio
async def test_managed_tool_returns_path_free_validation_and_permission_errors(
    tmp_path, monkeypatch
):
    store = make_store(tmp_path)
    tool = AgentSkillManageTool(store)
    private_path = tmp_path / "private" / "SKILL.md"

    monkeypatch.setattr(
        store,
        "create",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SkillError(f"invalid package at {private_path}")
        ),
    )
    invalid = decode(
        await tool.execute(
            action="create", name="invalid-path", content=skill_text("invalid-path")
        )
    )
    assert invalid["code"] == "validation_error"
    assert str(tmp_path) not in invalid["detail"]
    assert "SKILL.md" not in invalid["detail"]

    monkeypatch.setattr(
        store,
        "create",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            PermissionError(f"denied at {private_path}")
        ),
    )
    denied = decode(
        await tool.execute(
            action="create", name="denied-path", content=skill_text("denied-path")
        )
    )
    assert denied["code"] == "permission_denied"
    assert str(tmp_path) not in denied["detail"]


@pytest.mark.asyncio
async def test_generic_file_tools_protect_skill_roots_and_allow_workspace_files(tmp_path):
    workspace = tmp_path / "workspace"
    user_root = workspace / "data" / "skills" / "user"
    agent_root = workspace / "data" / "skills" / "agent"
    user_root.mkdir(parents=True)
    agent_root.mkdir(parents=True)
    protected = (user_root, agent_root)
    writer = WriteFileTool(workspace, protected_roots=protected)
    editor = EditFileTool(workspace, protected_roots=protected)
    agent_file = agent_root / "existing" / "SKILL.md"
    agent_file.parent.mkdir()
    agent_file.write_text("original", encoding="utf-8")

    blocked_write = await writer.execute(
        path="data/skills/user/new-skill/SKILL.md", content="invalid"
    )
    blocked_edit = await editor.execute(
        path="data/skills/agent/existing/SKILL.md",
        old_string="original",
        new_string="changed",
    )
    ordinary_write = await writer.execute(path="notes/result.txt", content="result")
    ordinary_edit = await editor.execute(
        path="notes/result.txt", old_string="result", new_string="updated"
    )

    assert "agent_skill_manage" in blocked_write
    assert "agent_skill_manage" in blocked_edit
    assert not (user_root / "new-skill").exists()
    assert agent_file.read_text(encoding="utf-8") == "original"
    assert ordinary_write.startswith("已写入")
    assert ordinary_edit.startswith("已替换")
    assert (workspace / "notes" / "result.txt").read_text(
        encoding="utf-8"
    ) == "updated"

