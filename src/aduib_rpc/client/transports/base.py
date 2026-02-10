from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from aduib_rpc.client.midwares import ClientContext
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse
from aduib_rpc.server.tasks import TaskSubscribeRequest, TaskCancelRequest, TaskQueryRequest, TaskSubmitRequest
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
        raise NotImplementedError

    @abstractmethod
    async def call(
            self,
            request: AduibRpcRequest,
            *,
            context: ClientContext,
    ) -> AduibRpcResponse:
        """AduibRpcService.Call."""
        raise NotImplementedError

    @abstractmethod
    async def call_server_stream(
            self,
            request: AduibRpcRequest,
            *,
            context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        """AduibRpcService.CallServerStream."""
        raise NotImplementedError

    @abstractmethod
    async def call_client_stream(
            self,
            requests: AsyncIterator[AduibRpcRequest],
            *,
            context: ClientContext,
    ) -> AduibRpcResponse:
        """AduibRpcService.CallClientStream."""
        raise NotImplementedError

    @abstractmethod
    async def call_bidirectional(
            self,
            requests: AsyncIterator[AduibRpcRequest],
            *,
            context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        """AduibRpcService.CallBidirectional."""
        raise NotImplementedError

    @abstractmethod
    async def task_submit(self, request: TaskSubmitRequest,
                          *, context: ClientContext) -> Any:
        """TaskService.Submit."""
        raise NotImplementedError

    @abstractmethod
    async def task_query(self, request: TaskQueryRequest,
                         *, context: ClientContext) -> Any:
        """TaskService.Query."""
        raise NotImplementedError

    @abstractmethod
    async def task_cancel(self, request: TaskCancelRequest,
                          *, context: ClientContext) -> Any:
        """TaskService.Cancel."""
        raise NotImplementedError

    @abstractmethod
    async def task_subscribe(
            self,
            request: TaskSubscribeRequest,
            *,
            context: ClientContext,
    ) -> AsyncGenerator[Any, None]:
        """TaskService.Subscribe."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self, request: HealthCheckRequest, *, context: ClientContext) -> HealthCheckResponse:
        """HealthService.Check."""
        raise NotImplementedError

    @abstractmethod
    async def health_watch(
            self,
            request: HealthCheckRequest,
            *,
            context: ClientContext,
    ) -> AsyncGenerator[HealthCheckResponse, None]:
        """HealthService.Watch."""
        raise NotImplementedError
