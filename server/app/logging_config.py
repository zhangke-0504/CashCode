"""Central logging configuration and correlation context for CashCode."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any, Iterator, Mapping, TextIO


DEFAULT_FILE_LEVEL = "DEBUG"
DEFAULT_CONSOLE_LEVEL = "INFO"
DEFAULT_RETENTION_DAYS = 10
LOG_FILE_NAME = "cashcode.log"

_request_id: ContextVar[str] = ContextVar("cashcode_request_id", default="-")
_chat_id: ContextVar[str] = ContextVar("cashcode_chat_id", default="-")
_turn_id: ContextVar[str] = ContextVar("cashcode_turn_id", default="-")

_CONTEXT_VARS: dict[str, ContextVar[str]] = {
    "request_id": _request_id,
    "chat_id": _chat_id,
    "turn_id": _turn_id,
}
_CONFIG_LOCK = threading.RLock()
_OWNED_HANDLER_MARKER = "_cashcode_owned_handler"
_configured_settings: "LoggingSettings | None" = None

_LABELED_SECRET_RE = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|authorization|cookie|access[_-]?token|"
    r"refresh[_-]?token|secret|password)[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_CONTROL_CHARS_RE = re.compile(r"[\r\n\t]+")
_ARCHIVE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LoggingConfigurationError(RuntimeError):
    """Raised when durable logging cannot be configured safely."""


class SafeLoggedException(RuntimeError):
    """Exception proxy that preserves frames without rendering payload-bearing text."""


def safe_exception_info(
    exc: BaseException,
) -> tuple[type[BaseException], BaseException, TracebackType | None]:
    """Return diagnostic traceback data with the original exception text omitted."""

    proxy = SafeLoggedException(f"{type(exc).__name__}: exception details omitted")
    return SafeLoggedException, proxy, exc.__traceback__


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    log_dir: Path
    file_level: int
    console_level: int
    retention_days: int

    @property
    def log_file(self) -> Path:
        return self.log_dir / LOG_FILE_NAME


def redact_sensitive_text(value: str) -> str:
    """Redact common credential shapes from a fully rendered log record."""

    redacted = _BEARER_RE.sub("Bearer [redacted]", value)
    redacted = _LABELED_SECRET_RE.sub(r"\1[redacted]", redacted)
    return _OPENAI_KEY_RE.sub("sk-[redacted]", redacted)


class RedactingFormatter(logging.Formatter):
    """Render local timestamps and redact the final message plus traceback."""

    def formatTime(  # noqa: N802 - logging.Formatter API
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:
        moment = datetime.fromtimestamp(record.created).astimezone()
        if datefmt:
            return moment.strftime(datefmt)
        return (
            f"{moment:%Y-%m-%d %H:%M:%S}."
            f"{moment.microsecond // 1000:03d} {moment:%z}"
        )

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))


class CorrelationFilter(logging.Filter):
    """Supply fixed correlation fields for every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, context_var in _CONTEXT_VARS.items():
            if not hasattr(record, name):
                setattr(record, name, context_var.get())
        return True


class DynamicStderrHandler(logging.StreamHandler):
    """Follow the current stderr so pytest capture streams can be replaced safely."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._fixed_stream = stream
        super().__init__(stream or sys.stderr)

    def emit(self, record: logging.LogRecord) -> None:
        if self._fixed_stream is None:
            self.stream = sys.stderr
        super().emit(record)


class CashCodeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Daily handler that also enforces calendar retention at startup."""

    def __init__(self, filename: str | Path, *, retention_days: int) -> None:
        self.retention_days = retention_days
        super().__init__(
            filename=str(filename),
            when="midnight",
            interval=1,
            backupCount=max(0, retention_days - 1),
            encoding="utf-8",
            delay=False,
            utc=False,
        )
        self.suffix = "%Y-%m-%d"

    def cleanup_expired_archives(self, *, today: date | None = None) -> list[Path]:
        active_day = today or datetime.now().astimezone().date()
        oldest_retained = active_day - timedelta(days=self.retention_days - 1)
        base_path = Path(self.baseFilename)
        removed: list[Path] = []
        for candidate in base_path.parent.glob(f"{base_path.name}.*"):
            suffix = candidate.name[len(base_path.name) + 1 :]
            if not _ARCHIVE_DATE_RE.fullmatch(suffix):
                continue
            archive_day = date.fromisoformat(suffix)
            if oldest_retained <= archive_day <= active_day:
                continue
            candidate.unlink()
            removed.append(candidate)
        return removed

    def doRollover(self) -> None:  # noqa: N802 - logging.Handler API
        super().doRollover()
        self.cleanup_expired_archives()


def _parse_level(value: str, *, setting_name: str) -> int:
    normalized = value.strip().upper()
    level = logging.getLevelNamesMapping().get(normalized)
    if not isinstance(level, int):
        raise LoggingConfigurationError(
            f"{setting_name} must be a standard logging level, got {value!r}"
        )
    return level


def _parse_retention(value: str) -> int:
    try:
        retention = int(value)
    except ValueError as exc:
        raise LoggingConfigurationError(
            "CASHCODE_LOG_RETENTION_DAYS must be an integer"
        ) from exc
    if not 1 <= retention <= 3650:
        raise LoggingConfigurationError(
            "CASHCODE_LOG_RETENTION_DAYS must be between 1 and 3650"
        )
    return retention


def resolve_logging_settings(
    environ: Mapping[str, str] | None = None,
    *,
    server_root: Path | None = None,
) -> LoggingSettings:
    values = os.environ if environ is None else environ
    root = (server_root or Path(__file__).resolve().parents[1]).resolve()
    configured_dir = values.get("CASHCODE_LOG_DIR", "").strip()
    if configured_dir:
        log_dir = Path(configured_dir).expanduser()
        if not log_dir.is_absolute():
            log_dir = root / log_dir
    else:
        log_dir = root / "logs"
    return LoggingSettings(
        log_dir=log_dir.resolve(),
        file_level=_parse_level(
            values.get("CASHCODE_FILE_LOG_LEVEL", DEFAULT_FILE_LEVEL),
            setting_name="CASHCODE_FILE_LOG_LEVEL",
        ),
        console_level=_parse_level(
            values.get("CASHCODE_CONSOLE_LOG_LEVEL", DEFAULT_CONSOLE_LEVEL),
            setting_name="CASHCODE_CONSOLE_LOG_LEVEL",
        ),
        retention_days=_parse_retention(
            values.get("CASHCODE_LOG_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))
        ),
    )


def _owned_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [
        handler
        for handler in logger.handlers
        if getattr(handler, _OWNED_HANDLER_MARKER, False)
    ]


def _remove_owned_handlers(logger: logging.Logger) -> None:
    for handler in _owned_handlers(logger):
        logger.removeHandler(handler)
        handler.close()


def configure_logging(
    environ: Mapping[str, str] | None = None,
    *,
    server_root: Path | None = None,
    console_stream: TextIO | None = None,
    force: bool = False,
) -> LoggingSettings:
    """Configure CashCode handlers once and return the resolved settings."""

    global _configured_settings

    settings = resolve_logging_settings(environ, server_root=server_root)
    root_logger = logging.getLogger()
    with _CONFIG_LOCK:
        if (
            not force
            and _configured_settings == settings
            and len(_owned_handlers(root_logger)) == 2
        ):
            return settings

        try:
            settings.log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = CashCodeTimedRotatingFileHandler(
                settings.log_file, retention_days=settings.retention_days
            )
            file_handler.cleanup_expired_archives()
        except (OSError, ValueError) as exc:
            message = f"CashCode logging initialization failed: {type(exc).__name__}: {exc}"
            print(redact_sensitive_text(message), file=sys.__stderr__)
            raise LoggingConfigurationError(message) from exc

        formatter = RedactingFormatter(
            "%(asctime)s %(levelname)-8s %(name)s "
            "request_id=%(request_id)s chat_id=%(chat_id)s turn_id=%(turn_id)s "
            "%(message)s"
        )
        context_filter = CorrelationFilter()

        file_handler.setLevel(settings.file_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        setattr(file_handler, _OWNED_HANDLER_MARKER, True)

        console_handler = DynamicStderrHandler(console_stream)
        console_handler.setLevel(settings.console_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(context_filter)
        setattr(console_handler, _OWNED_HANDLER_MARKER, True)

        _remove_owned_handlers(root_logger)
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        for logger_name in ("uvicorn", "uvicorn.error"):
            uvicorn_logger = logging.getLogger(logger_name)
            uvicorn_logger.handlers.clear()
            uvicorn_logger.propagate = True
            uvicorn_logger.setLevel(logging.DEBUG)
            uvicorn_logger.disabled = False
        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        uvicorn_access_logger.handlers.clear()
        uvicorn_access_logger.propagate = False
        uvicorn_access_logger.disabled = True
        for logger_name in ("httpcore", "httpx", "openai", "websockets"):
            logging.getLogger(logger_name).setLevel(logging.WARNING)

        _configured_settings = settings
        return settings


@contextmanager
def log_context(**values: str | None) -> Iterator[None]:
    """Temporarily bind request/chat/turn identifiers in the current context."""

    tokens: list[tuple[ContextVar[str], Token[str]]] = []
    try:
        for name, value in values.items():
            context_var = _CONTEXT_VARS.get(name)
            if context_var is None or value is None:
                continue
            safe_value = _CONTROL_CHARS_RE.sub(" ", str(value)).strip()[:128] or "-"
            tokens.append((context_var, context_var.set(safe_value)))
        yield
    finally:
        for context_var, token in reversed(tokens):
            context_var.reset(token)


def current_log_context() -> dict[str, str]:
    return {name: context_var.get() for name, context_var in _CONTEXT_VARS.items()}


def _format_field_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    text = _CONTROL_CHARS_RE.sub(" ", str(value)).strip()[:500]
    return json.dumps(text, ensure_ascii=False)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    /,
    **fields: Any,
) -> None:
    """Emit a stable key-value event from explicitly selected metadata."""

    suffix = "".join(
        f" {name}={_format_field_value(value)}" for name, value in sorted(fields.items())
    )
    logger.log(level, "event=%s%s", event, suffix)


def reset_logging_for_tests() -> None:
    """Remove only CashCode-owned handlers so tests can isolate configuration."""

    global _configured_settings
    with _CONFIG_LOCK:
        _remove_owned_handlers(logging.getLogger())
        _configured_settings = None
