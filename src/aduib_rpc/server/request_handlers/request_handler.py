from abc import ABC
from typing import AsyncGenerator

from aduib_rpc.server.context import ServerContext
from aduib_rpc.types import CompletionRequest, ChatCompletionResponse, ChatCompletionResponseChunk, \
    ChatCompletionRequest


class RequestHandler(ABC):
    """ request handler base class """

    @staticmethod
    async def on_message(
            message: CompletionRequest | ChatCompletionRequest,
            context: ServerContext | None = None
    )-> ChatCompletionResponse:
        """Handles the 'message' method.

        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.

        Returns:
            The `ChatCompletionResponse` object containing the response.
        """
        raise NotImplementedError("Method not implemented.")

    @staticmethod
    async def on_stream_message(
            message: CompletionRequest | ChatCompletionRequest,
            context: ServerContext | None = None
    )-> AsyncGenerator[ChatCompletionResponseChunk]:
        """Handles the 'stream_message' method.

        Args:
            message: The incoming `CompletionRequest` object.
            context: Context provided by the server.

        Yields:
            The `ChatCompletionResponse` object containing the response.
        """
        raise NotImplementedError("Method not implemented.")
        yield