from __future__ import annotations

import contextvars
import re
import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, field_serializer, field_validator

from aduib_rpc.exceptions import RpcException
from aduib_rpc.protocol.v2 import RequestMetadata
from aduib_rpc.protocol.v2.errors import ERROR_CODE_NAMES

_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-fA-F]{16}$")


class ResponseStatus(StrEnum):
    """Response status for Aduib RPC v2."""

    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"

    @classmethod
    def from_proto(cls, value: Any) -> "ResponseStatus":
        return cls._from_wire(value)

    @classmethod
    def from_thrift(cls, value: Any) -> "ResponseStatus":
        return cls._from_wire(value)

    @classmethod
    def _from_wire(cls, value: Any) -> "ResponseStatus":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.ERROR
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "success":
                return cls.SUCCESS
            if key == "error":
                return cls.ERROR
            if key == "partial":
                return cls.PARTIAL
            try:
                raw = int(raw)
            except Exception:
                return cls.ERROR
        try:
            num = int(raw)
        except Exception:
            return cls.ERROR
        if num == 1:
            return cls.SUCCESS
        if num == 2:
            return cls.ERROR
        if num == 3:
            return cls.PARTIAL
        return cls.ERROR

    @classmethod
    def to_proto(cls, value: "ResponseStatus | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def to_thrift(cls, value: "ResponseStatus | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def _to_wire(cls, value: "ResponseStatus | str | int | None") -> int:
        if value is None:
            return 0
        if isinstance(value, cls):
            if value == cls.SUCCESS:
                return 1
            if value == cls.ERROR:
                return 2
            if value == cls.PARTIAL:
                return 3
            return 0
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "success":
                return 1
            if key == "error":
                return 2
            if key == "partial":
                return 3
            try:
                raw = int(raw)
            except Exception:
                return 0
        try:
            num = int(raw)
        except Exception:
            return 0
        if num == 1:
            return 1
        if num == 2:
            return 2
        if num == 3:
            return 3
        return 0


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

    @classmethod
    def create(cls, sampled: bool = True, baggage: dict[str, str] | None = None) -> "TraceContext":
        trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]
        return cls(trace_id=trace_id, span_id=span_id, sampled=sampled, baggage=baggage)


_trace_ctx: contextvars.ContextVar[TraceContext] = contextvars.ContextVar(
    "aduib_rpc_trace_ctx",
)

def get_current_trace_context() -> TraceContext | None:
    """Get the current TraceContext from context variables, if set."""
    try:
        return _trace_ctx.get()
    except LookupError:
        return None

def set_current_trace_context(trace_context: TraceContext) -> None:
    """Set the current TraceContext in context variables."""
    _trace_ctx.set(trace_context)


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
        supported_versions: Optional list of protocol versions the client supports.
        trace_context: Optional W3C trace context information.
        metadata: Optional metadata (typed in metadata.py).
        qos: Optional quality of service settings (typed in qos.py).
        meta: Optional unstructured metadata for transport/client hints.
    """

    aduib_rpc: Literal["2.0"] = "2.0"
    id: str | None = None
    method: str
    name: str | None = None
    data: dict[str, Any] | None = None
    supported_versions: list[str] | None = None  # Protocol version negotiation (spec 2.2)
    trace_context: TraceContext | None = None
    metadata: RequestMetadata | None = None  # Typed in metadata.py.
    qos: Any | None = None  # Typed in qos.py.
    meta: dict[str, Any] | None = None
    _id_str: str | None = None  # Internal storage for string ID

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: Any) -> str | None:
        """Convert id to string for internal storage."""
        if value is None:
            return None
        return str(value)

    @field_serializer("id")
    def serialize_id(self, value: Any) -> str:
        """Serialize id as string."""
        if value is None:
            return str(uuid.uuid4())
        return str(value)

    @property
    def id_str(self) -> str:
        """Get the string ID (generates one if None)."""
        if self._id_str:
            return self._id_str
        if self.id is None:
            self._id_str = str(uuid.uuid4())
        else:
            self._id_str = str(self.id)
        return self._id_str

    @classmethod
    def create(cls,
               id: str,
               name: str,
               method: str,
               data: dict[str, Any] | None = None,
               meta: dict[str, Any] | None = None
               ,*,
               trace_context:TraceContext,
               qos:Any,
               metadata:Any) -> "AduibRpcRequest":
        """Helper to create a request with minimal parameters.

        Args:
            id: Request identifier.
            method: RPC method path.
            data: Optional request payload.

        Returns:
            AduibRpcRequest instance.
        """

        return cls(id=id,
                    name=name,
                   method=method,
                   data=data,
                   meta=meta,
                   trace_context=trace_context,
                   qos=qos,
                   metadata=metadata,
                   _id_str=str(uuid.uuid4()))


class AduibRpcResponse(BaseModel):
    """Aduib RPC v2.0 response envelope.

    Attributes:
        aduib_rpc: Protocol version identifier.
        id: Identifier matching the request.
        status: Response status indicator.
        result: Optional response payload.
        error: Optional error payload.
        negotiated_version: The protocol version negotiated for this response (spec 2.2).
        trace_context: Optional W3C trace context information.
        metadata: Optional metadata (typed later).
    """

    aduib_rpc: Literal["2.0"] = "2.0"
    id: str | None = None
    status: ResponseStatus = ResponseStatus.SUCCESS
    result: Any | None = None
    error: RpcError | None = None
    negotiated_version: str | None = None  # Protocol version negotiation (spec 2.2)
    trace_context: TraceContext | None = None
    metadata: Any | None = None  # Typed later.

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: Any) -> str | None:
        """Convert id to string for internal storage."""
        if value is None:
            return None
        return str(value)

    @field_serializer("id")
    def serialize_id(self, value: Any) -> str:
        """Serialize id as string."""
        if value is None:
            return ""
        return str(value)

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

