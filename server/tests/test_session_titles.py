from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.loop import SimpleAgentLoop, first_session_title
from app.api.sessions import router as sessions_router
from app.bus.events import InboundMessage, OutboundMessage
from app.bus.queue import MessageBus
from app.llm.runtime import LLMRuntime
from app.paths import DataPaths
from app.ws.channel import WebSocketChannel


class ControlledCompletions:
    def __init__(self, *, block_calls: set[int] | None = None, fail_calls: set[int] | None = None):
        self.calls = 0
        self.block_calls = block_calls or set()
        self.fail_calls = fail_calls or set()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def create(self, **_kwargs):
        self.calls += 1
        call = self.calls
        if call in self.block_calls:
            self.started.set()
            await self.release.wait()
        if call in self.fail_calls:
            raise RuntimeError("fixture turn failed")
        message = SimpleNamespace(content=f"answer-{call}", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_agent(tmp_path, monkeypatch, completions: ControlledCompletions):
    workspace = tmp_path / "workspace"
    data_root = tmp_path / "data"
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CASHCODE_DATA_DIR", str(data_root))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    runtime = LLMRuntime.from_client(client, "fixture-model")
    bus = MessageBus()
    agent = SimpleAgentLoop(
        bus,
        data_paths=DataPaths.from_environment(default_root=data_root),
        llm_runtime=runtime,
    )
    return agent, bus


def inbound(chat_id: str, content: str = "first question") -> InboundMessage:
    return InboundMessage(
        channel="websocket",
        sender_id="fixture",
        chat_id=chat_id,
        content=content,
        metadata={
            "llm": {"provider": "openai_compatible", "model": "fixture-model"}
        },
    )


def outbound_nowait(bus: MessageBus) -> list[OutboundMessage]:
    messages: list[OutboundMessage] = []
    while not bus.outbound.empty():
        messages.append(bus.outbound.get_nowait())
    return messages


def test_first_session_title_normalizes_and_truncates_unicode():
    assert first_session_title("  hello\n\tworld   again  ") == "hello world again"
    assert first_session_title("问" * 45) == "问" * 40


@pytest.mark.asyncio
async def test_first_title_is_persisted_and_published_before_completion(
    tmp_path, monkeypatch
):
    completions = ControlledCompletions(block_calls={1})
    agent, bus = make_agent(tmp_path, monkeypatch, completions)

    turn = asyncio.create_task(
        agent._handle_turn_locked(inbound("chat-first", "  explain\n  this   behavior  "))
    )
    await asyncio.wait_for(completions.started.wait(), timeout=1)

    update = await asyncio.wait_for(bus.consume_outbound(), timeout=1)
    assert update.metadata["_session_updated"] is True
    assert update.metadata["_title"] == "explain this behavior"
    assert update.metadata["_updated_at"]
    assert agent._store.read_session_metadata("chat-first")["title"] == "explain this behavior"
    assert not turn.done()

    completions.release.set()
    await turn


@pytest.mark.asyncio
async def test_first_title_survives_failure_and_existing_titles_are_preserved(
    tmp_path, monkeypatch
):
    completions = ControlledCompletions(fail_calls={1})
    agent, bus = make_agent(tmp_path, monkeypatch, completions)

    await agent._handle_turn_locked(inbound("chat-failure", "failed first question"))

    assert agent._store.read_session_metadata("chat-failure")["title"] == "failed first question"
    assert agent._session_metadata["chat-failure"]["title"] == "failed first question"
    metadata_events = [message.metadata for message in outbound_nowait(bus)]
    assert metadata_events[0]["_session_updated"] is True
    assert metadata_events[0]["_title"] == "failed first question"
    assert metadata_events[0]["_updated_at"]
    assert metadata_events[1] == {"_user_error": True}

    preserved = ControlledCompletions()
    agent2, bus2 = make_agent(tmp_path, monkeypatch, preserved)
    agent2._store.write_session_metadata("chat-existing", {"title": "Manual title"})
    await agent2._handle_turn_locked(inbound("chat-existing", "different question"))
    assert agent2._store.read_session_metadata("chat-existing")["title"] == "Manual title"
    assert not any(message.metadata.get("_session_updated") for message in outbound_nowait(bus2))


@pytest.mark.asyncio
async def test_legacy_untitled_history_is_not_named_from_a_later_message(
    tmp_path, monkeypatch
):
    completions = ControlledCompletions()
    agent, bus = make_agent(tmp_path, monkeypatch, completions)
    agent._store.append_turn("chat-legacy", "old question", "old answer")

    await agent._handle_turn_locked(inbound("chat-legacy", "new unrelated question"))

    assert "title" not in agent._store.read_session_metadata("chat-legacy")
    assert not any(message.metadata.get("_session_updated") for message in outbound_nowait(bus))


@pytest.mark.asyncio
async def test_manual_rename_survives_later_success_failure_and_inflight_turn(
    tmp_path, monkeypatch
):
    completions = ControlledCompletions(block_calls={4}, fail_calls={3})
    agent, _bus = make_agent(tmp_path, monkeypatch, completions)

    await agent._handle_turn_locked(inbound("chat-rename", "automatic title"))
    assert agent.rename_session("chat-rename", "User title") == "User title"

    await agent._handle_turn_locked(inbound("chat-rename", "successful follow-up"))
    assert agent._store.read_session_metadata("chat-rename")["title"] == "User title"

    await agent._handle_turn_locked(inbound("chat-rename", "failed follow-up"))
    assert agent._store.read_session_metadata("chat-rename")["title"] == "User title"
    assert agent._session_metadata["chat-rename"]["title"] == "User title"

    inflight = asyncio.create_task(
        agent._handle_turn_locked(inbound("chat-rename", "in-flight follow-up"))
    )
    await asyncio.wait_for(completions.started.wait(), timeout=1)
    agent.rename_session("chat-rename", "Renamed in flight")
    completions.release.set()
    await inflight

    assert agent._store.read_session_metadata("chat-rename")["title"] == "Renamed in flight"
    assert agent._session_metadata["chat-rename"]["title"] == "Renamed in flight"


def test_session_api_rename_updates_agent_cache(tmp_path, monkeypatch):
    completions = ControlledCompletions()
    agent, _bus = make_agent(tmp_path, monkeypatch, completions)
    agent._store.write_session_metadata("chat-api", {"title": "Before"})
    agent._session_metadata["chat-api"] = {"title": "Before"}

    app = FastAPI()
    app.state.agent = agent
    app.include_router(sessions_router, prefix="/api")
    client = TestClient(app)

    response = client.patch("/api/sessions/chat-api", json={"title": "  After  "})
    assert response.status_code == 200
    assert response.json() == {"chat_id": "chat-api", "title": "After"}
    assert agent._session_metadata["chat-api"]["title"] == "After"
    assert agent._store.read_session_metadata("chat-api")["title"] == "After"
    assert client.patch("/api/sessions/missing", json={"title": "No"}).status_code == 404
    assert client.patch("/api/sessions/chat-api", json={"title": "  "}).status_code == 422


@pytest.mark.asyncio
async def test_websocket_maps_session_update_metadata():
    channel = WebSocketChannel(MessageBus())
    frames: list[dict] = []

    async def capture(_chat_id: str, payload: dict):
        frames.append(payload)

    channel._fan_out = capture  # type: ignore[method-assign]
    await channel._route_outbound(OutboundMessage(
        channel="websocket",
        chat_id="chat-wire",
        content="",
        metadata={
            "_session_updated": True,
            "_title": "Wire title",
            "_updated_at": "2026-07-26T12:00:00+08:00",
        },
    ))

    assert frames == [{
        "event": "session_updated",
        "chat_id": "chat-wire",
        "title": "Wire title",
        "updated_at": "2026-07-26T12:00:00+08:00",
    }]
