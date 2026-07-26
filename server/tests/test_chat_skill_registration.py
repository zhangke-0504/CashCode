from __future__ import annotations

import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.runner import SimpleAgentRunner
from app.agent.loop import SimpleAgentLoop
from app.agent.tools.registry import ToolRegistry
from app.agent.tools.tool_search import DeferredAwareRegistry
from app.api.skills import router as skills_router
from app.bus.queue import MessageBus
from app.paths import DataPaths
from app.skills.authoring import AgentSkillManageTool
from app.skills.catalog import SkillCatalog
from app.skills.models import SkillSource
from app.skills.loader import parse_skill_text
from app.skills.store import SkillStore
from app.skills.tools import SkillLoadTool, SkillSearchTool


def skill_text(name: str, display_name: str = "认知扭曲") -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"display_name: {display_name}\n"
        "description: 识别并重构常见认知扭曲\n"
        "version: 1\n"
        "tags: [心理, 反思]\n"
        "---\n\n"
        "# 工作流程\n\n识别想法、核对证据并生成平衡表述。\n"
    )


def make_store(tmp_path, *, builtin_root: Path | None = None) -> SkillStore:
    catalog = SkillCatalog(
        builtin_root or tmp_path / "builtin",
        tmp_path / "data" / "skills" / "user",
        tmp_path / "data" / "skills" / "agent",
    )
    return SkillStore(catalog, tmp_path / "snapshots")


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.function = SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        )

    def model_dump(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


class ScriptedCompletions:
    def __init__(self, messages):
        self.messages = list(messages)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        message = self.messages.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def response_message(*, content: str = "", tool_call: FakeToolCall | None = None):
    return SimpleNamespace(
        content=content,
        tool_calls=[tool_call] if tool_call is not None else None,
    )


def test_creator_localized_template_passes_current_loader():
    contract_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "skills"
        / "builtin"
        / "skill-creator"
        / "SKILL.md"
    )
    contract = contract_path.read_text(encoding="utf-8")
    template_match = re.search(r"```markdown\n(---\n.*?\n)```", contract, re.DOTALL)

    assert template_match is not None
    manifest, body, digest = parse_skill_text(
        template_match.group(1), expected_name="renzhi-niuqu"
    )
    assert manifest.name == "renzhi-niuqu"
    assert manifest.display_name == "认知扭曲"
    assert body.startswith("# 工作流程")
    assert len(digest) == 64
    assert "agent_skill_manage" in contract
    assert "^[a-z0-9][a-z0-9._-]{0,63}$" in contract


@pytest.mark.asyncio
async def test_restarted_agent_blocks_historical_direct_skill_write(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    data_root = workspace / "data"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_DIR", str(workspace / "memory"))
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CASHCODE_DATA_DIR", str(data_root))
    paths = DataPaths.from_environment(default_root=data_root)
    agent = SimpleAgentLoop(MessageBus(), data_paths=paths)
    writer = agent._registry.get("write_file")

    result = await writer.execute(  # type: ignore[union-attr]
        path="data/skills/user/renzhi-niuqu/SKILL.md",
        content=skill_text("认知扭曲"),
    )

    assert "agent_skill_manage" in result
    assert not (paths.skills_user / "renzhi-niuqu" / "SKILL.md").exists()
    assert agent._registry.get("agent_skill_manage") is not None
    assert agent.skill_catalog.get("skill-creator").missing == []  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_recorded_chinese_request_uses_creator_then_managed_tool(tmp_path):
    builtin_root = Path(__file__).resolve().parents[1] / "app" / "skills" / "builtin"
    store = make_store(tmp_path, builtin_root=builtin_root)
    full_registry = ToolRegistry()
    full_registry.register(AgentSkillManageTool(store))
    store.catalog.set_runtime_sources(
        tool_names=lambda: full_registry.tool_names,
        mcp_servers=lambda: (),
    )
    registry = DeferredAwareRegistry(full_registry)

    async def prepare_mcp(_name: str) -> bool:
        return False

    registry.register(SkillSearchTool(store.catalog))
    registry.register(SkillLoadTool(store.catalog, full_registry, prepare_mcp))
    content = skill_text("renzhi-niuqu")
    completions = ScriptedCompletions(
        [
            response_message(
                tool_call=FakeToolCall(
                    "load-creator", "skill_load", {"name": "skill-creator"}
                )
            ),
            response_message(
                tool_call=FakeToolCall(
                    "create-skill",
                    "agent_skill_manage",
                    {
                        "action": "create",
                        "name": "renzhi-niuqu",
                        "content": content,
                        "reason": "用户要求创建认知扭曲识别 Skill",
                    },
                )
            ),
            response_message(content="已创建“认知扭曲” Skill。"),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    runner = SimpleAgentRunner(client, "test-model")

    trace = await runner.run(
        [
            {"role": "system", "content": "按 Skill 创建合约执行。"},
            {
                "role": "user",
                "content": "帮我创建一个识别认知扭曲并引导重构想法的 Skill",
            },
        ],
        registry,
    )

    assert trace.success is True, trace.model_messages
    assert trace.tools_used == ["skill_load", "agent_skill_manage"]
    assert not {"write_file", "edit_file", "exec"}.intersection(trace.tools_used)
    managed_result = json.loads(
        next(
            message["content"]
            for message in trace.model_messages
            if message.get("role") == "tool"
            and message.get("name") == "agent_skill_manage"
        )
    )
    assert managed_result["success"] is True
    record = store.catalog.get("renzhi-niuqu")
    assert record is not None
    assert record.source is SkillSource.AGENT
    assert record.display_name == "认知扭曲"


@pytest.mark.asyncio
async def test_created_skill_is_immediately_listed_selected_and_editable(tmp_path):
    store = make_store(tmp_path)
    result = json.loads(
        await AgentSkillManageTool(store).execute(
            action="create",
            name="renzhi-niuqu",
            content=skill_text("renzhi-niuqu"),
        )
    )
    app = FastAPI()
    app.state.skill_store = store
    app.include_router(skills_router, prefix="/api")
    client = TestClient(app)

    localized = client.get("/api/skills", params={"query": "认知扭曲"}).json()
    canonical = client.get("/api/skills", params={"query": "renzhi-niuqu"}).json()
    selectable = client.get(
        "/api/skills",
        params={"enabled": "true", "availability": "available"},
    ).json()

    assert localized["items"][0]["name"] == "renzhi-niuqu"
    assert localized["items"][0]["display_name"] == "认知扭曲"
    assert localized["items"][0]["source"] == "agent"
    assert canonical["items"][0]["name"] == "renzhi-niuqu"
    assert any(item["name"] == "renzhi-niuqu" for item in selectable["items"])

    content = client.get("/api/skills/renzhi-niuqu/content").json()
    updated = client.put(
        "/api/skills/renzhi-niuqu",
        json={
            "content": skill_text("renzhi-niuqu", "思维偏差识别"),
            "expected_hash": content["hash"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "思维偏差识别"
    assert updated.json()["name"] == result["name"]
    assert store.catalog.get("renzhi-niuqu").display_name == "思维偏差识别"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_failed_managed_creation_marks_turn_failed_without_partial_package(tmp_path):
    store = make_store(tmp_path)
    registry = ToolRegistry()
    registry.register(AgentSkillManageTool(store))
    completions = ScriptedCompletions(
        [
            response_message(
                tool_call=FakeToolCall(
                    "invalid-create",
                    "agent_skill_manage",
                    {
                        "action": "create",
                        "name": "renzhi-niuqu",
                        "content": skill_text("wrong-name"),
                    },
                )
            ),
            response_message(content="创建失败，canonical name 与 frontmatter 不一致。"),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    trace = await SimpleAgentRunner(client, "test-model").run(
        [{"role": "user", "content": "创建认知扭曲 Skill"}], registry
    )

    assert trace.success is False
    assert trace.error == "one or more tool calls failed"
    tool_result = json.loads(trace.model_messages[1]["content"])
    assert tool_result["success"] is False
    assert tool_result["code"] == "validation_error"
    assert not any(store.catalog.roots[SkillSource.AGENT].iterdir())


@pytest.mark.asyncio
async def test_legacy_invalid_package_is_diagnostic_and_never_migrated(tmp_path):
    user_root = tmp_path / "data" / "skills" / "user"
    legacy = user_root / "renzhi-niuqu"
    legacy.mkdir(parents=True)
    legacy_content = skill_text("认知扭曲")
    (legacy / "SKILL.md").write_text(legacy_content, encoding="utf-8")
    store = make_store(tmp_path)

    result = json.loads(
        await AgentSkillManageTool(store).execute(
            action="create",
            name="renzhi-niuqu",
            content=skill_text("renzhi-niuqu"),
        )
    )

    assert result["success"] is False
    assert result["code"] == "conflict"
    assert set(store.catalog.invalid) == {"user:renzhi-niuqu"}
    assert store.catalog.get("renzhi-niuqu") is None
    assert (legacy / "SKILL.md").read_text(encoding="utf-8") == legacy_content
    assert not (store.catalog.roots[SkillSource.AGENT] / "renzhi-niuqu").exists()
