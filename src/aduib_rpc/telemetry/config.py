from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    """Unified configuration for OpenTelemetry observability.

    Includes:
    - Tracing (Spans, distributed tracing)
    - Metrics (Counters, Histograms, Gauges)
    - Logging (Structured logging with trace context)
    - Audit (Security and compliance logging)

    If `enabled` is False, `configure_telemetry()` becomes a no-op.

    Environment variables:
    - OTEL_SERVICE_NAME: Service name for traces/metrics
    - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (e.g., "http://localhost:4318")
    - OTEL_EXPORTER_OTLP_PROTOCOL: Protocol (http/protobuf, grpc)
    """

    # Core
    enabled: bool = True
    service_name: str = "aduib-rpc"

    # OTLP endpoint, e.g., "http://localhost:4318"
    otlp_endpoint: str = "http://10.0.0.96:4317"
    otlp_protocol: str = "grpc"

    # Tracing
    tracing_enabled: bool = True
    instrument_fastapi: bool = True
    instrument_httpx: bool = True
    instrument_grpc: bool = True

    # Metrics
    metrics_enabled: bool = True
    metrics_export_interval_ms: int = 30000  # 30 seconds

    # Logging
    logging_enabled: bool = True
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    # Audit
    audit_enabled: bool = True
    audit_include_params: bool = False
    audit_include_response: bool = False
