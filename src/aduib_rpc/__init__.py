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
]

