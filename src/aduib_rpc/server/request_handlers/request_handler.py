from abc import ABC, abstractmethod
from typing import AsyncGenerator

from aduib_rpc.server.context import ServerContext, ServerInterceptor
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse


class RequestHandler(ABC):
    """ request handler base class """

    @abstractmethod
    async def on_message(
            self,
            message: AduibRpcRequest,
            context: ServerContext | None = None,
    )-> AduibRpcResponse:
        """Handles the 'message' method.

        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.
            interceptors: list of ServerInterceptor instances to process the request.

        Returns:
            The `AduibRpcResponse` object containing the response.
        """
        raise NotImplementedError("Method not implemented.")

    @abstractmethod
    async def on_stream_message(
            self,
            message: AduibRpcRequest,
            context: ServerContext | None = None,
    )-> AsyncGenerator[AduibRpcResponse, None]:
        """Handles the 'stream_message' method.

        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.
            interceptors: list of ServerInterceptor instances to process the request.

        Yields:
            The `AduibRpcResponse` objects containing the streaming responses.
        """
        raise NotImplementedError("Method not implemented.")
        yield