from __future__ import annotations

import json

import pytest

from app.mcp.models import (
    MASKED_HEADER_VALUE,
    MCPConflictError,
    MCPPermissionError,
    MCPValidationError,
)
from app.mcp.store import MCPServerCatalog


@pytest.fixture
def catalog(tmp_path):
    builtin = tmp_path / "mcp_config.json"
    builtin.write_text(
        json.dumps(
            {
                "local": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["server.py"],
                    "display_name": "Local",
                },
                "remote": {
                    "type": "sse",
                    "url": "https://example.com/sse",
                    "display_name": "Remote",
                },
            }
        ),
        encoding="utf-8",
    )
    return MCPServerCatalog(builtin, tmp_path / "data" / "mcp" / "servers.json")


def test_catalog_merges_builtins_and_atomically_persisted_users(catalog):
    created = catalog.create(
        {
            "name": "weather",
            "type": "sse",
            "display_name": "Weather",
            "description": "Forecast tools",
            "url": "https://mcp.example/sse",
            "headers": {"Authorization": "Bearer secret"},
        }
    )

    assert [row.name for row in catalog.list()] == ["local", "remote", "weather"]
    assert created.to_public()["headers"] == {"Authorization": MASKED_HEADER_VALUE}
    assert not list(catalog.user_path.parent.glob(".*.tmp"))

    reloaded = MCPServerCatalog(catalog.builtin_path, catalog.user_path)
    assert reloaded.get("weather").headers["Authorization"] == "Bearer secret"


def test_masked_header_is_preserved_on_update(catalog):
    catalog.create(
        {
            "name": "secure",
            "display_name": "Secure",
            "url": "https://mcp.example/sse",
            "headers": {"Authorization": "secret"},
        }
    )
    updated = catalog.update(
        "secure",
        {
            "display_name": "Secure v2",
            "url": "https://mcp.example/sse",
            "headers": {"Authorization": MASKED_HEADER_VALUE},
        },
    )
    assert updated.headers == {"Authorization": "secret"}


def test_catalog_rejects_builtin_mutation_collision_and_non_sse(catalog):
    with pytest.raises(MCPPermissionError):
        catalog.update("local", {"display_name": "No", "url": "https://x/sse"})
    with pytest.raises(MCPPermissionError):
        catalog.delete("local")
    with pytest.raises(MCPConflictError):
        catalog.create(
            {"name": "remote", "display_name": "Other", "url": "https://x/sse"}
        )
    with pytest.raises(MCPValidationError):
        catalog.create(
            {
                "name": "bad",
                "type": "stdio",
                "display_name": "Bad",
                "url": "https://x/sse",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Bad Name", "display_name": "Bad", "url": "https://x/sse"},
        {"name": "bad", "display_name": "", "url": "https://x/sse"},
        {"name": "bad", "display_name": "Bad", "url": "file:///tmp/mcp"},
        {
            "name": "bad",
            "display_name": "Bad",
            "url": "https://x/sse",
            "headers": {"Authorization": "bad\nvalue"},
        },
    ],
)
def test_catalog_validates_user_payload(catalog, payload):
    with pytest.raises(MCPValidationError):
        catalog.create(payload)
