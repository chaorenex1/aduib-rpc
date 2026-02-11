from __future__ import annotations

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)

from .config import TelemetryConfig


def configure_telemetry(config: TelemetryConfig) -> None:
    """Configure OpenTelemetry tracing, metrics, and instrumentations.

    Safe behavior:
    - If telemetry extras are not installed, this is a no-op.
    - If called multiple times, it attempts to be idempotent.

    Configures:
    - Tracing: Spans with OTLP export
    - Metrics: Counters, histograms, gauges with OTLP export
    - Auto-instrumentation: FastAPI, ASGI, HTTPX
    """

    if not config.enabled:
        return

    # Configure tracing
    if config.tracing_enabled:
        _configure_tracing(config)

    # Configure metrics
    if config.metrics_enabled:
        _configure_metrics(config)
    if config.logging_enabled:
        configure_logging(config)

    # Auto-instrumentation
    _configure_auto_instrumentation(config)


def _configure_tracing(config: TelemetryConfig) -> None:
    """Configure tracing with OTLP export."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError:
        logger.error("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")
        raise RuntimeError("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")

    current_provider = trace.get_tracer_provider()
    if current_provider and current_provider.__class__.__name__ == "TracerProvider":
        provider = current_provider
    else:
        resource = Resource.create({"service.name": config.service_name})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

    endpoint = config.otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    try:
        exporter = OTLPSpanExporter(endpoint=endpoint)
    except TypeError:
        exporter = OTLPSpanExporter()  # type: ignore[call-arg]
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def _configure_metrics(config: TelemetryConfig) -> None:
    """Configure metrics with OTLP export."""
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    except ImportError:
        logger.error("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")
        raise RuntimeError("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")

    current_provider = metrics.get_meter_provider()
    if current_provider and current_provider.__class__.__name__ == "MeterProvider":
        return  # Already configured

    endpoint = config.otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    try:
        exporter = OTLPMetricExporter(endpoint=endpoint)
    except TypeError:
        exporter = OTLPMetricExporter()

    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=config.metrics_export_interval_ms,
    )

    resource = _get_resource(config.service_name)
    provider = MeterProvider(metric_readers=[reader], resource=resource)
    metrics.set_meter_provider(provider)


def _configure_auto_instrumentation(config: TelemetryConfig) -> None:
    """Configure auto-instrumentation for frameworks."""
    if config.instrument_fastapi:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument()  # type: ignore[call-arg]

    if config.instrument_httpx:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()  # type: ignore[call-arg]

    if config.instrument_grpc:
        from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer

        GrpcInstrumentorClient().instrument()
        GrpcInstrumentorServer().instrument()


def configure_instrumentation_fastapi(app: FastAPI) -> None:
    """Configure FastAPI instrumentation."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument_app(app)  # type: ignore[call-arg]
    except ImportError:
        logger.error("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")
        raise RuntimeError("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")


def configure_logging(config: TelemetryConfig) -> None:
    """Configure structured logging with trace context."""
    if not config.logging_enabled:
        return

    import logging
    from opentelemetry import trace

    class TraceContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            span = trace.get_current_span()
            if span and span.get_span_context().is_valid:
                record.trace_id = span.get_span_context().trace_id
                record.span_id = span.get_span_context().span_id
            else:
                record.trace_id = None
                record.span_id = None
            return True

    logging.getLogger().addFilter(TraceContextFilter())


def _get_resource(service_name: str):
    """Get or create OTel Resource."""
    from opentelemetry.sdk.resources import Resource

    return Resource.create({"service.name": service_name})
