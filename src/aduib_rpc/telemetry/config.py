from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    """Configuration for OpenTelemetry wiring.

    If `enabled` is False, `configure_telemetry()` becomes a no-op.

    Typical environment variables you may use:
    - OTEL_SERVICE_NAME
    - OTEL_EXPORTER_OTLP_ENDPOINT
    - OTEL_EXPORTER_OTLP_PROTOCOL

    We keep config minimal here; advanced users can directly use OpenTelemetry APIs.
    """

    enabled: bool = True
    service_name: str = "aduib-rpc"

    # OTLP/HTTP endpoint, e.g. "http://localhost:4318".
    # If None, OpenTelemetry SDK will use its own env-based defaults.
    otlp_endpoint: str | None = None

    # Whether to auto-instrument FastAPI / ASGI / HTTPX.
    instrument_fastapi: bool = True
    instrument_asgi: bool = True
    instrument_httpx: bool = True

