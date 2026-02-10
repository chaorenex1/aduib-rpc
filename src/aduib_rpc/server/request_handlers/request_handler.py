from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from aduib_rpc.server.context import ServerContext
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse
from aduib_rpc.server.tasks.types import (
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
)


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

    @abstractmethod
    async def call(
            self,
            request: AduibRpcRequest,
            context: ServerContext | None = None,
    ) -> AduibRpcResponse:
        """Handles AduibRpcService.Call."""
        return await self.on_message(request, context)

    @abstractmethod
    async def call_server_stream(
            self,
            request: AduibRpcRequest,
            context: ServerContext | None = None,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        """Handles AduibRpcService.CallServerStream."""
        async for response in self.on_stream_message(request, context):
            yield response

    @abstractmethod
    async def call_client_stream(
            self,
            requests: AsyncIterator[AduibRpcRequest],
            context: ServerContext | None = None,
    ) -> AduibRpcResponse:
        """Handles AduibRpcService.CallClientStream."""
        request = await self._collect_stream_request(requests)
        return await self.on_message(request, context)

    @abstractmethod
    async def call_bidirectional(
            self,
            requests: AsyncIterator[AduibRpcRequest],
            context: ServerContext | None = None,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        """Handles AduibRpcService.CallBidirectional."""
        request = await self._collect_stream_request(requests)
        async for response in self.on_stream_message(request, context):
            yield response

    @abstractmethod
    async def task_submit(
            self,
            request: TaskSubmitRequest,
            context: ServerContext | None = None,
    ) -> TaskSubmitResponse:
        """Handles TaskService.Submit."""
        raise NotImplementedError("Method not implemented.")

    @abstractmethod
    async def task_query(
            self,
            request: TaskQueryRequest,
            context: ServerContext | None = None,
    ) -> TaskQueryResponse:
        """Handles TaskService.Query."""
        raise NotImplementedError("Method not implemented.")

    @abstractmethod
    async def task_cancel(
            self,
            request: TaskCancelRequest,
            context: ServerContext | None = None,
    ) -> TaskCancelResponse:
        """Handles TaskService.Cancel."""
        raise NotImplementedError("Method not implemented.")

    @abstractmethod
    async def task_subscribe(
            self,
            request: TaskSubscribeRequest,
            context: ServerContext | None = None,
    ) -> AsyncGenerator[TaskEvent, None]:
        """Handles TaskService.Subscribe."""
        raise NotImplementedError("Method not implemented.")

    @abstractmethod
    async def health_check(
            self,
            request: HealthCheckRequest,
            context: ServerContext | None = None,
    ) -> HealthCheckResponse:
        """Handles HealthService.Check."""
        raise NotImplementedError("Method not implemented.")

    @abstractmethod
    async def health_watch(
            self,
            request: HealthCheckRequest,
            context: ServerContext | None = None,
    ) -> AsyncGenerator[HealthCheckResponse, None]:
        """Handles HealthService.Watch."""
        raise NotImplementedError("Method not implemented.")

    async def _collect_stream_request(
            self,
            requests: AsyncIterator[AduibRpcRequest],
    ) -> AduibRpcRequest:
        base_request: AduibRpcRequest | None = None
        stream_items: list[Any] = []
        async for request in requests:
            if base_request is None:
                base_request = request
                continue
            if isinstance(request, AduibRpcRequest):
                stream_items.append(request.data if request.data is not None else {})
            else:
                stream_items.append(request)
        if base_request is None:
            raise ValueError("request stream is empty")
        if stream_items:
            data = base_request.data if isinstance(base_request.data, dict) else {"_data": base_request.data}
            data.setdefault("stream_items", []).extend(stream_items)
            base_request.data = data
        return base_request
