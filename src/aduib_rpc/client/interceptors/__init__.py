"""Client interceptors for cross-cutting concerns.

This module provides interceptors for client-side request processing,
including resilience patterns, authentication, and observability.
"""

from __future__ import annotations

from aduib_rpc.client.interceptors.otel_client import OTelClientInterceptor

# Import base classes from parent midwares module
from aduib_rpc.client.midwares import (
    ClientContext,
    ClientRequestInterceptor,
)

__all__ = [
    # Base classes
    "ClientContext",
    "ClientRequestInterceptor",
    # OpenTelemetry interceptor
    "OTelClientInterceptor",
]
