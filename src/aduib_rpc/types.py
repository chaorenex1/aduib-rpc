"""Aduib RPC Types - v2 Protocol.

Primary types (v2):
    AduibRpcRequest - v2.0 request envelope
    AduibRpcResponse - v2.0 response envelope
    RpcError - v2.0 error structure
    TraceContext - W3C trace context
    RequestMetadata, ResponseMetadata - Structured metadata
    QosConfig - Quality of service configuration
    StreamMessage - Streaming message types
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, RootModel

from aduib_rpc.protocol.v2.types import (
    AduibRpcResponse as V2Response,
    AduibRpcRequest as V2Request,
)
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse
from aduib_rpc.server.tasks.types import (
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
)

# ============================================================
# v2 Protocol Types (Primary Export)
# ============================================================

# ============================================================
# Primary Type Exports (v2)
# ============================================================

AduibRpcRequest = V2Request
AduibRpcResponse = V2Response

# ============================================================
# JSON-RPC Union Types
# ============================================================

JsonRpcParams = Union[
    AduibRpcRequest,
    TaskSubmitRequest,
    TaskQueryRequest,
    TaskCancelRequest,
    TaskSubscribeRequest,
    HealthCheckRequest,
]

JsonRpcResult = Union[
    AduibRpcResponse,
    TaskSubmitResponse,
    TaskQueryResponse,
    TaskCancelResponse,
    TaskEvent,
    HealthCheckResponse,
]

# ============================================================
# JSON-RPC Wrapper Types
# ============================================================


class JSONRPCError(BaseModel):
    """Represents a JSON-RPC 2.0 Error object (code/message/data)."""

    code: int
    message: str
    data: Any | None = None


class JSONRPCErrorResponse(BaseModel):
    """Represents a JSON-RPC 2.0 Error Response object."""

    error: JSONRPCError
    id: str | int | None = None
    jsonrpc: Literal["2.0"] = "2.0"


class JSONRPCRequest(BaseModel):
    """Represents a JSON-RPC 2.0 Request object."""

    id: str | int | None = None
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: JsonRpcParams | None = None


class JSONRPCSuccessResponse(BaseModel):
    """Represents a successful JSON-RPC 2.0 Response object."""

    id: str | int | None = None
    jsonrpc: Literal["2.0"] = "2.0"
    result: JsonRpcResult


class JsonRpcMessageRequest(BaseModel):
    id: str | int
    jsonrpc: Literal["2.0"] = "2.0"
    # v2: JSON-RPC method carries the v2 RPC method path, e.g. "rpc.v2/UserService/GetUser".
    method: str
    params: JsonRpcParams | None = None


class JsonRpcStreamingMessageRequest(BaseModel):
    id: str | int
    jsonrpc: Literal["2.0"] = "2.0"
    # v2: JSON-RPC method carries the v2 RPC method path.
    method: str
    params: JsonRpcParams | None = None


class JsonRpcMessageSuccessResponse(BaseModel):
    id: str | int | None = None
    jsonrpc: Literal["2.0"] = "2.0"
    result: JsonRpcResult


class JsonRpcStreamingMessageSuccessResponse(BaseModel):
    id: str | int | None = None
    jsonrpc: Literal["2.0"] = "2.0"
    result: JsonRpcResult


class AduibJSONRPCResponse(
    RootModel[
        Union[
            JSONRPCErrorResponse,
            JsonRpcMessageSuccessResponse,
            JsonRpcStreamingMessageSuccessResponse,
        ]
    ]
):
    root: Union[
        JSONRPCErrorResponse,
        JsonRpcMessageSuccessResponse,
        JsonRpcStreamingMessageSuccessResponse,
    ]


class AduibJSONRpcRequest(
    RootModel[
        Union[
            JsonRpcMessageRequest,
            JsonRpcStreamingMessageRequest,
        ]
    ]
):
    root: Union[JsonRpcMessageRequest, JsonRpcStreamingMessageRequest]


class JsonRpcMessageResponse(RootModel[Union[JSONRPCErrorResponse, JsonRpcMessageSuccessResponse]]):
    root: Union[JSONRPCErrorResponse, JsonRpcMessageSuccessResponse]


class JsonRpcStreamingMessageResponse(RootModel[Union[JSONRPCErrorResponse, JsonRpcStreamingMessageSuccessResponse]]):
    root: Union[JSONRPCErrorResponse, JsonRpcStreamingMessageSuccessResponse]
