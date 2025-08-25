import contextlib
from abc import ABC, abstractmethod

import grpc
from a2a import types
from a2a.utils.errors import ServerError

from aduib_rpc.grpc.chat_completion_pb2 import ChatCompletion
from aduib_rpc.grpc.chat_completion_response_pb2 import ChatCompletionResponse
from aduib_rpc.grpc.completion_rpc_pb2_grpc import ChatCompletionServiceServicer
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.utils import proto_utils


class ServerContentBuilder(ABC):
    """Abstract base class for building server content."""

    @abstractmethod
    def build_context(self, context: grpc.aio.ServicerContext) -> ServerContext:
        """Builds and returns server content based on the provided data."""

class DefaultServerContentBuilder(ServerContentBuilder):
    """Default implementation of ServerContentBuilder."""

    def build_context(self, context: grpc.aio.ServicerContext) -> ServerContext:
        """Builds and returns a default ServerContext."""
        state={}
        with contextlib.suppress(Exception):
            state['grpc_context'] = context
        return ServerContext(state=state,metadata=
                                dict(context.invocation_metadata() or {}))

class GrpcHandler(ChatCompletionServiceServicer):
    """Maps incoming gRPC requests to the appropriate request handler method and formats responses."""

    def __init__(
        self,
        context_builder: ServerContentBuilder,
        request_handler: RequestHandler,
    ):
        """Initializes the GrpcHandler.

        Args:
          context_builder: The ServerContentBuilder instance to build server context.
          request_handler: The underlying `RequestHandler` instance to delegate requests to.
        """
        self.context_builder = context_builder or DefaultServerContentBuilder()
        self.request_handler = request_handler

    async def chatCompletion(self, request:ChatCompletion,
                             context:grpc.aio.ServicerContext):
        """Handles the 'chatCompletion' gRPC method.

        Args:
            request: An iterator of incoming request messages.
            context: The gRPC ServicerContext.
        """
        try:
            server_context = self.context_builder.build_context(context)
            chat_completion_request=proto_utils.FromProto.chat_completion_request(request)
            async for response in self.request_handler.on_stream_message(
                chat_completion_request, server_context
            ):
                yield proto_utils.ToProto.chat_completion_response(response)
        except ServerError as e:
            await self.abort_context(e, context)
        return


    async def completion(self, request, context):
        """Handles the 'completion' gRPC method.

        Args:
            request: The incoming request message.
            context: The gRPC ServicerContext.
        """
        try:
            server_context = self.context_builder.build_context(context)
            chat_completion_request=proto_utils.FromProto.completion_request(request)
            response = await self.request_handler.on_message(
                chat_completion_request, server_context
            )
            return proto_utils.ToProto.chat_completion_response(response)
        except ServerError as e:
            return await self.abort_context(e, context)
        return ChatCompletionResponse()


    async def abort_context(
            self, error: ServerError, context: grpc.aio.ServicerContext
    ) -> None:
        """Sets the grpc errors appropriately in the context."""
        match error.error:
            case types.JSONParseError():
                await context.abort(
                    grpc.StatusCode.INTERNAL,
                    f'JSONParseError: {error.error.message}',
                )
            case types.InvalidRequestError():
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f'InvalidRequestError: {error.error.message}',
                )
            case types.MethodNotFoundError():
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f'MethodNotFoundError: {error.error.message}',
                )
            case types.InvalidParamsError():
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f'InvalidParamsError: {error.error.message}',
                )
            case types.InternalError():
                await context.abort(
                    grpc.StatusCode.INTERNAL,
                    f'InternalError: {error.error.message}',
                )
            case types.TaskNotFoundError():
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f'TaskNotFoundError: {error.error.message}',
                )
            case types.TaskNotCancelableError():
                await context.abort(
                    grpc.StatusCode.UNIMPLEMENTED,
                    f'TaskNotCancelableError: {error.error.message}',
                )
            case types.PushNotificationNotSupportedError():
                await context.abort(
                    grpc.StatusCode.UNIMPLEMENTED,
                    f'PushNotificationNotSupportedError: {error.error.message}',
                )
            case types.UnsupportedOperationError():
                await context.abort(
                    grpc.StatusCode.UNIMPLEMENTED,
                    f'UnsupportedOperationError: {error.error.message}',
                )
            case types.ContentTypeNotSupportedError():
                await context.abort(
                    grpc.StatusCode.UNIMPLEMENTED,
                    f'ContentTypeNotSupportedError: {error.error.message}',
                )
            case types.InvalidAgentResponseError():
                await context.abort(
                    grpc.StatusCode.INTERNAL,
                    f'InvalidAgentResponseError: {error.error.message}',
                )
            case _:
                await context.abort(
                    grpc.StatusCode.UNKNOWN,
                    f'Unknown error type: {error.error}',
                )

