"""Aduib RPC Protocol v2.0."""

from __future__ import annotations

from aduib_rpc.protocol.v2.errors import (
    ERROR_CODE_NAMES,
    ErrorCode,
    error_code_to_grpc_status,
    error_code_to_http_status,
    exception_from_code,
    exception_to_rpc_error,
    is_debug_enabled,
    map_exception_to_error_code,
    reset_debug_cache,
    set_debug_enabled,
)
from aduib_rpc.protocol.v2.health import (
    HealthCheckRequest,
    HealthCheckResponse,
    HealthStatus,
)
from aduib_rpc.protocol.v2.metadata import (
    AuthContext,
    AuthScheme,
    RequestMetadata,
    ResponseMetadata,
)
from aduib_rpc.protocol.v2.qos import Priority, QosConfig
from aduib_rpc.protocol.v2.types import (
    AduibRpcRequest,
    AduibRpcResponse,
    DebugInfo,
    ErrorDetail,
    ResponseStatus,
    RpcError,
    TraceContext,
    get_current_trace_context,
    set_current_trace_context,
)

__all__ = [
    # Error handling
    "ErrorCode",
    "ERROR_CODE_NAMES",
    "error_code_to_http_status",
    "error_code_to_grpc_status",
    "exception_from_code",
    "map_exception_to_error_code",
    "exception_to_rpc_error",
    "is_debug_enabled",
    "set_debug_enabled",
    "reset_debug_cache",
    # Metadata
    "AuthScheme",
    "AuthContext",
    "RequestMetadata",
    "ResponseMetadata",
    # QoS
    "Priority",
    "QosConfig",
    # Health checks
    "HealthStatus",
    "HealthCheckRequest",
    "HealthCheckResponse",
    # Core request/response types
    "AduibRpcRequest",
    "AduibRpcResponse",
    "DebugInfo",
    "ErrorDetail",
    "ResponseStatus",
    "RpcError",
    "TraceContext",
    "get_current_trace_context",
    "set_current_trace_context",
]
