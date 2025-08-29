from typing import AsyncGenerator, Any

from google.protobuf.json_format import Parse, MessageToDict, MessageToJson
from starlette.requests import Request

from aduib_rpc.grpc import aduib_rpc_pb2
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.utils import proto_utils


class RESTHandler:
    """ request handler base class """

    def __init__(self,request_handler: RequestHandler):
        """Initializes the RESTHandler.
        """
        self.request_handler = request_handler

    async def on_message(
            self,
            request: Request,
            context: ServerContext | None = None
    ) -> dict[str, Any]:
        """Handles the 'message' method.

        Args:
            request: The incoming http `Request` object.
            context: Context provided by the server.
        Returns:
            The `ChatCompletionResponse` object containing the response.
        """
        body = await request.body()
        params =aduib_rpc_pb2.RpcTask()
        Parse(body, params)
        # Transform the proto object to the python internal objects
        request = proto_utils.FromProto.rpc_request(
            params,
        )
        message = await self.request_handler.on_message(
            request, context
        )
        return MessageToDict(proto_utils.ToProto.rpc_response(message))

    async def on_stream_message(
            self,
            request: Request,
            context: ServerContext | None = None
    ) -> AsyncGenerator[str, None]:
        """Handles the 'stream_message' method.

        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.

        Yields:
            The `ChatCompletionResponse` object containing the response.
        """
        body = await request.body()
        params = aduib_rpc_pb2.RpcTask()
        Parse(body, params)
        # Transform the proto object to the python internal objects
        request = proto_utils.FromProto.rpc_request(
            params,
        )
        async for chunk in self.request_handler.on_stream_message(request, context):
            yield MessageToJson(proto_utils.ToProto.rpc_response(chunk))