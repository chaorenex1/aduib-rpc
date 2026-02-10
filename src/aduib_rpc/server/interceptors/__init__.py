"""Server interceptors for request processing.

This module provides server-side interceptors for security, observability,
and other cross-cutting concerns.
"""
from __future__ import annotations

from aduib_rpc.server.interceptors.security import (
    SecurityConfig,
    SecurityInterceptor,
    create_security_interceptor,
)
from aduib_rpc.server.interceptors.tenant import (
    TenantInterceptor,
    TenantScope,
)
from aduib_rpc.server.interceptors.resilience import (
    ServerResilienceConfig,
    ServerResilienceInterceptor,
    ResilienceHandler,
    with_resilience,
)
from aduib_rpc.server.interceptors.audit import (
    AuditInterceptor,
)
from aduib_rpc.server.interceptors.qos import (
    QosInterceptor,
)

from aduib_rpc.server.interceptors.version_negotiation import (
    VersionNegotiationInterceptor,
    negotiate_client_version,
    normalize_request,
    normalize_response,
)
from aduib_rpc.server.interceptors.telemetry import OTelServerInterceptor, end_otel_span

__all__ = [
    "SecurityConfig",
    "SecurityInterceptor",
    "create_security_interceptor",
    "TenantInterceptor",
    "TenantScope",
    "ServerResilienceConfig",
    "ServerResilienceInterceptor",
    "ResilienceHandler",
    "with_resilience",
    "AuditInterceptor",
    "QosInterceptor",
    "VersionNegotiationInterceptor",
    "negotiate_client_version",
    "normalize_request",
    "normalize_response",
    "OTelServerInterceptor",
    "end_otel_span",
]
