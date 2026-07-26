from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import app.agent.loop as loop_module
from app.agent.loop import SimpleAgentLoop
from app.agent.tools.registry import ToolRegistry


class FakeHandle:
    def __init__(self, tools):
        self.session = SimpleNamespace(list_tools=self._list_tools)
        self._tools = tools
        self.closed = 0

    async def _list_tools(self):
        return SimpleNamespace(tools=self._tools)

    async def aclose(self):
        self.closed += 1
        self.session = None


class FakeSkillCatalog:
    def __init__(self):
        self.refresh_count = 0

    def refresh(self):
        self.refresh_count += 1


class FakeStore:
    def __init__(self):
        self.metadata = {}

    def list_chat_ids(self):
        return list(self.metadata)

    def read_session_metadata(self, chat_id):
        return self.metadata.get(chat_id, {})

    def write_session_metadata(self, chat_id, data):
        self.metadata[chat_id] = data


def make_loop():
    loop = object.__new__(SimpleAgentLoop)
    loop._mcp_config = {"one": {"type": "sse", "url": "https://one/sse"}}
    loop._mcp_handles = {}
    loop._mcp_tool_names = {}
    loop._mcp_status = {"one": loop._disconnected_mcp_status()}
    loop._mcp_locks = {}
    loop._registry = ToolRegistry()
    loop._skill_catalog = FakeSkillCatalog()
    loop._session_metadata = {}
    loop._store = FakeStore()
    return loop


def tool(name="ping"):
    return SimpleNamespace(
        name=name,
        description="Ping",
        inputSchema={"type": "object", "properties": {}},
    )


@pytest.mark.asyncio
async def test_same_server_connect_is_coalesced(monkeypatch, tmp_path):
    loop = make_loop()
    handle = FakeHandle([tool()])
    calls = 0

    async def establish(configs, errors_out=None):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"one": handle}

    monkeypatch.setattr(loop_module, "establish_mcp_sessions", establish)
    monkeypatch.setattr(loop_module, "write_cache", lambda *args, **kwargs: None)

    first, second = await asyncio.gather(
        loop.connect_mcp_server("one"), loop.connect_mcp_server("one")
    )

    assert calls == 1
    assert first["status"] == second["status"] == "connected"
    assert loop._mcp_tool_names["one"] == {"mcp_one_ping"}


@pytest.mark.asyncio
async def test_connect_failure_leaves_no_handle_or_wrappers(monkeypatch):
    loop = make_loop()

    async def establish(configs, errors_out=None):
        errors_out["one"] = "RuntimeError: token [redacted]"
        return {}

    monkeypatch.setattr(loop_module, "establish_mcp_sessions", establish)
    status = await loop.connect_mcp_server("one")
    assert status["status"] == "error"
    assert not loop._mcp_handles
    assert not loop._registry.tool_names


@pytest.mark.asyncio
async def test_disconnect_unregisters_tools_and_purges_activation(monkeypatch):
    loop = make_loop()
    handle = FakeHandle([tool()])

    async def establish(configs, errors_out=None):
        return {"one": handle}

    monkeypatch.setattr(loop_module, "establish_mcp_sessions", establish)
    monkeypatch.setattr(loop_module, "write_cache", lambda *args, **kwargs: None)
    await loop.connect_mcp_server("one")
    loop._session_metadata["loaded"] = {
        "activated_tools": {"mcp_one_ping": 1, "save_memory": 2}
    }
    loop._store.metadata["disk"] = {
        "activated_tools": {"mcp_one_ping": 1}
    }

    status = await loop.disconnect_mcp_server("one")

    assert status["status"] == "disconnected"
    assert handle.closed == 1
    assert "mcp_one_ping" not in loop._registry.tool_names
    assert loop._session_metadata["loaded"]["activated_tools"] == {"save_memory": 2}
    assert loop._store.metadata["disk"]["activated_tools"] == {}


@pytest.mark.asyncio
async def test_remove_config_refreshes_skills_and_deletes_cache(monkeypatch):
    loop = make_loop()
    deleted = []
    monkeypatch.setattr(loop_module, "delete_cache", deleted.append)
    await loop.remove_mcp_config("one")
    assert "one" not in loop._mcp_config
    assert deleted == ["one"]
    assert loop._skill_catalog.refresh_count == 1


@pytest.mark.asyncio
async def test_different_servers_can_connect_concurrently(monkeypatch):
    loop = make_loop()
    loop._mcp_config["two"] = {"type": "sse", "url": "https://two/sse"}
    loop._mcp_status["two"] = loop._disconnected_mcp_status()
    running = 0
    max_running = 0

    async def establish(configs, errors_out=None):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.01)
        running -= 1
        name = next(iter(configs))
        return {name: FakeHandle([tool(name)])}

    monkeypatch.setattr(loop_module, "establish_mcp_sessions", establish)
    monkeypatch.setattr(loop_module, "write_cache", lambda *args, **kwargs: None)
    await asyncio.gather(
        loop.connect_mcp_server("one"), loop.connect_mcp_server("two")
    )
    assert max_running == 2


@pytest.mark.asyncio
async def test_replace_connected_config_closes_old_generation(monkeypatch):
    loop = make_loop()
    handle = FakeHandle([tool()])

    async def establish(configs, errors_out=None):
        return {"one": handle}

    monkeypatch.setattr(loop_module, "establish_mcp_sessions", establish)
    monkeypatch.setattr(loop_module, "write_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(loop_module, "delete_cache", lambda name: None)
    await loop.connect_mcp_server("one")
    await loop.replace_mcp_config(
        "one", {"type": "sse", "url": "https://new.example/sse"}
    )
    assert handle.closed == 1
    assert loop.get_mcp_status("one")["status"] == "disconnected"
    assert "mcp_one_ping" not in loop._registry.tool_names
