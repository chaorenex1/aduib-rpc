from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Mapping

__all__ = ["LEVEL_NAME_TO_INT", "LOG_FORMAT_CONSOLE", "LOG_FORMAT_ENV", "LOG_FORMAT_JSON", "LogContext", "StructuredConsoleFormatter", "StructuredJSONFormatter", "StructuredLogger", "get_logger"]


LOG_FORMAT_ENV = "Aduib_RPC_LOG_FORMAT"
LOG_FORMAT_JSON = "json"
LOG_FORMAT_CONSOLE = "console"

LEVEL_NAME_TO_INT: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_DEFAULT_CONTEXT_KEYS = ("tenant_id", "trace_id", "request_id")
_LOG_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("aduib_rpc_log_context")

_DEFAULT_CONSOLE_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s tenant_id=%(tenant_id)s trace_id=%(trace_id)s request_id=%(request_id)s"

_RESERVED_FIELDS = {"timestamp", "level", "logger", "message", "exception", "stack"}

_LOG_RECORD_ATTRS = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process", "message", "asctime"}


def _normalize_log_format(value: str | None) -> str:
    if not value:
        return LOG_FORMAT_JSON
    normalized = value.strip().lower()
    if normalized in {LOG_FORMAT_JSON, LOG_FORMAT_CONSOLE}:
        return normalized
    return LOG_FORMAT_JSON


def _json_default(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return repr(value)


def _extract_extras(record: logging.LogRecord) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _LOG_RECORD_ATTRS or key.startswith("_"):
            continue
        extras[key] = value
    return extras


def _merge_context(
    base: Mapping[str, Any],
    updates: Mapping[str, Any],
    *,
    ignore_none: bool = True,
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if ignore_none and value is None:
            continue
        merged[key] = value
    return merged


def _context_snapshot() -> dict[str, Any]:
    current = _LOG_CONTEXT.get({})
    snapshot: dict[str, Any] = {key: current.get(key) for key in _DEFAULT_CONTEXT_KEYS}
    for key, value in current.items():
        if key not in snapshot:
            snapshot[key] = value
    return snapshot


def _filter_reserved(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key not in _RESERVED_FIELDS}


def _handler_exists(logger: logging.Logger, format_kind: str) -> bool:
    for handler in logger.handlers:
        if getattr(handler, "_aduib_rpc_handler", False) and getattr(
            handler, "_format_kind", None
        ) == format_kind:
            return True
    return False


def _ensure_handler(
    logger: logging.Logger,
    formatter: logging.Formatter,
    *,
    format_kind: str,
    level: int | None,
    stream: Any,
) -> None:
    if _handler_exists(logger, format_kind):
        return
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())
    handler.setLevel(level or logging.NOTSET)
    handler._aduib_rpc_handler = True
    handler._format_kind = format_kind
    logger.addHandler(handler)
    # Set logger level to ensure it processes log records
    if level is not None:
        logger.setLevel(level)
    elif logger.level == logging.NOTSET:
        logger.setLevel(logging.DEBUG)  # Allow all levels by default
    logger.propagate = False


class LogContext:
    """Async-safe structured logging context.

    Args:
        tenant_id: Tenant identifier for multi-tenant tracing.
        trace_id: Distributed tracing identifier.
        request_id: Request correlation identifier.
        **extra: Additional context values for log enrichment.
    """

    def __init__(
        self,
        tenant_id: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        **extra: str | None,
    ) -> None:
        values: dict[str, Any] = {}
        if tenant_id is not None:
            values["tenant_id"] = tenant_id
        if trace_id is not None:
            values["trace_id"] = trace_id
        if request_id is not None:
            values["request_id"] = request_id
        for key, value in extra.items():
            if value is not None:
                values[key] = value
        self._values = values
        self._token: contextvars.Token[dict[str, Any]] | None = None

    def __enter__(self) -> LogContext:
        current = _LOG_CONTEXT.get({})
        updated = _merge_context(current, self._values, ignore_none=True)
        self._token = _LOG_CONTEXT.set(updated)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        if self._token is not None:
            _LOG_CONTEXT.reset(self._token)
            self._token = None

    @classmethod
    def bind(
        cls,
        tenant_id: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        **extra: str | None,
    ) -> None:
        updates: dict[str, Any] = {}
        if tenant_id is not None:
            updates["tenant_id"] = tenant_id
        if trace_id is not None:
            updates["trace_id"] = trace_id
        if request_id is not None:
            updates["request_id"] = request_id
        for key, value in extra.items():
            if value is not None:
                updates[key] = value
        current = _LOG_CONTEXT.get({})
        _LOG_CONTEXT.set(_merge_context(current, updates, ignore_none=True))

    @classmethod
    def clear(cls) -> None:
        _LOG_CONTEXT.set({})

    @classmethod
    def snapshot(cls) -> dict[str, Any]:
        return _context_snapshot()


class ContextFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        context = _context_snapshot()
        for key, value in context.items():
            if hasattr(record, key):
                continue
            record.__dict__[key] = "-" if value is None else value
        return True


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as JSON strings.

    Args:
        datefmt: Optional date format string.
        json_default: Callable used by json.dumps for unknown types.
        ensure_ascii: Whether to escape non-ASCII characters.
    """

    def __init__(
        self,
        *,
        datefmt: str | None = None,
        json_default: Any | None = None,
        ensure_ascii: bool = True,
    ) -> None:
        super().__init__(datefmt=datefmt)
        self._json_default = json_default or _json_default
        self._ensure_ascii = ensure_ascii

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_filter_reserved(_context_snapshot()))
        payload.update(_filter_reserved(_extract_extras(record)))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        return json.dumps(
            payload,
            default=self._json_default,
            ensure_ascii=self._ensure_ascii,
        )


class StructuredConsoleFormatter(logging.Formatter):

    def __init__(
        self,
        fmt: str | None = None,
        *,
        datefmt: str | None = None,
    ) -> None:
        super().__init__(fmt=fmt or _DEFAULT_CONSOLE_FORMAT, datefmt=datefmt)


class StructuredLogger:
    """Creates structured JSON and console loggers.

    Args:
        name: Base name for both loggers.
        json_formatter: Formatter for JSON output.
        console_formatter: Formatter for console output.
        level: Optional log level to apply to handlers and logger.
        stream: Optional stream for handler output.
    """

    def __init__(
        self,
        name: str,
        *,
        json_formatter: logging.Formatter | None = None,
        console_formatter: logging.Formatter | None = None,
        level: int | None = None,
        stream: Any | None = None,
    ) -> None:
        json_formatter = json_formatter or StructuredJSONFormatter()
        console_formatter = console_formatter or StructuredConsoleFormatter()
        self.json_logger = logging.getLogger(f"{name}.json")
        self.console_logger = logging.getLogger(f"{name}.console")
        _ensure_handler(
            self.json_logger,
            json_formatter,
            format_kind=LOG_FORMAT_JSON,
            level=level,
            stream=stream,
        )
        _ensure_handler(
            self.console_logger,
            console_formatter,
            format_kind=LOG_FORMAT_CONSOLE,
            level=level,
            stream=stream,
        )


def get_logger(
    name: str,
    *,
    log_format: str | None = None,
    json_formatter: logging.Formatter | None = None,
    console_formatter: logging.Formatter | None = None,
    level: int | None = None,
    stream: Any | None = None,
) -> logging.Logger:
    """Return a configured logger based on environment configuration.

    Args:
        name: Logger name.
        log_format: Optional override for log format selection.
        json_formatter: Optional JSON formatter override.
        console_formatter: Optional console formatter override.
        level: Optional log level to apply to handler and logger.
        stream: Optional stream for handler output.

    Returns:
        Configured logging.Logger instance.
    """

    resolved_format = _normalize_log_format(
        log_format or os.getenv(LOG_FORMAT_ENV)
    )
    formatter: logging.Formatter
    if resolved_format == LOG_FORMAT_CONSOLE:
        formatter = console_formatter or StructuredConsoleFormatter()
    else:
        formatter = json_formatter or StructuredJSONFormatter()
    logger = logging.getLogger(name)
    _ensure_handler(
        logger,
        formatter,
        format_kind=resolved_format,
        level=level,
        stream=stream,
    )
    return logger
