from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.agent.loop import SimpleAgentLoop
from app.agent.runner import TurnTrace
from app.bus.events import InboundMessage
from app.bus.queue import MessageBus
from app.llm.runtime import LLMRuntime
from app.memory.consolidator import ConsolidationPlan, SimpleConsolidator
from app.memory.dream import SimpleDream
from app.memory.store import MemoryStore
from app.paths import DataPaths


def completion(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class FakeClient:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.slow = False
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **_kwargs):
        if self.slow:
            await asyncio.Event().wait()
        return self.responses.pop(0)

    async def close(self):
        return None


class ImmediateRunner:
    async def run(self, messages, _registry, **_kwargs):
        return TurnTrace(final_text=f"reply: {messages[-1]['content']}")


class BlockingConsolidator:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()

    def prepare(self, chat_id, _history):
        return ConsolidationPlan(chat_id, [], 0, None)

    async def consolidate(self, _plan, **_kwargs):
        self.started.set()
        try:
            await self.release.wait()
            return False
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class BlockingSummaryClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def create(self, **_kwargs):
        self.started.set()
        await self.release.wait()
        return completion("captured summary")


class FailingClient(FakeClient):
    async def create(self, **_kwargs):
        raise ValueError("fixture programming failure")


async def consume_done(bus: MessageBus, chat_id: str):
    while True:
        message = await asyncio.wait_for(bus.consume_outbound(), timeout=1)
        if message.chat_id == chat_id and message.metadata.get("_turn_done"):
            return message


def inbound(chat_id: str, content: str) -> InboundMessage:
    return InboundMessage(
        channel="websocket",
        sender_id="fixture",
        chat_id=chat_id,
        content=content,
        metadata={"llm": {"provider": "openai_compatible", "model": "model-a"}},
    )


@pytest.mark.asyncio
async def test_turn_done_and_later_turn_do_not_wait_for_consolidation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    runtime = LLMRuntime.from_client(FakeClient(), "model-a")
    bus = MessageBus()
    agent = SimpleAgentLoop(
        bus,
        data_paths=DataPaths.from_environment(default_root=tmp_path / "data"),
        llm_runtime=runtime,
    )
    blocker = BlockingConsolidator()
    agent._runner = ImmediateRunner()
    agent._consolidator = blocker

    await asyncio.wait_for(agent._handle_turn(inbound("chat-a", "first")), timeout=1)
    first_done = await consume_done(bus, "chat-a")
    await asyncio.wait_for(blocker.started.wait(), timeout=1)
    assert first_done.content == "reply: first"
    assert not blocker.release.is_set()

    await asyncio.wait_for(agent._handle_turn(inbound("chat-a", "second")), timeout=1)
    second_done = await consume_done(bus, "chat-a")
    assert second_done.content == "reply: second"

    blocker.release.set()
    await asyncio.gather(*tuple(agent._auxiliary_tasks))
    await runtime.close()


@pytest.mark.asyncio
async def test_late_consolidation_commit_preserves_newer_turns(tmp_path, monkeypatch):
    memory_root = tmp_path / "memory"
    monkeypatch.setenv("MEMORY_DIR", str(memory_root))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    store = MemoryStore(memory_root)
    store.append_turn("chat-a", "old one", "answer one")
    store.append_turn("chat-a", "old two", "answer two")
    client = BlockingSummaryClient()
    runtime = LLMRuntime.from_client(client, "model-a")
    bus = MessageBus()
    agent = SimpleAgentLoop(
        bus,
        data_paths=DataPaths.from_environment(default_root=tmp_path / "data"),
        llm_runtime=runtime,
    )
    agent._runner = ImmediateRunner()
    agent._consolidator = SimpleConsolidator(
        runtime,
        agent._store,
        char_threshold=1,
        operation_timeout=2,
    )

    await agent._handle_turn(inbound("chat-a", "first new"))
    await consume_done(bus, "chat-a")
    await asyncio.wait_for(client.started.wait(), timeout=1)

    await asyncio.wait_for(agent._handle_turn(inbound("chat-a", "second new")), timeout=1)
    await consume_done(bus, "chat-a")
    client.release.set()
    await asyncio.gather(*tuple(agent._auxiliary_tasks))

    contents = [message.get("content", "") for message in agent._sessions["chat-a"]]
    assert "second new" in contents
    assert "reply: second new" in contents
    assert contents[0] == "[历史摘要] captured summary"
    await runtime.close()


@pytest.mark.asyncio
async def test_agent_shutdown_cancels_and_awaits_auxiliary_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    runtime = LLMRuntime.from_client(FakeClient(), "model-a")
    bus = MessageBus()
    agent = SimpleAgentLoop(
        bus,
        data_paths=DataPaths.from_environment(default_root=tmp_path / "data"),
        llm_runtime=runtime,
    )
    blocker = BlockingConsolidator()
    agent._runner = ImmediateRunner()
    agent._consolidator = blocker
    run_task = asyncio.create_task(agent.run())

    await bus.publish_inbound(inbound("chat-a", "first"))
    await consume_done(bus, "chat-a")
    await asyncio.wait_for(blocker.started.wait(), timeout=1)
    agent.stop()
    await asyncio.wait_for(run_task, timeout=2)

    assert blocker.cancelled.is_set()
    assert not agent._auxiliary_tasks
    assert not agent._consolidation_tasks
    await runtime.close()


def test_consolidator_uses_production_threshold_and_allows_test_override(tmp_path):
    store = MemoryStore(tmp_path)
    runtime = LLMRuntime.from_client(FakeClient(), "model-a")
    history = [
        {"role": "user", "content": "12345"},
        {"role": "assistant", "content": "67890"},
        {"role": "user", "content": "abcde"},
        {"role": "assistant", "content": "fghij"},
    ]

    assert SimpleConsolidator.CHAR_THRESHOLD == 40_000
    assert SimpleConsolidator(runtime, store).prepare("chat-a", history) is None
    assert SimpleConsolidator(runtime, store, char_threshold=1).prepare("chat-a", history)


@pytest.mark.asyncio
async def test_consolidation_timeout_does_not_persist_summary(tmp_path, caplog):
    store = MemoryStore(tmp_path)
    store.append_turn("chat-a", "old question", "old answer")
    store.append_turn("chat-a", "new question", "new answer")
    history, _ = store.load_history_smart("chat-a")
    client = FakeClient()
    client.slow = True
    runtime = LLMRuntime.from_client(client, "model-a")
    consolidator = SimpleConsolidator(
        runtime,
        store,
        char_threshold=1,
        operation_timeout=0.01,
    )
    plan = consolidator.prepare("chat-a", history)
    assert plan is not None

    with caplog.at_level(logging.WARNING):
        assert await consolidator.consolidate(plan) is False

    assert all(entry.get("role") != "summary" for entry in store._read_raw_entries("chat-a"))
    record = next(record for record in caplog.records if "provider request failed" in record.message)
    assert record.exc_info is None
    await runtime.close()


@pytest.mark.asyncio
async def test_unexpected_consolidation_failure_keeps_diagnostic_traceback(tmp_path, caplog):
    store = MemoryStore(tmp_path)
    store.append_turn("chat-a", "old question", "old answer")
    store.append_turn("chat-a", "new question", "new answer")
    history, _ = store.load_history_smart("chat-a")
    runtime = LLMRuntime.from_client(FailingClient(), "model-a")
    consolidator = SimpleConsolidator(runtime, store, char_threshold=1)
    plan = consolidator.prepare("chat-a", history)
    assert plan is not None

    with caplog.at_level(logging.WARNING):
        assert await consolidator.consolidate(plan) is False

    record = next(record for record in caplog.records if "summarization failed" in record.message)
    assert record.exc_info is not None
    assert all(entry.get("role") != "summary" for entry in store._read_raw_entries("chat-a"))
    await runtime.close()


@pytest.mark.asyncio
async def test_dream_timeout_keeps_cursor_and_retries_same_entries(tmp_path, caplog):
    store = MemoryStore(tmp_path)
    store.append_turn("chat-a", "remember this", "noted")
    client = FakeClient([completion("analysis"), completion("# Memory\nRemembered")])
    client.slow = True
    runtime = LLMRuntime.from_client(client, "model-a")
    dream = SimpleDream(runtime, store, operation_timeout=0.01)

    with caplog.at_level(logging.WARNING):
        assert await dream.run() is False

    assert store.read_memory() == ""
    assert store.get_dream_cursors() == {}
    record = next(record for record in caplog.records if "Phase 1 provider request failed" in record.message)
    assert record.exc_info is None

    client.slow = False
    assert await dream.run() is True
    assert store.read_memory() == "# Memory\nRemembered"
    assert store.get_dream_cursors()["chat-a"] == 2
    await runtime.close()
