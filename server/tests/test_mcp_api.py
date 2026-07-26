from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mcp import router
from app.mcp.service import MCPManagementService
from app.mcp.store import MCPServerCatalog


class FakeAgent:
    def __init__(self):
        self.configs = {}
        self.statuses = {}

    def get_mcp_status(self, name):
        return self.statuses.get(
            name, {"status": "disconnected", "status_error": None, "tool_count": 0}
        )

    async def replace_mcp_config(self, name, config):
        self.configs[name] = config
        self.statuses[name] = {
            "status": "disconnected",
            "status_error": None,
            "tool_count": 0,
        }

    async def remove_mcp_config(self, name):
        self.configs.pop(name, None)
        self.statuses.pop(name, None)

    async def connect_mcp_server(self, name):
        self.statuses[name] = {
            "status": "connected",
            "status_error": None,
            "tool_count": 2,
        }
        return self.statuses[name]

    async def disconnect_mcp_server(self, name):
        self.statuses[name] = {
            "status": "disconnected",
            "status_error": None,
            "tool_count": 0,
        }
        return self.statuses[name]

    def get_mcp_tools(self, name):
        return {"tools": [], "source": "none", **self.get_mcp_status(name)}


def make_client(tmp_path):
    builtin = tmp_path / "mcp_config.json"
    builtin.write_text(
        json.dumps(
            {
                "builtin": {
                    "type": "sse",
                    "url": "https://builtin.example/sse",
                    "display_name": "Builtin",
                }
            }
        ),
        encoding="utf-8",
    )
    catalog = MCPServerCatalog(builtin, tmp_path / "data" / "mcp" / "servers.json")
    agent = FakeAgent()
    agent.configs.update(catalog.runtime_configs(tmp_path))
    app = FastAPI()
    app.state.mcp_service = MCPManagementService(catalog, agent, tmp_path)
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_api_crud_protection_masking_and_status(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/api/mcp/servers",
        json={
            "name": "secure",
            "type": "sse",
            "display_name": "Secure",
            "description": "Private tools",
            "url": "https://mcp.example/sse",
            "headers": {"Authorization": "secret"},
        },
    )
    assert response.status_code == 201
    assert response.json()["headers"] == {"Authorization": "********"}
    assert response.json()["status"] == "disconnected"

    connected = client.post("/api/mcp/servers/secure/connect")
    assert connected.status_code == 200
    assert connected.json()["connected"] is True
    assert connected.json()["tool_count"] == 2
    tools = client.get("/api/mcp/servers/secure/tools")
    assert tools.status_code == 200
    assert tools.json()["server"] == "secure"
    assert tools.json()["status"] == "connected"

    assert client.put(
        "/api/mcp/servers/builtin",
        json={
            "display_name": "No",
            "url": "https://other.example/sse",
        },
    ).status_code == 403
    assert client.delete("/api/mcp/servers/builtin").status_code == 403
    assert client.delete("/api/mcp/servers/secure").status_code == 204
    assert client.get("/api/mcp/servers/missing/tools").status_code == 404


def test_api_rejects_non_sse_and_collisions(tmp_path):
    client = make_client(tmp_path)
    payload = {
        "name": "bad",
        "type": "stdio",
        "display_name": "Bad",
        "url": "https://mcp.example/sse",
    }
    assert client.post("/api/mcp/servers", json=payload).status_code == 422
    payload.update(name="builtin", type="sse")
    assert client.post("/api/mcp/servers", json=payload).status_code == 409
