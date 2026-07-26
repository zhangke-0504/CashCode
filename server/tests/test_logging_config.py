from __future__ import annotations

import io
import logging
from datetime import date, datetime, time as datetime_time, timedelta

import pytest

from app.logging_config import (
    CashCodeTimedRotatingFileHandler,
    LoggingConfigurationError,
    configure_logging,
    log_context,
    reset_logging_for_tests,
)


@pytest.fixture(autouse=True)
def isolate_cashcode_logging():
    reset_logging_for_tests()
    yield
    reset_logging_for_tests()


def _flush_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def _owned_handlers() -> list[logging.Handler]:
    return [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_cashcode_owned_handler", False)
    ]


def test_first_start_levels_utf8_idempotency_and_same_day_append(tmp_path):
    console = io.StringIO()
    settings = configure_logging({}, server_root=tmp_path, console_stream=console)
    logger = logging.getLogger("cashcode.tests.logging")
    logger.debug("debug-only")
    logger.info("unicode-info=日志正常")
    _flush_handlers()

    assert settings.log_dir == tmp_path / "logs"
    assert settings.log_file.is_file()
    first_handlers = _owned_handlers()
    assert len(first_handlers) == 2
    assert "debug-only" in settings.log_file.read_text(encoding="utf-8")
    assert "debug-only" not in console.getvalue()
    assert "unicode-info=日志正常" in console.getvalue()

    same_settings = configure_logging({}, server_root=tmp_path)
    assert same_settings == settings
    assert _owned_handlers() == first_handlers

    reset_logging_for_tests()
    configure_logging({}, server_root=tmp_path, console_stream=io.StringIO())
    logger.info("restart-appended")
    _flush_handlers()
    contents = settings.log_file.read_text(encoding="utf-8")
    assert "unicode-info=日志正常" in contents
    assert "restart-appended" in contents


def test_level_overrides_are_applied_independently(tmp_path):
    console = io.StringIO()
    settings = configure_logging(
        {
            "CASHCODE_FILE_LOG_LEVEL": "INFO",
            "CASHCODE_CONSOLE_LOG_LEVEL": "ERROR",
        },
        server_root=tmp_path,
        console_stream=console,
    )
    logger = logging.getLogger("cashcode.tests.levels")
    logger.debug("hidden-debug")
    logger.info("file-info")
    logger.error("console-error")
    _flush_handlers()

    contents = settings.log_file.read_text(encoding="utf-8")
    assert "hidden-debug" not in contents
    assert "file-info" in contents
    assert "file-info" not in console.getvalue()
    assert "console-error" in console.getvalue()


def test_configuration_fails_when_log_directory_is_unavailable(tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")

    with pytest.raises(LoggingConfigurationError):
        configure_logging(
            {"CASHCODE_LOG_DIR": str(blocked)},
            server_root=tmp_path,
        )


def test_retention_keeps_exact_calendar_window_and_unrelated_files(tmp_path):
    runtime_dir = tmp_path / "server" / "logs"
    runtime_dir.mkdir(parents=True)
    server_test_log = tmp_path / "server" / "pytest_logs" / "pytest.log"
    client_log = tmp_path / "client" / "logs" / "vite.log"
    server_test_log.parent.mkdir(parents=True)
    client_log.parent.mkdir(parents=True)
    server_test_log.write_text("server test", encoding="utf-8")
    client_log.write_text("client test", encoding="utf-8")
    unrelated = runtime_dir / "cashcode.log.notes"
    unrelated.write_text("keep", encoding="utf-8")

    today = date(2026, 7, 26)
    archives = {}
    for age in range(13):
        archive = runtime_dir / f"cashcode.log.{today - timedelta(days=age):%Y-%m-%d}"
        archive.write_text(str(age), encoding="utf-8")
        archives[age] = archive

    handler = CashCodeTimedRotatingFileHandler(
        runtime_dir / "cashcode.log", retention_days=10
    )
    try:
        removed = handler.cleanup_expired_archives(today=today)
    finally:
        handler.close()

    assert {path.name for path in removed} == {
        archives[10].name,
        archives[11].name,
        archives[12].name,
    }
    assert all(archives[age].exists() for age in range(10))
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert server_test_log.read_text(encoding="utf-8") == "server test"
    assert client_log.read_text(encoding="utf-8") == "client test"


def test_startup_and_rollover_cleanup_use_date_suffixes(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    today = date.today()
    startup_expired = log_dir / f"cashcode.log.{today - timedelta(days=10):%Y-%m-%d}"
    startup_expired.write_text("expired", encoding="utf-8")

    settings = configure_logging({}, server_root=tmp_path)
    assert not startup_expired.exists()
    reset_logging_for_tests()

    rollover_expired = log_dir / f"cashcode.log.{today - timedelta(days=20):%Y-%m-%d}"
    rollover_expired.write_text("expired", encoding="utf-8")
    handler = CashCodeTimedRotatingFileHandler(settings.log_file, retention_days=10)
    try:
        handler.stream.write("before rollover\n")
        handler.stream.flush()
        handler.rolloverAt = int(
            datetime.combine(today, datetime_time.min).timestamp()
        )
        handler.doRollover()
    finally:
        handler.close()

    archive = log_dir / f"cashcode.log.{today - timedelta(days=1):%Y-%m-%d}"
    assert archive.read_text(encoding="utf-8") == "before rollover\n"
    assert settings.log_file.is_file()
    assert not rollover_expired.exists()


def test_correlation_defaults_binding_and_final_format_redaction(tmp_path):
    settings = configure_logging(
        {"CASHCODE_CONSOLE_LOG_LEVEL": "CRITICAL"},
        server_root=tmp_path,
    )
    logger = logging.getLogger("cashcode.tests.redaction")
    logger.info("default-context")
    with log_context(request_id="req-123", chat_id="chat-456", turn_id="turn-789"):
        logger.warning(
            "normal-secrets api_key=NORMAL_SECRET Authorization: Bearer BEARER_SECRET "
            "cookie=COOKIE_SECRET sk-abcdefghijk"
        )
        try:
            raise RuntimeError("password=TRACE_SECRET")
        except RuntimeError:
            logger.exception("exception-secret")
    _flush_handlers()

    contents = settings.log_file.read_text(encoding="utf-8")
    assert "request_id=- chat_id=- turn_id=- default-context" in contents
    assert "request_id=req-123 chat_id=chat-456 turn_id=turn-789" in contents
    for secret in (
        "NORMAL_SECRET",
        "BEARER_SECRET",
        "COOKIE_SECRET",
        "abcdefghijk",
        "TRACE_SECRET",
    ):
        assert secret not in contents
    assert "[redacted]" in contents
