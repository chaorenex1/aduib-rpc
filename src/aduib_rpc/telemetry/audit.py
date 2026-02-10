"""Audit logging for security and compliance.

This module provides audit logging functionality that tracks:
- Request/response events with timestamps
- User identity (principal) and tenant
- Method calls and parameters
- Sensitive field sanitization

Audit events are structured, JSON-formatted logs that can be
exported to SIEM systems for compliance monitoring.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from aduib_rpc.telemetry.logging import get_logger

# Default sensitive fields that should be redacted
_DEFAULT_SENSITIVE_FIELDS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "session",
    "credit_card",
    "ssn",
    "social_security",
    "pin",
}


@dataclass
class AuditConfig:
    """Configuration for audit logging.

    Attributes:
        enabled: Whether audit logging is enabled.
        log_level: Log level to use for audit events.
        sanitize_fields: Set of field names to redact.
        include_params: Whether to include request parameters.
        include_response: Whether to include response data.
        max_param_length: Maximum length for parameter values (0 = unlimited).
        export_to_telemetry: Whether to export audit events to OpenTelemetry logs.
        otlp_endpoint: OTLP HTTP endpoint for log export. If not set, uses OTEL_EXPORTER_OTLP_ENDPOINT.
    """

    enabled: bool = True
    log_level: int = logging.INFO
    sanitize_fields: set[str] = field(default_factory=lambda: _DEFAULT_SENSITIVE_FIELDS.copy())
    include_params: bool = False
    include_response: bool = False
    max_param_length: int = 256  # Truncate long values
    export_to_telemetry: bool = False
    otlp_endpoint: str | None = None


_OTEL_LOCK = threading.Lock()
_OTEL_LOGGER_PROVIDER: Any | None = None
_OTEL_LOGGER: Any | None = None
_OTEL_CONFIGURED_ENDPOINT: str | None = None


def _get_otel_logger(otlp_endpoint: str | None = None) -> Any | None:
    """Return an OpenTelemetry Logger configured for OTLP log export.

    This is best-effort: if OpenTelemetry isn't installed, returns None.
    The provider is cached to avoid repeated configuration.
    """
    global _OTEL_LOGGER_PROVIDER, _OTEL_LOGGER, _OTEL_CONFIGURED_ENDPOINT

    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    except ImportError:
        return None

    resolved_endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    with _OTEL_LOCK:
        if _OTEL_LOGGER is not None:
            # If a different endpoint is requested later, prefer the first configuration
            # to avoid repeatedly reconfiguring exporters/processors.
            return _OTEL_LOGGER

        provider = LoggerProvider()
        exporter = OTLPLogExporter(endpoint=resolved_endpoint) if resolved_endpoint else OTLPLogExporter()
        provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

        _OTEL_LOGGER_PROVIDER = provider
        _OTEL_CONFIGURED_ENDPOINT = resolved_endpoint
        _OTEL_LOGGER = provider.get_logger("aduib_rpc.audit")
        return _OTEL_LOGGER


class AuditLogger:
    """Structured audit logger for security and compliance.

    This logger creates structured, JSON-formatted audit events
    that include:
    - event_type: Type of audit event
    - timestamp: ISO 8601 timestamp
    - tenant_id: Tenant identifier
    - request_id: Request correlation ID
    - trace_id: Distributed trace ID
    - principal: User/service identity
    - method: RPC method being called
    - status: Result status (success/failure)
    - error_code: Error code if failed
    - duration_ms: Processing duration
    - params: Request parameters (if enabled, sanitized)
    - response: Response data (if enabled, sanitized)

    Usage:
        audit_logger = AuditLogger(config)
        audit_logger.log_request(
            tenant_id="acme",
            request_id="req-123",
            trace_id="trace-456",
            principal="user@example.com",
            method="UserService.create",
            params={"name": "John"},
        )
        audit_logger.log_response(
            request_id="req-123",
            status="success",
            duration_ms=42,
        )
    """

    def __init__(self, config: AuditConfig | None = None, otlp_endpoint: str | None = None) -> None:
        """Initialize the audit logger.

        Args:
            config: Audit configuration.
            otlp_endpoint: Optional OTLP HTTP endpoint for audit log export.
        """
        self.config = config or AuditConfig()
        self.logger = get_logger("aduib_rpc.audit")
        self._pending_events: dict[str, dict[str, Any]] = {}
        self._otel_logger: Any | None = None

        if self.config.export_to_telemetry:
            self._otel_logger = _get_otel_logger(otlp_endpoint or self.config.otlp_endpoint)

    def _emit_to_otel(self, event: dict[str, Any]) -> None:
        """Emit an audit event to OpenTelemetry logs (best effort)."""
        if not self._otel_logger:
            return

        try:
            import inspect

            from opentelemetry.sdk._logs import LogRecord
        except ImportError:
            return
        except Exception:  # pragma: no cover - best effort
            return

        event_type = str(event.get("event_type") or "")
        severity_text = "INFO"
        severity_number: int = 9  # INFO
        if event_type.startswith("security_") or event_type.endswith("auth_failed") or event_type == "auth_failed":
            severity_text = "WARNING"
            severity_number = 13  # WARN

        body = json.dumps(event, ensure_ascii=True, default=str)

        # OTEL log attributes prefer primitives; encode complex values as JSON.
        attributes: dict[str, Any] = {"event_type": event_type}
        for key in (
            "tenant_id",
            "request_id",
            "trace_id",
            "principal",
            "method",
            "status",
            "error_code",
            "duration_ms",
            "success",
            "auth_method",
            "failure_reason",
        ):
            if key in event and event[key] is not None:
                attributes[key] = event[key]

        for key in ("params", "response", "details"):
            if key in event and event[key] is not None:
                attributes[key] = json.dumps(event[key], ensure_ascii=True, default=str)

        # Convert ISO timestamp (if present) to unix nanoseconds.
        now_ns = int(time.time() * 1_000_000_000)
        ts_ns = now_ns
        ts_str = event.get("timestamp")
        if isinstance(ts_str, str):
            try:
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts_ns = int(dt.timestamp() * 1_000_000_000)
            except Exception:  # pragma: no cover - best effort
                ts_ns = now_ns

        trace_id_int = 0
        trace_id = event.get("trace_id")
        if isinstance(trace_id, str) and trace_id not in {"-", ""}:
            try:
                trace_id_int = int(trace_id, 16)
            except ValueError:
                trace_id_int = 0

        # LogRecord signatures have changed across OpenTelemetry releases; adapt dynamically.
        try:
            sig = inspect.signature(LogRecord)
            kwargs: dict[str, Any] = {}
            for name in sig.parameters:
                if name == "timestamp":
                    kwargs[name] = ts_ns
                elif name == "observed_timestamp":
                    kwargs[name] = now_ns
                elif name == "severity_text":
                    kwargs[name] = severity_text
                elif name == "severity_number":
                    kwargs[name] = severity_number
                elif name == "body":
                    kwargs[name] = body
                elif name == "attributes":
                    kwargs[name] = attributes
                elif name == "trace_id":
                    kwargs[name] = trace_id_int
                elif name == "span_id":
                    kwargs[name] = 0
                elif name == "trace_flags":
                    kwargs[name] = 0
                elif name == "resource":
                    kwargs[name] = None
                elif name == "instrumentation_scope":
                    kwargs[name] = None
                elif name == "logger":
                    kwargs[name] = None
            record = LogRecord(**kwargs)
        except Exception:  # pragma: no cover - best effort
            return

        try:
            emit = getattr(self._otel_logger, "emit", None)
            if callable(emit):
                emit(record)
        except Exception:  # pragma: no cover - best effort
            pass

    def log_request(
        self,
        *,
        request_id: str,
        method: str,
        tenant_id: str | None = None,
        trace_id: str | None = None,
        principal: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Log an incoming request.

        Args:
            request_id: Unique request identifier.
            method: RPC method being called.
            tenant_id: Tenant identifier.
            trace_id: Distributed trace identifier.
            principal: User/service identity.
            params: Request parameters (optional).
        """
        if not self.config.enabled:
            return

        event = {
            "event_type": "rpc_request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id or "-",
            "request_id": request_id,
            "trace_id": trace_id or "-",
            "principal": principal or "-",
            "method": method,
        }

        if self.config.include_params and params:
            event["params"] = sanitize_for_audit(
                params,
                self.config.sanitize_fields,
                max_length=self.config.max_param_length,
            )

        # Store for later response logging
        self._pending_events[request_id] = event

        self.logger.log(self.config.log_level, json.dumps(event))
        self._emit_to_otel(event)

    def log_response(
        self,
        *,
        request_id: str,
        status: str,
        duration_ms: int | float,
        error_code: str | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        """Log a response completion.

        Args:
            request_id: Request identifier (must match log_request).
            status: Response status (success/error).
            duration_ms: Processing duration in milliseconds.
            error_code: Error code if failed.
            response: Response data (optional).
        """
        if not self.config.enabled:
            return

        # Retrieve pending event if exists
        base_event = self._pending_events.pop(request_id, {})
        tenant_id = base_event.get("tenant_id", "-")
        trace_id = base_event.get("trace_id", "-")
        principal = base_event.get("principal", "-")
        method = base_event.get("method", "unknown")

        event = {
            "event_type": "rpc_response",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "request_id": request_id,
            "trace_id": trace_id,
            "principal": principal,
            "method": method,
            "status": status,
            "duration_ms": duration_ms,
        }

        if error_code:
            event["error_code"] = error_code

        if self.config.include_response and response:
            event["response"] = sanitize_for_audit(
                response,
                self.config.sanitize_fields,
                max_length=self.config.max_param_length,
            )

        self.logger.log(self.config.log_level, json.dumps(event))
        self._emit_to_otel(event)

    def log_auth_event(
        self,
        *,
        event_type: str,  # "login", "logout", "token_refresh", "auth_failed"
        tenant_id: str | None = None,
        principal: str | None = None,
        success: bool,
        auth_method: str | None = None,
        failure_reason: str | None = None,
    ) -> None:
        """Log an authentication/authorization event.

        Args:
            event_type: Type of auth event.
            tenant_id: Tenant identifier.
            principal: User/service identity.
            success: Whether the auth operation succeeded.
            auth_method: Authentication method used.
            failure_reason: Reason for failure (if any).
        """
        if not self.config.enabled:
            return

        event = {
            "event_type": f"auth_{event_type}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id or "-",
            "principal": principal or "-",
            "success": success,
        }

        if auth_method:
            event["auth_method"] = auth_method
        if failure_reason:
            event["failure_reason"] = failure_reason

        self.logger.log(self.config.log_level, json.dumps(event))
        self._emit_to_otel(event)

    def log_security_event(
        self,
        *,
        event_type: str,  # "rate_limit_exceeded", "blocked", "suspicious_activity"
        tenant_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        principal: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a security-relevant event.

        Args:
            event_type: Type of security event.
            tenant_id: Tenant identifier.
            request_id: Request identifier.
            trace_id: Trace identifier.
            principal: User/service identity.
            details: Additional event details.
        """
        if not self.config.enabled:
            return

        event = {
            "event_type": f"security_{event_type}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id or "-",
            "request_id": request_id or "-",
            "trace_id": trace_id or "-",
            "principal": principal or "-",
        }

        if details:
            event["details"] = sanitize_for_audit(
                details,
                self.config.sanitize_fields,
                max_length=self.config.max_param_length,
            )

        # Security events always use WARNING level
        self.logger.warning(json.dumps(event))
        self._emit_to_otel(event)

    def clear_pending(self) -> None:
        """Clear all pending events (useful for testing or cleanup)."""
        self._pending_events.clear()


def sanitize_for_audit(
    data: Any,
    sensitive_fields: set[str] | None = None,
    max_length: int = 256,
) -> Any:
    """Sanitize sensitive data for audit logging.

    Args:
        data: Data to sanitize.
        sensitive_fields: Field names to redact.
        max_length: Maximum length for string values.

    Returns:
        Sanitized data with sensitive fields redacted.
    """
    if sensitive_fields is None:
        sensitive_fields = _DEFAULT_SENSITIVE_FIELDS

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, (dict, list)):
                sanitized[key] = sanitize_for_audit(value, sensitive_fields, max_length)
            elif isinstance(value, str) and max_length > 0 and len(value) > max_length:
                sanitized[key] = value[:max_length] + "... (truncated)"
            else:
                sanitized[key] = value
        return sanitized

    if isinstance(data, list):
        return [sanitize_for_audit(item, sensitive_fields, max_length) for item in data]

    if isinstance(data, str) and max_length > 0 and len(data) > max_length:
        return data[:max_length] + "... (truncated)"

    return data
