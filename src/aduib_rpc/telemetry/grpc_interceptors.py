from __future__ import annotations

from collections.abc import Sequence
from typing import Any

try:
    import grpc
except Exception:  # pragma: no cover
    grpc = None  # type: ignore


def _otel_inject_to_grpc_metadata(metadata: Sequence[tuple[str, str]] | None) -> list[tuple[str, str]]:
    """Inject current trace context into gRPC metadata.

    Best-effort:
    - If OpenTelemetry isn't installed, returns metadata unchanged.
    """

    md = list(metadata or [])

    try:
        from opentelemetry.propagate import inject
    except Exception:
        return md

    carrier: dict[str, str] = {}
    inject(carrier)
    for k, v in carrier.items():
        md.append((str(k).lower(), str(v)))
    return md


def _otel_extract_from_grpc_metadata(metadata: Sequence[tuple[str, str]] | None):
    """Extract remote trace context from gRPC metadata (best-effort)."""

    try:
        from opentelemetry.propagate import extract
    except Exception:
        return None

    carrier = {str(k).lower(): str(v) for (k, v) in (metadata or [])}
    return extract(carrier)


def _make_client_call_details(client_call_details: Any, metadata: Sequence[tuple[str, str]] | None):
    """Create a concrete grpc.aio.ClientCallDetails.

    grpc.aio.ClientCallDetails is an interface; different grpcio versions expose
    different helper types. This function creates a minimal compatible object.
    """

    if grpc is None:
        raise RuntimeError("grpc is not installed")

    class _ClientCallDetails(grpc.aio.ClientCallDetails):
        def __init__(self, base, md):
            self.method = base.method
            self.timeout = getattr(base, "timeout", None)
            self.metadata = md
            self.credentials = getattr(base, "credentials", None)
            self.wait_for_ready = getattr(base, "wait_for_ready", None)
            self.compression = getattr(base, "compression", None)

    return _ClientCallDetails(client_call_details, metadata)


class OTelGrpcClientInterceptor:
    """gRPC aio client interceptor injecting OpenTelemetry trace context.

    Implemented dynamically to keep module import safe when grpc isn't installed.
    """

    def __init__(self) -> None:
        if grpc is None:
            raise RuntimeError("grpc is not installed")

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        md = _otel_inject_to_grpc_metadata(getattr(client_call_details, "metadata", None))
        new_details = _make_client_call_details(client_call_details, md)
        return await continuation(new_details, request)

    async def intercept_unary_stream(self, continuation, client_call_details, request):
        md = _otel_inject_to_grpc_metadata(getattr(client_call_details, "metadata", None))
        new_details = _make_client_call_details(client_call_details, md)
        return await continuation(new_details, request)


class OTelGrpcServerInterceptor:
    """gRPC aio server interceptor extracting OpenTelemetry trace context.

    Wraps unary-unary and unary-stream handlers in a span.
    """

    def __init__(self) -> None:
        if grpc is None:
            raise RuntimeError("grpc is not installed")

    async def intercept_service(self, continuation, handler_call_details):
        inv_md = getattr(handler_call_details, "invocation_metadata", None)
        otel_ctx = _otel_extract_from_grpc_metadata(inv_md)

        try:
            from opentelemetry import trace
        except Exception:
            return await continuation(handler_call_details)

        tracer = trace.get_tracer("aduib_rpc")

        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        method = getattr(handler_call_details, "method", "")

        # grpc.aio.RpcMethodHandler exists on grpc aio
        RpcMethodHandler = grpc.aio.RpcMethodHandler

        if getattr(handler, "unary_unary", None) is not None:
            inner = handler.unary_unary

            async def unary_unary(request, context):
                with tracer.start_as_current_span(
                    name=f"grpc {method}",
                    context=otel_ctx,
                    attributes={"rpc.system": "grpc", "rpc.method": str(method)},
                ):
                    return await inner(request, context)

            return RpcMethodHandler(
                unary_unary=unary_unary,
                unary_stream=handler.unary_stream,
                stream_unary=handler.stream_unary,
                stream_stream=handler.stream_stream,
                request_streaming=handler.request_streaming,
                response_streaming=handler.response_streaming,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if getattr(handler, "unary_stream", None) is not None:
            inner = handler.unary_stream

            async def unary_stream(request, context):
                with tracer.start_as_current_span(
                    name=f"grpc {method}",
                    context=otel_ctx,
                    attributes={"rpc.system": "grpc", "rpc.method": str(method)},
                ):
                    async for item in inner(request, context):
                        yield item

            return RpcMethodHandler(
                unary_unary=handler.unary_unary,
                unary_stream=unary_stream,
                stream_unary=handler.stream_unary,
                stream_stream=handler.stream_stream,
                request_streaming=handler.request_streaming,
                response_streaming=handler.response_streaming,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler


def inject_otel_to_grpc_metadata(metadata: Sequence[tuple[str, str]] | None) -> list[tuple[str, str]]:
    """Public helper: inject OpenTelemetry context into a gRPC metadata list."""
    return _otel_inject_to_grpc_metadata(metadata)
