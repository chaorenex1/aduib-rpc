from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from aduib_rpc.client.midwares import ClientContext
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse


class ClientTransport(ABC):
    """Abstract base class for client transport mechanisms."""

    @abstractmethod
    async def completion(self,
                   request: AduibRpcRequest,
                   *,
                   context: ClientContext) -> AduibRpcResponse:
        """Sends a request and returns the response.
        Args:
            request: The `AduibRpcRequest` object to be sent.
            context: Context provided by the client.
        Returns:
            The `AduibRpcResponse` object containing the response.
        """

    @abstractmethod
    async def completion_stream(self,
                            request: AduibRpcRequest,
                            *,
                            context: ClientContext) -> AsyncGenerator[AduibRpcResponse, None]:
        """Sends a request and returns an async generator for streaming responses.
        Args:
            request: The `AduibRpcRequest` object to be sent.
            context: Context provided by the client.
        Yields:
            The `AduibRpcResponse` objects containing the streaming responses.
        """
        return
        yield