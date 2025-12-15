from typing import TypeVar
from typing import Optional, Union, Literal, Any
from typing import TypeVar

from pydantic import BaseModel, RootModel

T=TypeVar('T')
class AduibRPCError(BaseModel):
    """
    Represents a JSON-RPC 2.0 Error object, included in an error response.
    """

    code: int
    """
    A number that indicates the error type that occurred.
    """
    data: Any | None = None
    """
    A primitive or structured value containing additional information about the error.
    This may be omitted.
    """
    message: str
    """
    A string providing a short description of the error.
    """

class AduibRpcRequest(BaseModel):
    aduib_rpc: Literal['1.0'] = '1.0'
    method: str
    data: Union[dict[str, Any],Any, None] = None
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
    result: Union[dict[str, Any],Any, None] = None
    error: Optional[AduibRPCError] = None
    id: Union[str, int, None] = None
    status: str = 'success' # 'success' or 'error'

    def is_success(self) -> bool:
        return self.status == 'success' and self.error is None

    def cast(self, typ: type) -> Any:
        if self.result is None:
            return None
        if isinstance(self.result, typ):
            return self.result
        return typ(**self.result)

"""
jsonrpc types
"""

class JSONRPCError(BaseModel):
    """
    Represents a JSON-RPC 2.0 Error object, included in an error response.
    """

    code: int
    """
    A number that indicates the error type that occurred.
    """
    data: Any | None = None
    """
    A primitive or structured value containing additional information about the error.
    This may be omitted.
    """
    message: str
    """
    A string providing a short description of the error.
    """

class JSONRPCErrorResponse(BaseModel):
    """
    Represents a JSON-RPC 2.0 Error Response object.
    """

    error: (
        JSONRPCError
    )
    """
    An object describing the error that occurred.
    """
    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """

class JSONRPCRequest(BaseModel):
    """
    Represents a JSON-RPC 2.0 Request object.
    """

    id: str | int | None = None
    """
    A unique identifier established by the client. It must be a String, a Number, or null.
    The server must reply with the same value in the response. This property is omitted for notifications.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    method: str
    """
    A string containing the name of the method to be invoked.
    """
    params: dict[str, Any] | None = None
    """
    A structured value holding the parameter values to be used during the method invocation.
    """


class JSONRPCSuccessResponse(BaseModel):
    """
    Represents a successful JSON-RPC 2.0 Response object.
    """

    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    result: Any
    """
    The value of this member is determined by the method invoked on the Server.
    """

class JsonRpcMessageRequest(BaseModel):
    """
    Represents a JSON-RPC request for the `message/send` method.
    """

    id: str | int
    """
    The identifier for this request.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    method: Literal['message/completion'] = 'message/completion'
    """
    The method name. Must be 'message/completion'.
    """
    params: AduibRpcRequest
    """
    The parameters for sending a message.
    """

class JsonRpcStreamingMessageRequest(BaseModel):
    """
    Represents a JSON-RPC request for the `message/stream` method.
    """

    id: str | int
    """
    The identifier for this request.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    method: Literal['message/completion/stream'] = 'message/completion/stream'
    """
    The method name. Must be 'message/completion/stream'.
    """
    params: AduibRpcRequest
    """
    The parameters for sending a message.
    """

class JsonRpcMessageSuccessResponse(BaseModel):
    """
    Represents a successful JSON-RPC response for the `message/send` method.
    """

    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    result: AduibRpcResponse
    """
    The result, which can be a direct reply Message or the initial Task object.
    """


class JsonRpcStreamingMessageSuccessResponse(BaseModel):
    """
    Represents a successful JSON-RPC response for the `message/stream` method.
    The server may send multiple response objects for a single request.
    """

    id: str | int | None = None
    """
    The identifier established by the client.
    """
    jsonrpc: Literal['2.0'] = '2.0'
    """
    The version of the JSON-RPC protocol. MUST be exactly "2.0".
    """
    result: AduibRpcResponse
    """
    The result, which can be a Message, Task, or a streaming update event.
    """
class AduibJSONRPCResponse(
    RootModel[
        JSONRPCErrorResponse
        | JsonRpcMessageSuccessResponse
        | JsonRpcStreamingMessageSuccessResponse
    ]):
    root: (
        JSONRPCErrorResponse
        | JsonRpcMessageSuccessResponse
        | JsonRpcStreamingMessageSuccessResponse
    )
    """
    Represents a JSON-RPC response envelope.
    """

class AduibJSONRpcRequest(
    RootModel[JsonRpcMessageRequest
              |JsonRpcStreamingMessageRequest
              ]):
    root: (JsonRpcMessageRequest
           | JsonRpcStreamingMessageRequest)
    """
    Represents a JSON-RPC request envelope.
    """


class JsonRpcMessageResponse(
    RootModel[JSONRPCErrorResponse | JsonRpcMessageSuccessResponse]
):
    root: JSONRPCErrorResponse | JsonRpcMessageSuccessResponse
    """
    Represents a JSON-RPC response for the `message/send` method.
    """


class JsonRpcStreamingMessageResponse(
    RootModel[JSONRPCErrorResponse | JsonRpcStreamingMessageSuccessResponse]
):
    root: JSONRPCErrorResponse | JsonRpcStreamingMessageSuccessResponse
    """
    Represents a JSON-RPC response for the `message/stream` method.
    """
