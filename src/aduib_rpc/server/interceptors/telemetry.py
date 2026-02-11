from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from aduib_rpc.protocol.v2.types import ResponseStatus
from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor

logger = logging.getLogger(__name__)


class OTelServerInterceptor(ServerInterceptor):
    """Server-side interceptor extracting trace context and creating a span per request.

    Integrates with:
    - W3C traceparent headers via OpenTelemetry propagate.extract()
    - v2 trace_context from ServerContext (if available)
    - tenant_id from metadata (added as span attribute)

    Note:
    - Decorator/service_call already logs duration; this gives distributed tracing.
    - We keep it optional and safe when otel isn't installed.
    """

    def order(self) -> int:
        """Order of the interceptor in the chain.

        Returns:
            An integer representing the order. Lower values run earlier.
        """
        return 3  # Run after tenant and auth interceptors

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        try:
            from opentelemetry import trace
            from opentelemetry.propagate import extract
        except ImportError:
            logger.error("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")
            yield
            return

        carrier: dict[str, Any] = {}
        if ctx.server_context and "headers" in ctx.server_context.state:
            carrier = {str(k): str(v) for k, v in (ctx.server_context.state.get("headers") or {}).items()}

        ctx_carrier = extract(carrier)
        tracer = trace.get_tracer("aduib_rpc")

        attributes: dict[str, Any] = {
            "rpc.method": ctx.request.method,
            "rpc.request_id": str(ctx.request.id) if ctx.request.id is not None else "",
            "rpc.system": "aduib_rpc",
            "rpc.version": ctx.request.aduib_rpc,
            "trace.id": ctx.request.trace_context.trace_id if ctx.request.trace_context else "",
            "span.id": ctx.request.trace_context.span_id if ctx.request.trace_context else "",
            "parent.span.id": ctx.request.trace_context.parent_span_id if ctx.request.trace_context else "",
            "tenant.id": ctx.request.metadata.tenant_id if ctx.request.metadata else "",
            "enduser.id": ctx.request.metadata.auth.principal
            if ctx.request.metadata and ctx.request.metadata.auth
            else "",
            "enduser.roles": (
                ",".join(ctx.request.metadata.auth.roles)
                if ctx.request.metadata
                and ctx.request.metadata.auth
                and isinstance(ctx.request.metadata.auth.roles, list)
                else str(ctx.request.metadata.auth.roles)
                if ctx.request.metadata and ctx.request.metadata.auth and ctx.request.metadata.auth.roles
                else ""
            ),
            "client_id": ctx.request.metadata.client_id if ctx.request.metadata else "",
            "client_version": ctx.request.metadata.client_version if ctx.request.metadata else "",
        }

        span = tracer.start_span(
            name=f"rpc {ctx.request.method}",
            context=ctx_carrier,
            attributes=attributes,
        )

        ctx.server_context.state["otel_span"] = span

        try:
            yield
        finally:
            status = ResponseStatus.ERROR
            if ctx.response is not None:
                status = ctx.response.status
            elif ctx.error is None:
                status = ResponseStatus.SUCCESS
            await end_otel_span(ctx.server_context, status=status, error=ctx.error)


async def end_otel_span(
    context: ServerContext | None,
    *,
    status: ResponseStatus | str,
    error: Exception | None = None,
) -> None:
    """Best-effort span finalization."""
    if not context:
        return
    span = context.state.get("otel_span")
    if not span:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        if status == ResponseStatus.ERROR:
            span.set_status(Status(StatusCode.ERROR, str(error) if error else "error"))
            # Add exception info if available
            if error:
                span.record_exception(error)
        else:
            span.set_status(Status(StatusCode.OK))
    except ImportError:
        logger.error("Please install the 'aduib-rpc[telemetry]' extras to enable telemetry features.")
    finally:
        try:
            span.end()
        except Exception as e:
            logger.error(f"Failed to end span: {e}")
        context.state.pop("otel_span", None)
