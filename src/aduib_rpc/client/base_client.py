import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Optional, Any

from aduib_rpc.client import ClientConfig
from aduib_rpc.client.midwares import ClientRequestInterceptor, ClientContext
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse

try:
    import httpx
    from grpc.aio import Channel
except ImportError:
    httpx = None  # type: ignore
    Channel = None  # type: ignore

logger=logging.getLogger(__name__)


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
        context.state['session_id'] = str(uuid.uuid4()) if not context.state.get('session_id') else context.state.get('session_id')
        context.state['http_kwargs'] = {'headers': meta['headers']} if meta and 'headers' in meta else context.state.get('http_kwargs')
        context.state['security_schema'] = meta['security_schema'] if 'security_schema' in meta else context.state.get('security_schema')
        if meta:
            if 'stream' in meta:
                logger.warning("The 'stream' meta field is managed by the client configuration and will be overridden.")
            meta['stream'] = str(self._config.streaming).lower()
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



