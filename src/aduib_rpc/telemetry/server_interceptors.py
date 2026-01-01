from __future__ import annotations

from typing import Any

from aduib_rpc.server.context import ServerContext, ServerInterceptor
from aduib_rpc.types import AduibRpcRequest, AduibRPCError


class OTelServerInterceptor(ServerInterceptor):
    """Server-side interceptor extracting trace context and creating a span per request.

    Note:
    - Decorator/service_call already logs duration; this gives distributed tracing.
    - We keep it optional and safe when otel isn't installed.
    """

    async def intercept(
        self,
        request_body: AduibRpcRequest,
        context: ServerContext,
    ) -> AduibRPCError | None:
        try:
            from opentelemetry import trace
            from opentelemetry.propagate import extract
        except Exception:
            return None

        carrier: dict[str, Any] = {}
        # headers live in ServerContext.metadata/state['headers'] depending on transport
        if context and getattr(context, "metadata", None):
            carrier = {str(k): str(v) for k, v in (context.metadata or {}).items()}
        elif context and "headers" in context.state:
            carrier = {str(k): str(v) for k, v in (context.state.get("headers") or {}).items()}

        ctx = extract(carrier)
        tracer = trace.get_tracer("aduib_rpc")
        span = tracer.start_span(
            name=f"rpc {request_body.method}",
            context=ctx,
            attributes={
                "rpc.method": request_body.method,
                "rpc.request_id": str(request_body.id) if request_body.id is not None else "",
            },
        )

        # Store it so request handler can end it later.
        context.state["otel_span"] = span
        return None


async def end_otel_span(context: ServerContext | None, *, status: str, error: Exception | None = None) -> None:
    """Best-effort span finalization."""
    if not context:
        return
    span = context.state.get("otel_span")
    if not span:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        if status == "error":
            span.set_status(Status(StatusCode.ERROR, str(error) if error else "error"))
        else:
            span.set_status(Status(StatusCode.OK))
    except Exception:
        pass
    finally:
        try:
            span.end()
        except Exception:
            pass
        context.state.pop("otel_span", None)

