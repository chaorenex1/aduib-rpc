import dataclasses
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, AsyncIterator
from typing import Optional, Any

from aduib_rpc.client.midwares import ClientRequestInterceptor, ClientContext
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse

try:
    import httpx
    from grpc.aio import Channel
except ImportError:
    httpx = None  # type: ignore
    Channel = None  # type: ignore

from aduib_rpc.utils.constant import TransportSchemes


@dataclasses.dataclass
class ClientConfig:
    """Client configuration class."""
    streaming: bool = True
    """Whether to use streaming mode for message sending."""
    httpx_client: httpx.AsyncClient | None = None
    """Http client to use to connect to agent."""

    grpc_channel_factory: Callable[[str], Channel] | None = None
    """Generates a grpc connection channel for a given url."""

    supported_transports: list[TransportSchemes | str] = dataclasses.field(
        default_factory=list
    )

class AduibRpcClient(ABC):
    """Abstract base class for a client."""

    def __init__(
        self,
        middleware: list[ClientRequestInterceptor] | None = None,
    ):
        self._middleware = middleware
        if self._middleware is None:
            self._middleware = []


    @abstractmethod
    async def completion(
        self,
        method: str,
        data: Any= None,
        meta: Optional[dict[str, Any]] = None,
        *,
        context: ClientContext | None = None,
    ) -> AsyncIterator[AduibRpcResponse]:
        """Sends a message to the agent.

        This method handles both streaming and non-streaming (polling) interactions
        based on the client configuration and agent capabilities. It will yield
        events as they are received from the agent.

        Args:
            method: The RPC method to call.
            data: The data to send in the request.
            meta: Optional metadata to include in the request.
            context: The client call context.
        """
        return
        yield

    async def add_middleware(
        self,
        middleware: ClientRequestInterceptor,
    ) -> None:
        """Adds a middleware to the client.

        Args:
            middleware: The middleware to add.
        """
        self._middleware.append(middleware)



class BaseAduibRpcClient(AduibRpcClient):
    """Base implementation of the AduibRpc client, containing transport-independent logic."""

    def __init__(
        self,
        config: ClientConfig,
        transport: ClientTransport,
        middleware: list[ClientRequestInterceptor] | None = None,
    ):
        super().__init__(middleware)
        self._config = config
        self._transport = transport

    async def completion(self,
                         method: str,
                         data: Any = None,
                         meta: Optional[dict[str, Any]] = None,
                         *,
                         context: ClientContext | None = None) -> AsyncIterator[
        AduibRpcResponse]:
        """Sends a message to the agent.
        This method handles both streaming and non-streaming (polling) interactions
        based on the client configuration and agent capabilities. It will yield
        events as they are received from the agent.
        Args:
            method: The RPC method to call.
            data: The data to send in the request.
            meta: Optional metadata to include in the request.
            context: The client call context.
        Returns:
            An async iterator yielding `AduibRpcResponse` objects as they are received.
        """
        if context is None:
            context = ClientContext()
        context.state['session_id'] = str(uuid.uuid4())
        context.state['http_kwargs'] = {'headers': meta['headers']} if meta and 'headers' in meta else {}
        context.state['schema'] = meta['schema'] if 'schema' in meta else None
        request = AduibRpcRequest(method=method, data=data, meta=meta,id=str(uuid.uuid4()))
        if not self._config.streaming:
            response = await self._transport.completion(
                request, context=context
            )
            yield response
            return

        async for response in self._transport.completion_stream(
            request, context=context
        ):
            yield response



