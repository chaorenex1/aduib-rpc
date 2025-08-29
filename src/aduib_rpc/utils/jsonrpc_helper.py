"""Helper functions for building JSON-RPC response objects."""
from typing import TypeVar

from aduib_rpc.types import ChatCompletionResponse, ChatCompletionResponseChunk, JsonRpcMessageSuccessResponse, \
    JsonRpcStreamingMessageSuccessResponse, JsonRpcMessageResponse, JsonRpcStreamingMessageResponse, JSONRPCError, \
    JSONRPCErrorResponse, AduibRpcResponse

RT = TypeVar(
    'RT',
    JsonRpcMessageResponse,
    JsonRpcStreamingMessageResponse,
)
"""Type variable for RootModel response types."""

# success types
SPT = TypeVar(
    'SPT',
    JsonRpcMessageSuccessResponse,
    JsonRpcStreamingMessageSuccessResponse,
)
"""Type variable for SuccessResponse types."""

# result types
EventTypes = (
    AduibRpcResponse
    | ChatCompletionResponse
    | ChatCompletionResponseChunk
)
"""Type alias for possible event types produced by handlers."""


def build_error_response(
    request_id: str | int | None,
    error: JSONRPCError,
    response_wrapper_type: type[RT],
) -> RT:
    """Helper method to build a JSONRPCErrorResponse wrapped in the appropriate response type.
    Args:
        request_id: The ID of the request.
        error: The JSONRPCError object containing error details.
        response_wrapper_type: The Pydantic RootModel type that wraps the final response
    :returns:
    A Pydantic model representing the JSON-RPC error response.
    """

    return response_wrapper_type(
        JSONRPCErrorResponse(
            id=request_id,
            error=error,
        )
    )


def prepare_response_object(
    request_id: str | int | None,
    response: EventTypes,
    success_response_types: tuple[type, ...],
    success_payload_type: type[SPT],
    response_type: type[RT],
) -> RT:
    """Prepares a JSON-RPC response object based on the handler's response.
    Args:
        request_id: The ID of the request.
        response: The response object from the handler.
        success_response_types: A tuple of types that are considered successful responses.
        success_payload_type: The Pydantic model type that wraps successful responses.
        response_type: The Pydantic RootModel type that wraps the final response.
    :returns:
    A Pydantic model representing the JSON-RPC response.
    """
    if isinstance(response, success_response_types):
        return response_type(
            root=success_payload_type(id=request_id, result=response)  # type:ignore
        )


    if isinstance(response,JSONRPCError):
        return build_error_response(request_id, response, response_type)

    response = JSONRPCError(
        code=-32603,
        message='Internal error',
        data=f'Handler returned invalid response type: {type(response)}'
    )

    return build_error_response(request_id, response, response_type)
