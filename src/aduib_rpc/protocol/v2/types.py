from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from aduib_rpc.exceptions import RpcException
from aduib_rpc.protocol.v2.errors import ErrorCode, ERROR_CODE_NAMES

_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-fA-F]{16}$")


class ResponseStatus(StrEnum):
    """Response status for Aduib RPC v2."""

    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class TraceContext(BaseModel):
    """W3C Trace Context-compatible trace metadata for distributed tracing.

    Attributes:
        trace_id: 128-bit trace identifier, encoded as 32 hex characters.
        span_id: 64-bit span identifier, encoded as 16 hex characters.
        parent_span_id: Optional parent span identifier.
        sampled: Whether the trace is sampled for export.
        baggage: Optional key-value baggage for propagation.
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    sampled: bool = True
    baggage: dict[str, str] | None = None

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        if not _TRACE_ID_RE.fullmatch(value):
            raise ValueError("trace_id must be a 32-character hex string")
        return value

    @field_validator("span_id")
    @classmethod
    def validate_span_id(cls, value: str) -> str:
        if not _SPAN_ID_RE.fullmatch(value):
            raise ValueError("span_id must be a 16-character hex string")
        return value


class ErrorDetail(BaseModel):
    """Detailed error information for a specific failure condition.

    Attributes:
        type: Error type URI.
        field: Optional field name related to the error.
        reason: Human-readable reason for the error.
        metadata: Optional extra metadata for diagnostics.
    """

    type: str
    field: str | None = None
    reason: str
    metadata: dict[str, Any] | None = None


class DebugInfo(BaseModel):
    """Debug-only information that should not be returned in production.

    Attributes:
        stack_trace: Optional stack trace string.
        internal_message: Optional internal diagnostic message.
        timestamp_ms: Epoch timestamp in milliseconds.
    """

    stack_trace: str | None = None
    internal_message: str | None = None
    timestamp_ms: int


class RpcError(BaseModel):
    """Canonical RPC error payload for Aduib RPC v2.0 responses.

    Attributes:
        code: Numeric error code (see ErrorCode).
        name: Error name such as "INVALID_PARAMS".
        message: Human-readable error message.
        details: Optional list of structured error details.
        debug: Optional debug information for diagnostics.
    """

    code: int
    name: str
    message: str
    details: list[ErrorDetail] | None = None
    debug: DebugInfo | None = None

    @classmethod
    def from_exception(cls, exc: RpcException) -> "RpcError":
        """Create an RpcError from a RpcException instance.

        Args:
            exc: Exception to convert.

        Returns:
            RpcError populated from the exception data.
        """

        name = ERROR_CODE_NAMES.get(exc.code, "UNKNOWN")
        details = None
        if exc.data is not None and isinstance(exc.data, list):
            details = [
                item if isinstance(item, ErrorDetail) else ErrorDetail.model_validate(item)
                for item in exc.data
            ]
        return cls(code=int(exc.code), name=name, message=exc.message, details=details)


class AduibRpcRequest(BaseModel):
    """Aduib RPC v2.0 request envelope.

    Attributes:
        aduib_rpc: Protocol version identifier.
        id: Request identifier (UUID v4 recommended).
        method: RPC method path in the form "rpc.v2/{service}/{handler}".
        name: Optional service alias.
        data: Optional request payload.
        trace_context: Optional W3C trace context information.
        metadata: Optional metadata (typed in metadata.py).
        qos: Optional quality of service settings (typed in qos.py).
    """

    aduib_rpc: Literal["2.0"] = "2.0"
    id: str
    method: str
    name: str | None = None
    data: dict[str, Any] | None = None
    trace_context: TraceContext | None = None
    metadata: Any | None = None  # Typed in metadata.py.
    qos: Any | None = None  # Typed in qos.py.


class AduibRpcResponse(BaseModel):
    """Aduib RPC v2.0 response envelope.

    Attributes:
        aduib_rpc: Protocol version identifier.
        id: Identifier matching the request.
        status: Response status indicator.
        result: Optional response payload.
        error: Optional error payload.
        trace_context: Optional W3C trace context information.
        metadata: Optional metadata (typed later).
    """

    aduib_rpc: Literal["2.0"] = "2.0"
    id: str
    status: ResponseStatus
    result: Any | None = None
    error: RpcError | None = None
    trace_context: TraceContext | None = None
    metadata: Any | None = None  # Typed later.

    def is_success(self) -> bool:
        """Return True when the response is successful and has no error."""

        return self.status == ResponseStatus.SUCCESS and self.error is None

    @field_validator("error")
    @classmethod
    def validate_result_error(cls, value: RpcError | None, info) -> RpcError | None:
        result = info.data.get("result")
        if value is not None and result is not None:
            raise ValueError("result and error are mutually exclusive")
        return value


__all__ = [
    "AduibRpcRequest",
    "AduibRpcResponse",
    "DebugInfo",
    "ErrorDetail",
    "ResponseStatus",
    "RpcError",
    "TraceContext",
]
