from __future__ import annotations

import logging
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.http_logging import http_request_logging
from app.logging_config import configure_logging, reset_logging_for_tests


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(http_request_logging)

    @app.post("/items/{item_id}")
    async def item(item_id: str, request: Request):
        await request.body()
        return {"item_id": item_id}

    @app.get("/teapot")
    async def teapot():
        raise HTTPException(status_code=418, detail="short and stout")

    @app.get("/explode")
    async def explode():
        raise RuntimeError("request handler failed")

    return app


def _summaries(caplog):
    return [
        record.getMessage()
        for record in caplog.records
        if "event=http.request." in record.getMessage()
    ]


def test_http_summary_uses_route_template_and_omits_request_payload(caplog):
    payload = "REQUEST_BODY_SENTINEL"
    with caplog.at_level(logging.INFO, logger="app.http_logging"):
        response = TestClient(_app()).post(
            "/items/private-item?token=QUERY_SENTINEL",
            content=payload,
        )

    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    summaries = _summaries(caplog)
    assert len(summaries) == 1
    assert "event=http.request.completed" in summaries[0]
    assert 'method="POST"' in summaries[0]
    assert 'route="/items/{item_id}"' in summaries[0]
    assert "status=200" in summaries[0]
    assert "duration_ms=" in summaries[0]
    assert payload not in caplog.text
    assert "private-item" not in caplog.text
    assert "QUERY_SENTINEL" not in caplog.text


def test_http_errors_emit_one_summary_and_return_request_id(caplog):
    client = TestClient(_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="app.http_logging"):
        teapot = client.get("/teapot")
    assert teapot.status_code == 418
    assert len(_summaries(caplog)) == 1
    assert "status=418" in _summaries(caplog)[0]

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.http_logging"):
        failed = client.get("/explode")
    assert failed.status_code == 500
    assert failed.json()["request_id"] == failed.headers["X-Request-ID"]
    summaries = _summaries(caplog)
    assert len(summaries) == 1
    assert "event=http.request.failed" in summaries[0]
    assert "status=500" in summaries[0]
    assert "error_type=RuntimeError" in summaries[0]


def test_uvicorn_error_uses_root_handlers_and_raw_access_is_disabled(tmp_path):
    reset_logging_for_tests()
    settings = configure_logging(
        {"CASHCODE_CONSOLE_LOG_LEVEL": "CRITICAL"},
        server_root=tmp_path,
    )
    try:
        error_logger = logging.getLogger("uvicorn.error")
        access_logger = logging.getLogger("uvicorn.access")
        assert error_logger.handlers == []
        assert error_logger.propagate is True
        assert access_logger.handlers == []
        assert access_logger.propagate is False
        assert access_logger.disabled is True

        error_logger.error("UVICORN_ERROR_SENTINEL")
        access_logger.info("UVICORN_ACCESS_SENTINEL")
        for handler in logging.getLogger().handlers:
            handler.flush()
        contents = settings.log_file.read_text(encoding="utf-8")
        assert "UVICORN_ERROR_SENTINEL" in contents
        assert "UVICORN_ACCESS_SENTINEL" not in contents
    finally:
        reset_logging_for_tests()
