"""Public API for aduib_rpc.

This module intentionally re-exports the stable, supported surface area of the
library. Import from here when possible.
"""

from aduib_rpc.types import (
    AduibRPCError,
    AduibRpcError,
    AduibRpcRequest,
    AduibRpcResponse,
    AduibJSONRpcRequest,
    AduibJSONRPCResponse,
    JSONRPCError,
    JSONRPCErrorResponse,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)

from aduib_rpc.server.rpc_execution.runtime import RpcRuntime, get_runtime
from aduib_rpc.server.rpc_execution.service_call import (
    client,
    client_function,
    service,
    service_function,
)

# Optional telemetry (requires `aduib-rpc[telemetry]`)
try:
    from aduib_rpc.telemetry.config import TelemetryConfig
    from aduib_rpc.telemetry.setup import configure_telemetry
except Exception:  # pragma: no cover
    TelemetryConfig = None  # type: ignore
    configure_telemetry = None  # type: ignore

__all__ = [
    # types
    "AduibRpcError",
    "AduibRPCError",
    "AduibRpcRequest",
    "AduibRpcResponse",
    "AduibJSONRpcRequest",
    "AduibJSONRPCResponse",
    "JSONRPCError",
    "JSONRPCErrorResponse",
    "JSONRPCRequest",
    "JSONRPCSuccessResponse",
    # runtime
    "RpcRuntime",
    "get_runtime",
    # decorators
    "service",
    "service_function",
    "client",
    "client_function",
    # optional telemetry
    "TelemetryConfig",
    "configure_telemetry",
]
