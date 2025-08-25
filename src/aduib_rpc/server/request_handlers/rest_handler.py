from typing import AsyncGenerator

from google.protobuf.json_format import Parse
from starlette.requests import Request

from aduib_rpc.grpc.chat_completion_pb2 import ChatCompletion
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.types import ChatCompletionResponseChunk, ChatCompletionResponse
from aduib_rpc.utils import proto_utils


class RESTHandler:
    """ request handler base class """

    def __init__(self,request_handler: RequestHandler):
        """Initializes the RESTHandler.
        """
        self.request_handler = request_handler

    @staticmethod
    async def on_message(
            self,
            request: Request,
            context: ServerContext | None = None
    ) -> ChatCompletionResponse:
        """Handles the 'message' method.

        Args:
            request: The incoming http `Request` object.
            context: Context provided by the server.
        Returns:
            The `ChatCompletionResponse` object containing the response.
        """
        body = await request.body()
        params = ChatCompletion()
        Parse(body, params)
        # Transform the proto object to the python internal objects
        completion_request = proto_utils.FromProto.completion_request(
            params,
        )
        message = await self.request_handler.on_message(
            completion_request, context
        )
        return message

    @staticmethod
    async def on_stream_message(
            self,
            request: Request,
            context: ServerContext | None = None
    ) -> AsyncGenerator[ChatCompletionResponseChunk]:
        """Handles the 'stream_message' method.

        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.

        Yields:
            The `ChatCompletionResponse` object containing the response.
        """
        body = await request.body()
        params = ChatCompletion()
        Parse(body, params)
        # Transform the proto object to the python internal objects
        completion_request = proto_utils.FromProto.chat_completion_request(
            params,
        )
        async for chunk in self.request_handler.on_stream_message(
                completion_request, context
        ):
            yield chunk