from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MetricLabels:
    service: str = ""
    method: str = ""
    status: str = ""
    error_code: str = ""


class RpcMetrics:
    """RPC metrics using OpenTelemetry.

    Replaces observability.metrics.RpcMetrics with OTel-based implementation.
    Gracefully degrades when OTel is not installed.
    """

    _disabled: bool = True
    _meter: Any = None
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls) -> None:
        if cls._initialized:
            return
        cls._initialized = True

        try:
            from opentelemetry import metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            import os

            provider = metrics.get_meter_provider()
            if not isinstance(provider, MeterProvider):
                endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
                if endpoint:
                    try:
                        exporter = OTLPMetricExporter(endpoint=endpoint.replace("v1/traces", "v1/metrics"))
                    except (TypeError, Exception):
                        exporter = OTLPMetricExporter()
                    reader = PeriodicExportingMetricReader(exporter)
                    provider = MeterProvider(metric_readers=[reader])
                else:
                    provider = MeterProvider(metric_readers=[])
                metrics.set_meter_provider(provider)

            cls._meter = metrics.get_meter("aduib_rpc")
            cls._disabled = False

            cls._request_total = cls._meter.create_counter(
                "rpc.requests.total", description="Total number of RPC requests"
            )
            cls._request_duration = cls._meter.create_histogram(
                "rpc.request.duration.ms", description="RPC request duration in milliseconds"
            )
            cls._request_size = cls._meter.create_histogram(
                "rpc.request.size.bytes", description="RPC request size in bytes"
            )
            cls._response_size = cls._meter.create_histogram(
                "rpc.response.size.bytes", description="RPC response size in bytes"
            )
            cls._active_requests = cls._meter.create_up_down_counter(
                "rpc.active_requests", description="Number of active RPC requests"
            )
            cls._error_total = cls._meter.create_counter("rpc.errors.total", description="Total number of RPC errors")
            cls._rate_limit_total = cls._meter.create_counter(
                "rpc.rate_limit.total", description="Total number of rate limit events"
            )
            cls._retry_total = cls._meter.create_counter(
                "rpc.retry.total", description="Total number of retry attempts"
            )

        except Exception:
            cls._disabled = True

    @classmethod
    def record_request(
        cls,
        service: str,
        method: str,
        status: str,
        duration_seconds: float,
        request_size: int = 0,
        response_size: int = 0,
        error_code: str = "",
    ) -> None:
        """Record a completed RPC request."""
        cls._ensure_initialized()
        if cls._disabled:
            return

        attributes = {
            "rpc.service": service,
            "rpc.method": method,
            "rpc.status": status,
        }
        if error_code:
            attributes["error.code"] = error_code

        cls._request_total.add(1, attributes)
        cls._request_duration.record(duration_seconds * 1000, attributes)
        if request_size:
            cls._request_size.record(request_size, attributes)
        if response_size:
            cls._response_size.record(response_size, attributes)

    @classmethod
    def record_error(
        cls,
        service: str,
        method: str,
        error_code: str,
    ) -> None:
        """Record an RPC error."""
        cls._ensure_initialized()
        if cls._disabled:
            return

        cls._error_total.add(
            1,
            {
                "rpc.service": service,
                "rpc.method": method,
                "error.code": error_code,
            },
        )
