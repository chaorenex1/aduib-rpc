import contextlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import grpc

from aduib_rpc.grpc import aduib_rpc_pb2
from aduib_rpc.grpc.aduib_rpc_pb2_grpc import AduibRpcServiceServicer
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.utils import proto_utils


class ServerContentBuilder(ABC):
    """Abstract base class for building server content."""

    @abstractmethod
    def build_context(self, context: grpc.aio.ServicerContext) -> ServerContext:
        """Builds and returns server content based on the provided data."""

class DefaultServerContentBuilder(ServerContentBuilder):
    """Default implementation of ServerContextBuilder."""

    def build_context(self, context: grpc.aio.ServicerContext) -> ServerContext:
        """Builds and returns a default ServerContext."""
        state={}
        with contextlib.suppress(Exception):
            state['grpc_context'] = context
            state['headers'] = dict(context.invocation_metadata() or {})
        return ServerContext(state=state,metadata=
                                dict(context.invocation_metadata() or {}))

class GrpcHandler(AduibRpcServiceServicer):
    """Maps incoming gRPC requests to the appropriate request handler method and formats responses."""

    def __init__(
        self,
        context_builder: ServerContentBuilder | None,
        request_handler: RequestHandler,
    ):
        """Initializes the GrpcHandler.

        Args:
          context_builder: The ServerContextBuilder instance to build server context.
          request_handler: The underlying `RequestHandler` instance to delegate requests to.
        """
        self.context_builder = context_builder or DefaultServerContentBuilder()
        self.request_handler = request_handler

    async def stream_completion(self, request:aduib_rpc_pb2.RpcTask,
                             context:grpc.aio.ServicerContext)->AsyncIterator[aduib_rpc_pb2.RpcTaskResponse]:
        """Handles the 'chatCompletion' gRPC method.

        Args:
            request: An iterator of incoming request messages.
            context: The gRPC ServicerContext.
        """
        try:
            server_context = self.context_builder.build_context(context)
            request=proto_utils.FromProto.rpc_request(request)
            async for response in self.request_handler.on_stream_message(request, server_context):
                yield proto_utils.ToProto.rpc_response(response)
        except Exception as e:
            await context.abort(
                    grpc.StatusCode.INTERNAL,
                    f'Internal server error: {e}',
                )
        return


    async def completion(self, request:aduib_rpc_pb2.RpcTask,
                             context:grpc.aio.ServicerContext)->aduib_rpc_pb2.RpcTaskResponse:
        """Handles the 'completion' gRPC method.

        Args:
            request: The incoming request message.
            context: The gRPC ServicerContext.
        """
        try:
            server_context = self.context_builder.build_context(context)
            request=proto_utils.FromProto.rpc_request(request)
            response = await self.request_handler.on_message(
                request, server_context
            )
            return proto_utils.ToProto.rpc_response(response)
        except Exception as e:
            await context.abort(
                    grpc.StatusCode.INTERNAL,
                    f'Internal server error: {e}',
                )
        return aduib_rpc_pb2.RpcTaskResponse()