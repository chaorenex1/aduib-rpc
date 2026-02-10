"""Server context and interceptor definitions.

This module provides:
1. ServerContext - per-request context for server interceptors
2. ServerInterceptor - abstract base class for request interception
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from aduib_rpc.protocol.v2 import RpcError, ERROR_CODE_NAMES, ResponseStatus, ErrorCode, AduibRpcRequest, \
    AduibRpcResponse

State = dict[str, Any]


class ServerContext(BaseModel):
    """Context for the server, including configuration and state information."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    state: State = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)


class InterceptorChain:
    """Interceptor chain using asynccontextmanager-based onion model."""

    def __init__(
        self,
        interceptors: list[ServerInterceptor],
    ) -> None:
        self.interceptors = sorted(
            interceptors or [],
            key=lambda item: item.order() if callable(getattr(item, "order", None)) else 0,
        )

    async def execute(
        self,
        request: AduibRpcRequest,
        server_context: ServerContext,
        handler: Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]],
        *,
        is_stream: bool = False,
    ) -> AsyncIterator[AduibRpcResponse]:
        """Execute the interceptor chain.

        Args:
            request: RPC request.
            server_context: Server context.
            handler: Final handler yielding response(s).

        Yields:
            AduibRpcResponse instances.
        """
        ctx = InterceptContext(
            request=request,
            server_context=server_context,
            handler=handler,
            chain=self,
            is_stream=is_stream,
            index=0,
        )
        ctx.store("handler_wrappers", [])

        async with self._nest(ctx, 0):
            if ctx.aborted:
                response = self._abort_response(ctx)
                ctx.response = response
                yield response
                return

            try:
                wrapped = self._apply_wrappers(ctx, handler)
                async for response in wrapped(ctx):
                    ctx.response = response
                    yield response
            except Exception as exc:
                ctx.error = exc
                raise

    @asynccontextmanager
    async def _nest(self, ctx: InterceptContext, index: int) -> AsyncIterator[None]:
        """Recursively nest interceptors."""
        if index >= len(self.interceptors) or ctx.aborted:
            yield
            return

        async with self.interceptors[index].intercept(ctx):
            if not ctx.aborted:
                async with self._nest(ctx, index + 1):
                    yield
            else:
                yield

    def _apply_wrappers(
        self,
        ctx: InterceptContext,
        handler: Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]],
    ) -> Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]]:
        wrappers = ctx.load("handler_wrappers", []) or []
        wrapped = handler
        for wrapper in reversed(wrappers):
            wrapped = wrapper(wrapped)
        return wrapped

    def _abort_response(self, ctx: InterceptContext) -> AduibRpcResponse:
        """Construct short-circuit error response."""
        error = ctx.abort_error
        if error is None:
            code = int(ErrorCode.INTERNAL_ERROR)
            error = RpcError(
                code=code,
                name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                message="Request aborted",
            )
        request_id = ctx.request.id
        if request_id is None:
            request_id = ctx.request.id_str
        return AduibRpcResponse(
            id=request_id,
            status=ResponseStatus.ERROR,
            error=error,
        )


@dataclass
class InterceptContext:
    """Shared request context for interceptor chain execution."""

    request: AduibRpcRequest
    server_context: ServerContext
    handler: Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]]
    chain: InterceptorChain
    is_stream: bool = False
    index: int = 0

    response: AduibRpcResponse | None = None
    error: Exception | None = None

    _aborted: bool = False
    _abort_error: RpcError | None = None
    _local: dict[str, Any] = field(default_factory=dict)

    @property
    def aborted(self) -> bool:
        return self._aborted

    @property
    def abort_error(self) -> RpcError | None:
        return self._abort_error

    def abort(self, error: RpcError) -> None:
        """Abort request handling and return an error response."""
        self._aborted = True
        self._abort_error = error

    def store(self, key: str, value: Any) -> None:
        """Store interceptor-local state."""
        self._local[key] = value

    def load(self, key: str, default: Any = None) -> Any:
        """Load interceptor-local state."""
        return self._local.get(key, default)


class ServerInterceptor(ABC):
    """Base class for server interceptors.

    Implementations should use @asynccontextmanager to implement onion model:
      - Code before yield: pre-processing
      - Code after yield: post-processing
      - Call ctx.abort() before yield to short-circuit
    """
    @abstractmethod
    def order(self) -> int:
        """Order of the interceptor in the chain.

        Lower values indicate higher precedence.
        """
        return 0

    @abstractmethod
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        """Intercept a request.

        Args:
            ctx: Interceptor context containing request, response, and error info.

        Yields:
            None: yield separates pre- and post-processing logic.
        """
