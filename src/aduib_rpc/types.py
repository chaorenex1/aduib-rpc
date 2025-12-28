from __future__ import annotations

from typing import Any, Literal, Optional, TypeVar, Union
from pydantic import BaseModel, RootModel

T = TypeVar('T')


class AduibRpcError(BaseModel):
    """Canonical error shape used across transports.

    This intentionally matches the JSON-RPC error object structure (code/message/data),
    but is also reused by the Aduib RPC 1.0 envelope.
    """

    code: int
    message: str
    data: Any | None = None


# Backward compatible alias (old name)
AduibRPCError = AduibRpcError


class AduibRpcRequest(BaseModel):
    aduib_rpc: Literal['1.0'] = '1.0'
    method: str
    data: Union[dict[str, Any], Any, None] = None
    meta: Optional[dict[str, Any]] = None
    id: Union[str, int, None] = None

    def add_meta(self, key: str, value: Any) -> None:
        if self.meta is None:
            self.meta = {}
        self.meta[key] = value

    def cast(self, typ: type) -> Any:
        if self.data is None:
            return None
        if isinstance(self.data, typ):
            return self.data
        return typ(**self.data)


class AduibRpcResponse(BaseModel):
    aduib_rpc: Literal['1.0'] = '1.0'
    result: Union[dict[str, Any], Any, None] = None
    error: Optional[AduibRpcError] = None
    id: Union[str, int, None] = None
    status: str = 'success'  # 'success' or 'error'

    def is_success(self) -> bool:
        return self.status == 'success' and self.error is None

    def cast(self, typ: type) -> Any:
        if self.result is None:
            return None
        if isinstance(self.result, typ):
            return self.result
        return typ(**self.result)


"""jsonrpc types"""


# Backward compatible alias: JSONRPCError is the same shape as our canonical error
JSONRPCError = AduibRpcError


class JSONRPCErrorResponse(BaseModel):
    """Represents a JSON-RPC 2.0 Error Response object."""

    error: JSONRPCError
    id: str | int | None = None
    jsonrpc: Literal['2.0'] = '2.0'


class JSONRPCRequest(BaseModel):
    """Represents a JSON-RPC 2.0 Request object."""

    id: str | int | None = None
    jsonrpc: Literal['2.0'] = '2.0'
    method: str
    params: dict[str, Any] | None = None


class JSONRPCSuccessResponse(BaseModel):
    """Represents a successful JSON-RPC 2.0 Response object."""

    id: str | int | None = None
    jsonrpc: Literal['2.0'] = '2.0'
    result: Any


class JsonRpcMessageRequest(BaseModel):
    id: str | int
    jsonrpc: Literal['2.0'] = '2.0'
    method: Literal['message/completion'] = 'message/completion'
    params: AduibRpcRequest


class JsonRpcStreamingMessageRequest(BaseModel):
    id: str | int
    jsonrpc: Literal['2.0'] = '2.0'
    method: Literal['message/completion/stream'] = 'message/completion/stream'
    params: AduibRpcRequest


class JsonRpcMessageSuccessResponse(BaseModel):
    id: str | int | None = None
    jsonrpc: Literal['2.0'] = '2.0'
    result: AduibRpcResponse


class JsonRpcStreamingMessageSuccessResponse(BaseModel):
    id: str | int | None = None
    jsonrpc: Literal['2.0'] = '2.0'
    result: AduibRpcResponse


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


class JsonRpcMessageResponse(
    RootModel[Union[JSONRPCErrorResponse, JsonRpcMessageSuccessResponse]]
):
    root: Union[JSONRPCErrorResponse, JsonRpcMessageSuccessResponse]


class JsonRpcStreamingMessageResponse(
    RootModel[Union[JSONRPCErrorResponse, JsonRpcStreamingMessageSuccessResponse]]
):
    root: Union[JSONRPCErrorResponse, JsonRpcStreamingMessageSuccessResponse]
