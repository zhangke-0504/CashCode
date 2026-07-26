from __future__ import annotations

import asyncio
import importlib
import io
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.agent.loop import SimpleAgentLoop
from app.bus.queue import MessageBus
from app.paths import DataPaths
from app.skills.catalog import SkillCatalog
from app.skills.store import SkillStore


def skill_text(name: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        "description: Lifecycle test\n"
        "---\n\n"
        "# Steps\n\nRun the lifecycle test.\n"
    )


def test_agent_loop_owns_one_live_store_and_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("CASHCODE_DATA_DIR", str(tmp_path / "data"))
    paths = DataPaths.from_environment()

    agent = SimpleAgentLoop(MessageBus(), data_paths=paths)
    revision = agent.skill_catalog.revision
    created = agent.skill_store.create("shared-skill", skill_text("shared-skill"))

    assert agent.skill_store.catalog is agent.skill_catalog
    assert agent._registry.get("agent_skill_manage").store is agent.skill_store  # type: ignore[union-attr]
    assert agent.skill_catalog.revision > revision
    assert agent.skill_catalog.get("shared-skill").content_hash == created["hash"]  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_lifespan_reuses_agent_store_for_api_and_evolution(tmp_path, monkeypatch):
    stdout = sys.stdout
    stderr = sys.stderr
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    try:
        main_module = importlib.import_module("main")
    finally:
        sys.stdout = stdout
        sys.stderr = stderr
    monkeypatch.setenv("CASHCODE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CASHCODE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("WS_PORT", "0")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    class FakeAgent:
        def __init__(self, bus, *, data_paths, llm_runtime):
            self.skill_catalog = SkillCatalog(
                tmp_path / "builtin",
                data_paths.skills_user,
                data_paths.skills_agent,
            )
            self.skill_store = SkillStore(
                self.skill_catalog, data_paths.skill_snapshots
            )
            self.llm_runtime = llm_runtime
            self._store = object()
            self._stopped = asyncio.Event()
            self.evolution = None

        def load_mcp_configs(self, configs):
            self.mcp_configs = configs

        def set_skill_evolution(self, service):
            self.evolution = service

        async def run(self):
            await self._stopped.wait()

        def stop(self):
            self._stopped.set()

    class FakeEvolution:
        def __init__(self, runtime, catalog, skill_store, root):
            self.runtime = runtime
            self.catalog = catalog
            self.skill_store = skill_store

        async def close(self):
            return None

    class FakeChannel:
        def __init__(self, bus, *, host, port):
            self._stopped = asyncio.Event()

        async def start(self):
            await self._stopped.wait()

        async def stop(self):
            self._stopped.set()

    monkeypatch.setattr(main_module, "SimpleAgentLoop", FakeAgent)
    monkeypatch.setattr(main_module, "EvolutionService", FakeEvolution)
    monkeypatch.setattr(main_module, "WebSocketChannel", FakeChannel)
    monkeypatch.setattr(main_module, "SimpleDream", lambda *args: SimpleNamespace())
    app = FastAPI()

    async with main_module.lifespan(app):
        assert app.state.llm_runtime.configured is False
        assert app.state.skill_store is main_module.agent.skill_store
        assert app.state.skill_catalog is main_module.agent.skill_catalog
        assert app.state.skill_evolution.skill_store is app.state.skill_store
        assert app.state.skill_evolution.catalog is app.state.skill_catalog
        assert main_module.agent.evolution is app.state.skill_evolution
