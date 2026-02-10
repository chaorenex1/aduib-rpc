"""OpenTelemetry integration helpers.

This package provides unified observability for aduib-rpc:
- Tracing via OpenTelemetry
- Metrics via OpenTelemetry
- Structured logging with trace context
- Audit logging for compliance

Install with:
    aduib-rpc[telemetry]

Design goals:
- Be safe to import even when telemetry extras aren't installed.
- Provide a single `configure_telemetry()` entrypoint.
- Keep the core library free of hard dependencies on OpenTelemetry.
"""

from .audit import AuditConfig, AuditLogger, sanitize_for_audit
from .config import TelemetryConfig
from .logging import (
    LOG_FORMAT_CONSOLE,
    LOG_FORMAT_JSON,
    LEVEL_NAME_TO_INT,
    StructuredConsoleFormatter,
    StructuredJSONFormatter,
    get_logger,
)
from .metrics import MetricLabels, RpcMetrics
from .setup import configure_telemetry
from .span_decorator import with_span

__all__ = [
    # Config
    "TelemetryConfig",
    "configure_telemetry",
    # Tracing
    "with_span",
    # Metrics
    "MetricLabels",
    "RpcMetrics",
    # Logging
    "LOG_FORMAT_JSON",
    "LOG_FORMAT_CONSOLE",
    "LEVEL_NAME_TO_INT",
    "get_logger",
    "StructuredJSONFormatter",
    "StructuredConsoleFormatter",
    # Audit
    "AuditConfig",
    "AuditLogger",
    "sanitize_for_audit",
]
