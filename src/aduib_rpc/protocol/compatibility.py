"""Compatibility helpers for Aduib RPC protocol v1.0 and v2.0.

This module provides a narrow conversion layer that maps the public protocol
types between v1.0 and v2.0. The conversions are intentionally conservative:
only fields that have direct equivalents are mapped, while v2-only structures
are populated with minimal, safe defaults.

The helpers here are primarily intended for server-side shims and unit tests.
They do not attempt to perform full semantic upgrades of messages across all
protocol features.
"""

from __future__ import annotations

import secrets
import time
import uuid

from aduib_rpc.types import AduibRpcError, AduibRpcRequest, AduibRpcResponse
from aduib_rpc.protocol.v2.metadata import RequestMetadata, ResponseMetadata
from aduib_rpc.protocol.v2.types import (
    AduibRpcRequest as V2Request,
    AduibRpcResponse as V2Response,
    ResponseStatus,
    RpcError,
    TraceContext,
)

_TRACE_ID_BYTES = 16
_SPAN_ID_BYTES = 8
_VERSION_PRIORITY: tuple[str, ...] = ("2.0", "1.0")


def _now_ms() -> int:
    """Return the current Unix timestamp in milliseconds.

    Returns:
        Current epoch timestamp in milliseconds.
    """

    return int(time.time() * 1000)


def _random_trace_id() -> str:
    """Generate a random trace identifier suitable for TraceContext.

    Returns:
        A 32-character hex string representing a 128-bit trace ID.
    """

    return secrets.token_hex(_TRACE_ID_BYTES)


def _random_span_id() -> str:
    """Generate a random span identifier suitable for TraceContext.

    Returns:
        A 16-character hex string representing a 64-bit span ID.
    """

    return secrets.token_hex(_SPAN_ID_BYTES)


def _ensure_request_id(value: str | int | None) -> str:
    """Return a string request ID suitable for v2 requests.

    Args:
        value: The incoming v1 request identifier.

    Returns:
        A string ID. If the incoming value is None, a UUID v4 is generated.
    """

    if value is None:
        return str(uuid.uuid4())
    return str(value)


def _build_trace_context() -> TraceContext:
    """Create a minimal TraceContext with random identifiers.

    Returns:
        TraceContext containing random trace and span identifiers.
    """

    return TraceContext(trace_id=_random_trace_id(), span_id=_random_span_id())


def _build_request_metadata() -> RequestMetadata:
    """Create basic request metadata with the current timestamp.

    Returns:
        RequestMetadata populated with a timestamp in milliseconds.
    """

    return RequestMetadata(timestamp_ms=_now_ms())


def _build_response_metadata(duration_ms: int | None = None) -> ResponseMetadata:
    """Create minimal response metadata with the current timestamp.

    Args:
        duration_ms: Optional duration value to attach to the response metadata.

    Returns:
        ResponseMetadata containing timestamp and duration values.
    """

    return ResponseMetadata(timestamp_ms=_now_ms(), duration_ms=duration_ms or 0)


def _compact_error_data(error: RpcError) -> dict[str, object] | None:
    """Build a compact data payload for v1 error objects.

    Args:
        error: The v2 error object to convert.

    Returns:
        A dictionary capturing extra error context or None when no extra data is
        available.
    """

    data: dict[str, object] = {"name": error.name}
    if error.details is not None:
        data["details"] = error.details
    if error.debug is not None:
        data["debug"] = error.debug
    if len(data) == 1:
        return None
    return data


def _rpc_error_to_v1(error: RpcError | None) -> AduibRpcError | None:
    """Convert a v2 RpcError to the v1 error envelope.

    Args:
        error: The v2 error payload.

    Returns:
        AduibRpcError if an error is provided, otherwise None.
    """

    if error is None:
        return None
    return AduibRpcError(
        code=int(error.code),
        message=error.message,
        data=_compact_error_data(error),
    )


def _v1_status_from_v2(response: V2Response) -> str:
    """Derive the v1 response status from a v2 response.

    Args:
        response: The v2 response to inspect.

    Returns:
        "success" when the response is successful without errors, otherwise
        "error".
    """

    if response.status == ResponseStatus.SUCCESS and response.error is None:
        return "success"
    return "error"


def v1_to_v2_request(v1_req: AduibRpcRequest) -> V2Request:
    """Convert a Protocol v1.0 request to a Protocol v2.0 request.

    Args:
        v1_req: The v1 request envelope.

    Returns:
        A v2 request with mapped fields, basic trace context, and request
        metadata.
    """

    return V2Request(
        aduib_rpc="2.0",
        id=_ensure_request_id(v1_req.id),
        method=v1_req.method,
        data=v1_req.data,
        name=v1_req.name,
        trace_context=_build_trace_context(),
        metadata=_build_request_metadata(),
    )


def v2_to_v1_response(v2_resp: V2Response) -> AduibRpcResponse:
    """Convert a Protocol v2.0 response to a Protocol v1.0 response.

    Args:
        v2_resp: The v2 response envelope.

    Returns:
        A v1 response with mapped result and error fields.
    """

    return AduibRpcResponse(
        id=v2_resp.id,
        result=v2_resp.result,
        error=_rpc_error_to_v1(v2_resp.error),
        status=_v1_status_from_v2(v2_resp),
    )


def negotiate_version(client_versions: list[str], server_versions: list[str]) -> str:
    """Negotiate the highest compatible protocol version.

    Args:
        client_versions: Versions supported by the client.
        server_versions: Versions supported by the server.

    Returns:
        The negotiated protocol version.

    Raises:
        ValueError: If no compatible protocol version exists.
    """

    client_set = {version for version in client_versions}
    server_set = {version for version in server_versions}
    for version in _VERSION_PRIORITY:
        if version in client_set and version in server_set:
            return version
    raise ValueError("No compatible protocol version found.")


__all__ = [
    "negotiate_version",
    "v1_to_v2_request",
    "v2_to_v1_response",
]
