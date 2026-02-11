from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Log format constants
LOG_FORMAT_JSON = "json"
LOG_FORMAT_CONSOLE = "console"

# Log level mapping
LEVEL_NAME_TO_INT = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter that includes OTel trace context."""

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        trace_fields = _fetch_trace_context()
        base.update(trace_fields)

        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)

        return json.dumps(base)


class StructuredConsoleFormatter(logging.Formatter):
    """Human-readable console formatter with optional trace context."""

    def format(self, record: logging.LogRecord) -> str:
        trace_fields = _fetch_trace_context()
        trace_info = ""
        if trace_fields.get("trace_id"):
            trace_info = f"[{trace_fields['trace_id'][:8]}] "

        return f"{trace_info}{record.levelname:8} {record.name}: {record.getMessage()}"


def _fetch_trace_context() -> dict[str, str]:
    try:
        from opentelemetry import trace

        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            context = current_span.get_span_context()
            return {
                "trace_id": format(context.trace_id, "032x"),
                "span_id": format(context.span_id, "016x"),
            }
    except Exception:  # pragma: no cover - best effort
        pass
    return {}


def get_logger(name: str, *, json_output: bool = True) -> logging.Logger:
    """Return a structured logger.

    Args:
        name: Logger name (typically __name__ of the caller).
        json_output: When True, use StructuredJSONFormatter; otherwise StructuredConsoleFormatter.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = StructuredJSONFormatter() if json_output else StructuredConsoleFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
