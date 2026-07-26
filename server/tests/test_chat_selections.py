from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agent.tools.base import Tool
from app.agent.tools.registry import ToolRegistry
from app.agent.tools.tool_search import (
    ActivatedToolSet,
    DeferredAwareRegistry,
    use_activated_set,
    use_temporary_tools,
)
from app.memory.store import MemoryStore
from app.selections import SelectionValidationError, sanitize_selection_metadata
from app.ws.channel import WebSocketChannel


class DummyTool(Tool):
    @property
    def name(self):
        return "mcp_weather_lookup"

    @property
    def description(self):
        return "Lookup weather"

    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return "sunny"


class FakeBus:
    def __init__(self):
        self.messages = []

    async def publish_inbound(self, message):
        self.messages.append(message)


def schema_names(registry):
    return {
        item["function"]["name"]
        for item in registry.get_definitions()
    }


def test_selection_metadata_is_sanitized_and_deduplicated():
    data = sanitize_selection_metadata(
        {
            "mentioned_skills": [
                {"name": "weather", "label": " Weather "},
                {"name": "weather", "label": "Duplicate"},
            ],
            "selected_mcp_connectors": [
                {"server": "weather-mcp", "label": "MCP"}
            ],
            "ignored": "value",
        }
    )
    assert data == {
        "mentioned_skills": [{"name": "weather", "label": "Weather"}],
        "selected_mcp_connectors": [
            {"server": "weather-mcp", "label": "MCP"}
        ],
    }


@pytest.mark.parametrize(
    "metadata",
    [
        {"mentioned_skills": "weather"},
        {"mentioned_skills": [{"name": "Bad Name"}]},
        {"selected_mcp_connectors": [{"server": "bad.name"}]},
        {"mentioned_skills": [{"name": f"s{i}"} for i in range(9)]},
        {"mentioned_skills": [{"name": "weather", "label": "x" * 101}]},
    ],
)
def test_invalid_selection_metadata_is_rejected(metadata):
    with pytest.raises(SelectionValidationError):
        sanitize_selection_metadata(metadata)


@pytest.mark.asyncio
async def test_websocket_passes_only_sanitized_metadata():
    bus = FakeBus()
    channel = WebSocketChannel(bus)
    channel._send = AsyncMock()
    conn = object()
    await channel._dispatch_envelope(
        conn,
        "client",
        {
            "type": "message",
            "chat_id": "chat-1",
            "content": "hello",
            "metadata": {
                "mentioned_skills": [{"name": "weather", "label": " Weather "}],
                "llm": {"provider": "ollama", "model": "qwen3"},
                "untrusted": {"tool": "exec"},
            },
        },
    )
    assert len(bus.messages) == 1
    assert bus.messages[0].metadata == {
        "mentioned_skills": [{"name": "weather", "label": "Weather"}],
        "llm": {"provider": "ollama", "model": "qwen3"},
    }


@pytest.mark.asyncio
async def test_websocket_rejects_missing_model_selection_without_enqueueing():
    bus = FakeBus()
    channel = WebSocketChannel(bus)
    channel._send = AsyncMock()
    await channel._dispatch_envelope(
        object(),
        "client",
        {"type": "message", "chat_id": "chat-1", "content": "hello"},
    )
    assert bus.messages == []
    assert "llm selection" in channel._send.await_args.args[1]["detail"]
    assert channel._send.await_args.args[1]["chat_id"] == "chat-1"


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_metadata_without_enqueueing():
    bus = FakeBus()
    channel = WebSocketChannel(bus)
    channel._send = AsyncMock()
    await channel._dispatch_envelope(
        object(),
        "client",
        {
            "type": "message",
            "chat_id": "chat-1",
            "content": "hello",
            "metadata": {"selected_mcp_connectors": "weather"},
        },
    )
    assert bus.messages == []
    assert channel._send.await_args.args[1]["event"] == "error"
    assert channel._send.await_args.args[1]["chat_id"] == "chat-1"


@pytest.mark.asyncio
async def test_temporary_mcp_visibility_never_persists():
    full = ToolRegistry()
    full.register(DummyTool())
    deferred = DeferredAwareRegistry(full)
    metadata = {"activated_tools": {}}
    activated = ActivatedToolSet.from_session(metadata)

    with use_activated_set(activated):
        assert "mcp_weather_lookup" not in schema_names(deferred)
        with use_temporary_tools({"mcp_weather_lookup"}):
            assert "mcp_weather_lookup" in schema_names(deferred)
            assert await deferred.execute("mcp_weather_lookup", {}) == "sunny"
        assert "mcp_weather_lookup" not in schema_names(deferred)

    assert metadata == {"activated_tools": {}}


def test_temporary_visibility_restores_after_exception():
    full = ToolRegistry()
    full.register(DummyTool())
    deferred = DeferredAwareRegistry(full)
    activated = ActivatedToolSet.from_session({})
    with use_activated_set(activated):
        with pytest.raises(RuntimeError):
            with use_temporary_tools({"mcp_weather_lookup"}):
                assert "mcp_weather_lookup" in schema_names(deferred)
                raise RuntimeError("turn failed")
        assert "mcp_weather_lookup" not in schema_names(deferred)


def test_history_persists_only_bounded_selection_receipts(tmp_path):
    store = MemoryStore(tmp_path)
    metadata = {
        "mentioned_skills": [{"name": "weather", "label": "Weather"}],
        "selected_mcp_connectors": [
            {"server": "weather-mcp", "label": "Weather MCP"}
        ],
        "headers": {"Authorization": "secret"},
    }
    store.append_turn("chat", "forecast", "sunny", user_metadata=metadata)
    messages = store.load_public_history("chat")
    assert messages[0] == {
        "role": "user",
        "content": "forecast",
        "mentioned_skills": [{"name": "weather", "label": "Weather"}],
        "selected_mcp_connectors": [
            {"server": "weather-mcp", "label": "Weather MCP"}
        ],
    }
    assert "secret" not in str(messages)


def test_legacy_history_remains_plain(tmp_path):
    store = MemoryStore(tmp_path)
    store.append_turn("chat", "hello", "hi")
    assert store.load_public_history("chat") == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
