"""QoS interceptor for server-side request processing."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Callable

from aduib_rpc.server.context import InterceptContext, ServerInterceptor
from aduib_rpc.server.qos.handler import QosHandler
from aduib_rpc.types import AduibRpcResponse


class QosInterceptor(ServerInterceptor):
    """Server interceptor that enforces QoS for unary and streaming requests."""

    def order(self) -> int:
        return 6

    def __init__(
        self,
        qos_handler: QosHandler | None = None
    ) -> None:
        self._qos_handler = qos_handler

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        if self._qos_handler is None:
            self._qos_handler = QosHandler()
        wrappers = ctx.load("handler_wrappers", []) or []

        def _wrap_handler(
            handler: Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]],
        ) -> Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]]:
            async def _wrapped(inner_ctx: InterceptContext) -> AsyncIterator[AduibRpcResponse]:
                if inner_ctx.is_stream:
                    async for response in self._qos_handler.handle_stream(
                        inner_ctx.request, handler, inner_ctx
                    ):
                        yield response
                    return

                async def _invoke_once() -> AduibRpcResponse | None:
                    iterator = handler(inner_ctx)
                    response: AduibRpcResponse | None = None
                    async for item in iterator:
                        response = item
                        break
                    if response is None:
                        return None
                    async for _ in iterator:
                        pass
                    return response

                response = await self._qos_handler.handle_request(inner_ctx.request, _invoke_once)
                if response is not None:
                    yield response

            return _wrapped

        wrappers.append(_wrap_handler)
        ctx.store("handler_wrappers", wrappers)
        yield
