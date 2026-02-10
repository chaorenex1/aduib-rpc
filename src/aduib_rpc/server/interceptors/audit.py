"""Audit interceptor for server-side request processing.

AuditInterceptor emits structured audit events via
:class:`aduib_rpc.telemetry.audit.AuditLogger`.

AuditInterceptor is intentionally non-blocking: it never returns an error.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor
from aduib_rpc.telemetry.audit import AuditConfig, AuditLogger
from aduib_rpc.types import AduibRpcResponse

logger = logging.getLogger(__name__)
class AuditInterceptor(ServerInterceptor):
    """Server interceptor that records request/response audit logs.

    It records request start in :meth:`intercept` and response completion in
    :meth:`log_response`. It never blocks requests.
    """

    def order(self) -> int:
        return 4

    def __init__(
        self,
        config: AuditConfig | None = None,
        audit_logger: AuditLogger | None = None,
        *,
        otlp_endpoint: str | None = None,
    ) -> None:
        """Initialize the audit interceptor.

        Args:
            config: Optional audit configuration.
            audit_logger: Optional pre-configured AuditLogger (takes precedence).
            otlp_endpoint: Optional OTLP endpoint (best-effort) for broader telemetry export.
                Audit logging itself is log-based; this is stored and used to seed
                ``OTEL_EXPORTER_OTLP_ENDPOINT`` for other OpenTelemetry exporters.
        """
        self.config = config or AuditConfig()
        self._audit_logger = audit_logger or AuditLogger(self.config)
        self._otlp_endpoint = otlp_endpoint

        if self._otlp_endpoint:
            os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", self._otlp_endpoint)
            logger.debug("AuditInterceptor: seeded OTEL_EXPORTER_OTLP_ENDPOINT")

        if audit_logger is not None and config is not None:
            logger.debug("AuditInterceptor: audit_logger provided; config is ignored for logger construction")

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        """Record request start and completion."""
        request_id = str(ctx.request.id) if ctx.request.id is not None else ""
        method = str(ctx.request.method or "")
        tenant_id = ctx.request.metadata.tenant_id if ctx.request.metadata else None
        trace_id = ctx.request.trace_context.trace_id if ctx.request.trace_context else None
        principal = ctx.request.metadata.auth.principal if ctx.request.metadata and ctx.request.metadata.auth else None

        start_time = time.perf_counter()
        ctx.store("audit_request_id", request_id)
        ctx.store("audit_start_time", start_time)

        logger.debug(
            "AuditInterceptor: request start request_id=%s method=%s tenant_id=%s trace_id=%s principal=%s",
            request_id,
            method,
            tenant_id,
            trace_id,
            principal,
        )

        params: dict[str, Any] | None = (
            ctx.request.data if isinstance(ctx.request.data, dict) else None
        )

        self._audit_logger.log_request(
            request_id=request_id,
            method=method,
            tenant_id=str(tenant_id) if tenant_id is not None else None,
            trace_id=trace_id,
            principal=principal,
            params=params,
        )

        try:
            yield
        finally:
            start_time = ctx.load("audit_start_time", time.perf_counter())
            ctx.store("audit_end_time", time.perf_counter())
            duration_ms = (time.perf_counter() - start_time) * 1000
            ctx.store("audit_duration_ms", duration_ms)

            status = "success"
            if ctx.error is not None:
                status = "error"
            elif ctx.response and getattr(ctx.response, "error", None):
                status = "error"

            error_code = None
            if ctx.response and ctx.response.error:
                code = getattr(ctx.response.error, "code", None)
                if code is not None:
                    error_code = str(code)

            response_payload = None
            if ctx.response and self._audit_logger.config.include_response:
                if hasattr(ctx.response, "model_dump"):
                    try:
                        response_payload = ctx.response.model_dump(mode="json", exclude_none=True)
                    except TypeError:
                        response_payload = ctx.response.model_dump(exclude_none=True)

            self._audit_logger.log_response(
                request_id=str(ctx.load("audit_request_id")),
                status=status,
                duration_ms=duration_ms,
                error_code=error_code,
                response=response_payload,
            )

            logger.debug(
                "AuditInterceptor: request end request_id=%s status=%s duration_ms=%.2f",
                request_id,
                status,
                duration_ms,
            )

    def log_response(
        self,
        request_id: str,
        *,
        response: AduibRpcResponse | None,
        error: Exception | None = None,
        context: ServerContext | None,
    ) -> None:
        """Record response completion.

        Args:
            request_id: Request id (correlates request and response).
            response: RPC response object (if available).
            error: Exception raised during handling (if any).
            context: Server context.
        """
        start_time = None
        if context is not None:
            start_time = context.state.pop("audit_start_time", None)

        duration_ms = 0.0
        if isinstance(start_time, (int, float)):
            duration_ms = max(0.0, (time.perf_counter() - float(start_time)) * 1000.0)

        status = "success"
        if error is not None:
            status = "error"
        elif response is not None and getattr(response, "error", None) is not None:
            status = "error"

        error_code: str | None = None
        if response is not None and getattr(response, "error", None) is not None:
            code = getattr(response.error, "code", None)
            if code is not None:
                error_code = str(code)

        logger.debug(
            "AuditInterceptor: request end request_id=%s status=%s duration_ms=%s error_code=%s",
            request_id,
            status,
            duration_ms,
            error_code,
        )

        response_payload: dict[str, Any] | None = None
        if response is not None and self._audit_logger.config.include_response:
            if hasattr(response, "model_dump"):
                try:
                    response_payload = response.model_dump(mode="json", exclude_none=True)
                except TypeError:
                    response_payload = response.model_dump(exclude_none=True)
            elif isinstance(response, dict):
                response_payload = response
            else:
                response_payload = {"value": str(response)}

        self._audit_logger.log_response(
            request_id=str(request_id),
            status=status,
            duration_ms=duration_ms,
            error_code=error_code,
            response=response_payload,
        )
