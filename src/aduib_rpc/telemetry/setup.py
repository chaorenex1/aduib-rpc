from __future__ import annotations

import os
from typing import Any

from .config import TelemetryConfig


def configure_telemetry(config: TelemetryConfig) -> None:
    """Configure OpenTelemetry tracing and common instrumentations.

    Safe behavior:
    - If telemetry extras are not installed, this is a no-op.
    - If called multiple times, it attempts to be idempotent.

    NOTE: Metrics are intentionally not wired here yet; tracing brings most value
    with minimal complexity.
    """

    if not config.enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except Exception:
        # telemetry extras not installed
        return

    # Avoid overwriting an existing provider (common in frameworks / tests).
    current_provider = trace.get_tracer_provider()
    if current_provider and current_provider.__class__.__name__ == "TracerProvider":
        # Already configured by someone else.
        provider = current_provider
    else:
        resource = Resource.create({"service.name": config.service_name})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

    endpoint = config.otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            exporter = OTLPSpanExporter(endpoint=endpoint)
        except TypeError:
            # exporter signature differs across versions; fall back to default
            exporter = OTLPSpanExporter()  # type: ignore[call-arg]
        provider.add_span_processor(BatchSpanProcessor(exporter))

    # Optional auto-instrumentation
    if config.instrument_fastapi:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            # Instrumentation is applied when app instance exists.
            # Users can also call `FastAPIInstrumentor.instrument_app(app)` themselves.
            FastAPIInstrumentor.instrument()
        except Exception:
            pass

    if config.instrument_asgi:
        try:
            from opentelemetry.instrumentation.asgi import AsgiInstrumentor

            AsgiInstrumentor.instrument()
        except Exception:
            pass

    if config.instrument_httpx:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()  # type: ignore[call-arg]
        except Exception:
            pass


def start_span(name: str, **attrs: Any):
    """Small helper to create spans in internal code without hard dependency.

    When telemetry isn't installed/configured, this returns a dummy context manager.
    """

    try:
        from opentelemetry import trace
    except Exception:
        from contextlib import nullcontext

        return nullcontext()

    tracer = trace.get_tracer("aduib_rpc")
    span_cm = tracer.start_as_current_span(name)
    # Can't easily set attrs before entering; callers can set inside span.
    return span_cm

