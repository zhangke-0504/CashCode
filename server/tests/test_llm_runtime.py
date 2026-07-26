from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agent.loop import SimpleAgentLoop
from app.agent.runner import SimpleAgentRunner
from app.agent.tools.base import Tool
from app.agent.tools.registry import ToolRegistry
from app.bus.events import InboundMessage
from app.bus.queue import MessageBus
from app.llm.models import LLMNotConfiguredError, LLMSettings, OllamaProfile, OpenAICompatibleProfile
from app.llm.models import RuntimeProviderConfig
from app.llm.runtime import LLMRuntime, _default_client_factory, _uses_loopback_ollama_transport
import app.llm.runtime as runtime_module
from app.paths import DataPaths


def settings(key: str, *, ollama: bool = False) -> LLMSettings:
    return LLMSettings.create(
        openai_compatible=OpenAICompatibleProfile.create(
            base_url="https://provider.example",
            api_key=key,
        ),
        ollama=OllamaProfile.create(
            base_url="http://127.0.0.1:11434" if ollama else ""
        ),
    )


class FakeClient:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []
        self.closed = False
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

    async def close(self):
        self.closed = True


def response(content: str = "", tool_call=None):
    message = SimpleNamespace(content=content, tool_calls=[tool_call] if tool_call else [])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=json.dumps(arguments))

    def model_dump(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


@pytest.mark.asyncio
async def test_runtime_retires_provider_client_only_after_last_lease_releases():
    clients = []

    def factory(_config):
        client = FakeClient()
        clients.append(client)
        return client

    runtime = LLMRuntime(client_factory=factory)
    await runtime.install(settings("key-one"))

    async with runtime.acquire("openai_compatible", "model-one") as old_snapshot:
        await runtime.install(settings("key-two"))
        assert old_snapshot.model == "model-one"
        assert clients[0].closed is False

        async with runtime.acquire("openai_compatible", "model-two") as new_snapshot:
            assert new_snapshot.model == "model-two"

    assert clients[0].closed is True
    assert clients[1].closed is False
    await runtime.close()
    assert clients[1].closed is True


@pytest.mark.asyncio
async def test_runtime_routes_selection_to_provider_specific_generation():
    by_provider = {}

    def factory(config):
        client = FakeClient()
        by_provider[config.provider] = client
        return client

    runtime = LLMRuntime(client_factory=factory)
    await runtime.install(settings("key", ollama=True))
    async with runtime.acquire("ollama", "qwen3") as snapshot:
        assert snapshot.client is by_provider["ollama"]
        assert snapshot.model == "qwen3"
    assert runtime.last_selection == ("ollama", "qwen3")


@pytest.mark.asyncio
async def test_unconfigured_runtime_raises_stable_error():
    runtime = LLMRuntime()

    with pytest.raises(LLMNotConfiguredError, match="LLM 未配置"):
        async with runtime.acquire("openai_compatible", "model-a"):
            pass


@pytest.mark.asyncio
async def test_runner_pins_snapshot_across_credential_switch():
    switch_call = FakeToolCall("switch-1", "switch_provider", {})
    old_client = FakeClient([response(tool_call=switch_call), response("old finished")])
    new_client = FakeClient([response("new response")])
    clients = [old_client, new_client]

    def factory(_config):
        return clients.pop(0)

    runtime = LLMRuntime(client_factory=factory)
    await runtime.install(settings("old-key"))

    class SwitchProviderTool(Tool):
        @property
        def name(self):
            return "switch_provider"

        @property
        def description(self):
            return "Switch credentials during the fixture turn"

        def parameters(self):
            return {"type": "object", "properties": {}}

        async def execute(self, **_kwargs):
            await runtime.install(settings("new-key"))
            return "switched"

    registry = ToolRegistry()
    registry.register(SwitchProviderTool())
    trace = await SimpleAgentRunner(runtime).run(
        [{"role": "user", "content": "switch"}],
        registry,
        provider="openai_compatible",
        model="chosen-model",
    )

    assert trace.final_text == "old finished"
    assert [call["model"] for call in old_client.calls] == ["chosen-model", "chosen-model"]
    assert new_client.calls == []
    await runtime.close()


@pytest.mark.asyncio
async def test_unconfigured_agent_turn_is_recoverable_and_not_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    paths = DataPaths.from_environment(default_root=tmp_path / "data")
    bus = MessageBus()
    agent = SimpleAgentLoop(bus, data_paths=paths, llm_runtime=LLMRuntime())

    await agent._handle_turn_locked(InboundMessage(
        channel="websocket",
        sender_id="fixture",
        chat_id="chat-unconfigured",
        content="hello",
        metadata={"llm": {"provider": "openai_compatible", "model": "model-a"}},
    ))
    outbound = await bus.consume_outbound()

    assert outbound.metadata == {"_user_error": True}
    assert "LLM 未配置" in outbound.content
    assert "chat-unconfigured" not in agent._sessions
    assert not (tmp_path / "memory" / "chat-unconfigured" / "history.jsonl").exists()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.2:11434/v1",
        "http://[::1]:11434/v1",
    ],
)
def test_loopback_ollama_transport_detection(base_url):
    assert _uses_loopback_ollama_transport(
        RuntimeProviderConfig("ollama", base_url, "ollama-local")
    )


def test_remote_and_generic_providers_keep_standard_transport():
    assert not _uses_loopback_ollama_transport(
        RuntimeProviderConfig("ollama", "http://ollama.internal:11434/v1", "ollama-local")
    )
    assert not _uses_loopback_ollama_transport(
        RuntimeProviderConfig("openai_compatible", "http://127.0.0.1:8000/v1", "key")
    )


def test_default_factory_disables_environment_proxy_only_for_loopback_ollama(monkeypatch):
    clients = []

    def fake_http_client(**kwargs):
        client = SimpleNamespace(options=kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(runtime_module.httpx, "AsyncClient", fake_http_client)
    monkeypatch.setattr(runtime_module, "AsyncOpenAI", lambda **kwargs: kwargs)

    local = _default_client_factory(
        RuntimeProviderConfig("ollama", "http://127.0.0.1:11434/v1", "ollama-local")
    )
    remote = _default_client_factory(
        RuntimeProviderConfig("ollama", "http://ollama.internal:11434/v1", "ollama-local")
    )

    assert local["http_client"] is clients[0]
    assert clients[0].options == {"trust_env": False}
    assert "http_client" not in remote
