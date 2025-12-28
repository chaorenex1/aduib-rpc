import logging
from typing import AsyncGenerator, Any

from google.protobuf.json_format import Parse, MessageToDict, MessageToJson
from starlette.requests import Request

from aduib_rpc.grpc import aduib_rpc_pb2
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.types import AduibRpcResponse
from aduib_rpc.utils import proto_utils
from aduib_rpc.utils.error_handlers import exception_to_error

logger = logging.getLogger(__name__)


class RESTHandler:
    """ request handler base class """

    def __init__(self, request_handler: RequestHandler):
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
        try:
            body = await request.body()
            params = aduib_rpc_pb2.RpcTask()
            Parse(body, params)
            # Transform the proto object to the python internal objects
            request_obj = proto_utils.FromProto.rpc_request(
                params,
            )
            message = await self.request_handler.on_message(
                request_obj, context
            )
            return MessageToDict(proto_utils.ToProto.rpc_response(message))
        except Exception as e:
            logger.exception("RESTHandler on_message failed")
            err = exception_to_error(e)
            return MessageToDict(
                proto_utils.ToProto.rpc_response(
                    AduibRpcResponse(
                        id=getattr(context, "request_id", None) if context else None,
                        status="error",
                        error=err,
                    )
                )
            )

    async def on_stream_message(
            self,
            request: Request,
            context: ServerContext | None = None
    ) -> AsyncGenerator[str, None]:
        """Handles the 'stream_message' method.

        Args:
            request: The incoming http `Request` object.
            context: Context provided by the server.

        Yields:
            The `ChatCompletionResponse` object containing the streaming responses.
        """
        try:
            body = await request.body()
            params = aduib_rpc_pb2.RpcTask()
            Parse(body, params)
            # Transform the proto object to the python internal objects
            request_obj = proto_utils.FromProto.rpc_request(
                params,
            )
            async for chunk in self.request_handler.on_stream_message(request_obj, context):
                yield MessageToJson(proto_utils.ToProto.rpc_response(chunk))
        except Exception as e:
            logger.exception("RESTHandler on_stream_message failed")
            # For streaming, yield a single error event serialized as JSON.
            err = exception_to_error(e)
            yield MessageToJson(
                proto_utils.ToProto.rpc_response(
                    AduibRpcResponse(
                        id=getattr(context, "request_id", None) if context else None,
                        status="error",
                        error=err,
                    )
                )
            )
