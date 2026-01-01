"""OpenTelemetry integration helpers.

This package is optional. Install with:
    aduib-rpc[telemetry]

Design goals:
- Be safe to import even when telemetry extras aren't installed.
- Provide a single `configure_telemetry()` entrypoint for servers and clients.
- Keep the core library free of hard dependencies on OpenTelemetry.
"""

from .config import TelemetryConfig
from .setup import configure_telemetry
from .grpc_interceptors import OTelGrpcClientInterceptor, OTelGrpcServerInterceptor

__all__ = [
    "TelemetryConfig",
    "configure_telemetry",
    "OTelGrpcClientInterceptor",
    "OTelGrpcServerInterceptor",
]
