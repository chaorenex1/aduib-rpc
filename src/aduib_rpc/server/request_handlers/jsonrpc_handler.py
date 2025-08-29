import logging
from collections.abc import AsyncIterable

from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.types import JsonRpcMessageRequest, \
    JsonRpcMessageResponse, JsonRpcMessageSuccessResponse, JsonRpcStreamingMessageRequest, \
    JsonRpcStreamingMessageSuccessResponse, JsonRpcStreamingMessageResponse, JSONRPCErrorResponse, AduibRpcResponse
from aduib_rpc.utils.jsonrpc_helper import prepare_response_object

logger = logging.getLogger(__name__)


class JSONRPCHandler:
    """Maps incoming JSON-RPC requests to the appropriate request handler method and formats responses."""

    def __init__(
        self,
        request_handler: RequestHandler,
    ):
        """Initializes the JSONRPCHandler.

        Args:
            request_handler: The underlying `RequestHandler` instance to delegate requests to.
              the extended agent card before it is served. It receives the
              call context.
        """
        self.request_handler = request_handler

    async def on_message(
        self,
        request: JsonRpcMessageRequest,
        context: ServerContext | None = None,
    ) -> JsonRpcMessageResponse:
        """Handles the 'message/send' JSON-RPC method.

        Args:
            request: The incoming `SendMessageRequest` object.
            context: Context provided by the server.

        Returns:
            A `SendMessageResponse` object containing the result (Task or Message)
            or a JSON-RPC error response if a `ServerError` is raised by the handler.
        """
        try:
            message = await self.request_handler.on_message(
                request.params, context
            )
            return prepare_response_object(
                request.id,
                message,
                (AduibRpcResponse,),
                JsonRpcMessageSuccessResponse,
                JsonRpcMessageResponse,
            )
        except Exception as e:
            return JsonRpcMessageResponse(
                root=JSONRPCErrorResponse(
                    id=request.id, error=str(e)
                )
            )

    async def on_stream_message(
        self,
        request: JsonRpcStreamingMessageRequest,
        context: ServerContext | None = None,
    ) -> AsyncIterable[JsonRpcStreamingMessageResponse]:
        """Handles the 'message/stream' JSON-RPC method.

        Yields response objects as they are produced by the underlying handler's stream.

        Args:
            request: The incoming `SendStreamingMessageRequest` object.
            context: Context provided by the server.

        Yields:
            `SendStreamingMessageResponse` objects containing streaming events
            (Task, Message, TaskStatusUpdateEvent, TaskArtifactUpdateEvent)
            or JSON-RPC error responses if a `ServerError` is raised.
        """
        try:
            async for event in self.request_handler.on_stream_message(request.params, context):
                yield prepare_response_object(
                    request.id,
                    event,
                    (
                        AduibRpcResponse,
                    ),
                    JsonRpcStreamingMessageSuccessResponse,
                    JsonRpcStreamingMessageResponse,
                )
        except Exception as e:
            yield JsonRpcStreamingMessageResponse(
                root=JSONRPCErrorResponse(id=request.id, error=str(e))
            )
