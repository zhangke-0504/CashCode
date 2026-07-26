from __future__ import annotations

import asyncio
import json
import logging
import re
from types import SimpleNamespace

import pytest
from mcp.types import TextContent

from app.agent.loop import SimpleAgentLoop
from app.agent.runner import SimpleAgentRunner, TurnTrace
from app.agent.tools.base import Tool
from app.agent.tools.mcp import MCPToolWrapper
from app.agent.tools.registry import ToolRegistry
from app.bus.events import InboundMessage
from app.bus.queue import MessageBus
from app.llm.runtime import LLMRuntime, LLMSnapshot
from app.logging_config import configure_logging, reset_logging_for_tests
from app.memory.consolidator import SimpleConsolidator
from app.memory.dream import SimpleDream
from app.memory.store import MemoryStore
from app.paths import DataPaths
from app.skills.evolution import EvolutionConfig, EvolutionService


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)

    async def close(self):
        return None


class PayloadFailingCompletions:
    async def create(self, **kwargs):
        raise RuntimeError(kwargs["messages"][0]["content"])


class PayloadFailingClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=PayloadFailingCompletions())


class PayloadTool(Tool):
    @property
    def name(self) -> str:
        return "payload_tool"

    @property
    def description(self) -> str:
        return "Fixture tool"

    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return "TOOL_RESULT_SENTINEL"


class FailingPayloadTool(PayloadTool):
    @property
    def name(self) -> str:
        return "failing_payload_tool"

    async def execute(self, **kwargs):
        raise RuntimeError(kwargs["secret"])


class FakeMCPSession:
    async def call_tool(self, name, arguments):
        return SimpleNamespace(
            content=[TextContent(type="text", text="MCP_RESULT_SENTINEL")]
        )


class FailingMCPSession:
    async def call_tool(self, name, arguments):
        raise RuntimeError(arguments["secret"])


class ImmediateRunner:
    async def run(self, messages, registry, **kwargs):
        return TurnTrace(
            final_text="AGENT_RESPONSE_SENTINEL",
            iterations=1,
            success=True,
        )


class EmptyCatalog:
    def list(self):
        return []

    def get(self, name):
        return None


@pytest.fixture(autouse=True)
def isolate_cashcode_logging():
    reset_logging_for_tests()
    yield
    reset_logging_for_tests()


def _completion(content: str, *, finish_reason: str = "stop", usage=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def _flush_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


@pytest.mark.asyncio
async def test_llm_tool_and_mcp_events_exclude_inputs_and_outputs(tmp_path):
    settings = configure_logging(
        {"CASHCODE_CONSOLE_LOG_LEVEL": "CRITICAL"}, server_root=tmp_path
    )
    llm_prompt = "LLM_PROMPT_SENTINEL"
    llm_response = "LLM_RESPONSE_SENTINEL"
    llm_client = FakeClient(
        [
            _completion(
                llm_response,
                usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            )
        ]
    )
    snapshot = LLMSnapshot(
        client=llm_client,
        model="fixture-model",
        provider="openai_compatible",
        generation=4,
    )
    runner = object.__new__(SimpleAgentRunner)
    await runner._call_llm(
        snapshot,
        {
            "model": snapshot.model,
            "messages": [{"role": "user", "content": llm_prompt}],
            "stream": False,
        },
        iteration=2,
        purpose="test",
        message_count=1,
        tool_count=0,
    )

    failing_snapshot = LLMSnapshot(
        client=PayloadFailingClient(),
        model="fixture-model",
        provider="openai_compatible",
        generation=5,
    )
    with pytest.raises(RuntimeError):
        await runner._call_llm(
            failing_snapshot,
            {
                "messages": [{"role": "user", "content": "LLM_FAILURE_PAYLOAD"}]
            },
            iteration=3,
            purpose="test_failure",
            message_count=1,
            tool_count=0,
        )

    registry = ToolRegistry()
    registry.register(PayloadTool())
    registry.register(FailingPayloadTool())
    assert await registry.execute(
        "payload_tool", {"secret": "TOOL_ARGUMENT_SENTINEL"}
    ) == "TOOL_RESULT_SENTINEL"
    await registry.execute(
        "failing_payload_tool", {"secret": "TOOL_FAILURE_PAYLOAD"}
    )

    tool_def = SimpleNamespace(
        name="lookup",
        description="Lookup",
        inputSchema={"type": "object", "properties": {}},
    )
    mcp_tool = MCPToolWrapper(FakeMCPSession(), "fixture", tool_def)
    assert await mcp_tool.execute(secret="MCP_ARGUMENT_SENTINEL") == "MCP_RESULT_SENTINEL"
    failing_mcp = MCPToolWrapper(FailingMCPSession(), "fixture", tool_def)
    await failing_mcp.execute(secret="MCP_FAILURE_PAYLOAD")
    _flush_handlers()

    contents = settings.log_file.read_text(encoding="utf-8")
    for event in (
        "event=llm.call.started",
        "event=llm.call.completed",
        "event=llm.call.failed",
        "event=tool.execution.started",
        "event=tool.execution.completed",
        "event=tool.execution.failed",
        "event=mcp.tool.started",
        "event=mcp.tool.completed",
        "event=mcp.tool.failed",
    ):
        assert event in contents
    assert 'provider="openai_compatible"' in contents
    assert 'model="fixture-model"' in contents
    assert "generation=4" in contents
    assert "iteration=2" in contents
    assert "prompt_tokens=7" in contents
    assert "total_tokens=10" in contents
    assert "error_type=RuntimeError" in contents
    for payload in (
        llm_prompt,
        llm_response,
        "LLM_FAILURE_PAYLOAD",
        "TOOL_ARGUMENT_SENTINEL",
        "TOOL_RESULT_SENTINEL",
        "TOOL_FAILURE_PAYLOAD",
        "MCP_ARGUMENT_SENTINEL",
        "MCP_RESULT_SENTINEL",
        "MCP_FAILURE_PAYLOAD",
    ):
        assert payload not in contents


@pytest.mark.asyncio
async def test_agent_turn_events_share_chat_and_turn_context_without_content(
    tmp_path, monkeypatch
):
    settings = configure_logging(
        {"CASHCODE_CONSOLE_LOG_LEVEL": "CRITICAL"}, server_root=tmp_path
    )
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    runtime = LLMRuntime.from_client(FakeClient([]), "fixture-model")
    bus = MessageBus()
    agent = SimpleAgentLoop(
        bus,
        data_paths=DataPaths.from_environment(default_root=tmp_path / "data"),
        llm_runtime=runtime,
    )
    agent._runner = ImmediateRunner()
    message = InboundMessage(
        channel="websocket",
        sender_id="fixture",
        chat_id="chat-logging-fixture",
        content="AGENT_USER_PAYLOAD_SENTINEL",
        metadata={
            "llm": {"provider": "openai_compatible", "model": "fixture-model"}
        },
    )

    await agent._handle_turn(message)
    _flush_handlers()
    contents = settings.log_file.read_text(encoding="utf-8")
    turn_lines = [line for line in contents.splitlines() if "event=agent.turn." in line]
    assert any("event=agent.turn.started" in line for line in turn_lines)
    assert any("event=agent.turn.completed" in line for line in turn_lines)
    assert all("chat_id=chat-logging-fixture" in line for line in turn_lines)
    turn_ids = {
        re.search(r"turn_id=([0-9a-f]{32})", line).group(1)  # type: ignore[union-attr]
        for line in turn_lines
    }
    assert len(turn_ids) == 1
    assert "content_chars=27" in contents
    assert "AGENT_USER_PAYLOAD_SENTINEL" not in contents
    assert "AGENT_RESPONSE_SENTINEL" not in contents
    await runtime.close()


@pytest.mark.asyncio
async def test_background_events_cover_completion_skip_and_safe_counts(tmp_path):
    settings = configure_logging(
        {"CASHCODE_CONSOLE_LOG_LEVEL": "CRITICAL"}, server_root=tmp_path
    )
    store = MemoryStore(tmp_path / "memory")
    store.append_turn(
        "chat-background",
        "BACKGROUND_USER_PAYLOAD",
        "BACKGROUND_ASSISTANT_PAYLOAD",
    )
    dream_client = FakeClient(
        [
            _completion("DREAM_ANALYSIS_PAYLOAD"),
            _completion("DREAM_MEMORY_PAYLOAD"),
        ]
    )
    dream_runtime = LLMRuntime.from_client(dream_client, "fixture-model")
    assert await SimpleDream(dream_runtime, store).run() is True

    store.append_turn(
        "chat-consolidator",
        "CONSOLIDATOR_USER_PAYLOAD",
        "CONSOLIDATOR_ASSISTANT_PAYLOAD",
    )
    store.append_turn(
        "chat-consolidator",
        "CONSOLIDATOR_SECOND_USER_PAYLOAD",
        "CONSOLIDATOR_SECOND_ASSISTANT_PAYLOAD",
    )
    history, _ = store.load_history_smart("chat-consolidator")
    consolidator_client = FakeClient([_completion("CONSOLIDATOR_SUMMARY_PAYLOAD")])
    consolidator_runtime = LLMRuntime.from_client(
        consolidator_client, "fixture-model"
    )
    consolidator = SimpleConsolidator(
        consolidator_runtime, store, char_threshold=1
    )
    plan = consolidator.prepare("chat-consolidator", history)
    assert plan is not None
    assert await consolidator.consolidate(plan) is True

    proposal_payload = {
        "action": "create",
        "name": "generated-fixture",
        "candidate_content": (
            "---\nname: generated-fixture\n"
            "description: Generated fixture\n---\n\n"
            "# Steps\n\nEVOLUTION_CANDIDATE_PAYLOAD\n"
        ),
        "reason": "recurring workflow",
    }
    evolution_client = FakeClient([_completion(json.dumps(proposal_payload))])
    evolution_runtime = LLMRuntime.from_client(evolution_client, "fixture-model")
    evolution = EvolutionService(
        evolution_runtime,
        EmptyCatalog(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        tmp_path / "evolution",
        EvolutionConfig(enabled=True, min_tool_calls=1, recurrence=2),
    )
    for _ in range(2):
        evolution.schedule_turn(
            chat_id="chat-evolution",
            user_content="EVOLUTION_USER_PAYLOAD",
            final_content="EVOLUTION_RESPONSE_PAYLOAD",
            tools_used=["fixture_tool"],
            durable_messages=[
                {"role": "tool", "content": "EVOLUTION_TOOL_PAYLOAD"}
            ],
            persisted=True,
            provider="openai_compatible",
            model="fixture-model",
        )
        await asyncio.gather(*tuple(evolution._tasks))
        await asyncio.sleep(0)
    await evolution.close()
    await dream_runtime.close()
    await consolidator_runtime.close()
    await evolution_runtime.close()
    _flush_handlers()

    contents = settings.log_file.read_text(encoding="utf-8")
    for event in (
        "event=dream.run.started",
        "event=dream.run.completed",
        "event=consolidator.run.prepared",
        "event=consolidator.run.started",
        "event=consolidator.run.completed",
        "event=skill_evolution.turn.started",
        "event=skill_evolution.turn.skipped",
        "event=skill_evolution.turn.completed",
        "event=skill_evolution.proposal.created",
    ):
        assert event in contents
    assert "duration_ms=" in contents
    assert "entry_count=2" in contents
    assert "proposal_created=true" in contents
    for payload in (
        "BACKGROUND_USER_PAYLOAD",
        "BACKGROUND_ASSISTANT_PAYLOAD",
        "DREAM_ANALYSIS_PAYLOAD",
        "DREAM_MEMORY_PAYLOAD",
        "CONSOLIDATOR_USER_PAYLOAD",
        "CONSOLIDATOR_ASSISTANT_PAYLOAD",
        "CONSOLIDATOR_SECOND_USER_PAYLOAD",
        "CONSOLIDATOR_SECOND_ASSISTANT_PAYLOAD",
        "CONSOLIDATOR_SUMMARY_PAYLOAD",
        "EVOLUTION_USER_PAYLOAD",
        "EVOLUTION_RESPONSE_PAYLOAD",
        "EVOLUTION_TOOL_PAYLOAD",
        "EVOLUTION_CANDIDATE_PAYLOAD",
    ):
        assert payload not in contents
