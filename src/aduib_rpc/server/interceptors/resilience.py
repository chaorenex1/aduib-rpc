"""Server-side resilience interceptor for inbound request processing.

This module provides server-side resilience patterns for handling incoming requests:
- Rate limiting per tenant/client
- Circuit breaking for downstream dependencies
- Bulkhead pattern for resource isolation
- Fallback handlers for degraded operations

Phase P0-2: Server-side resilience handler 入站执行
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aduib_rpc.protocol.v2 import RpcError
from aduib_rpc.protocol.v2.errors import ErrorCode, ERROR_CODE_NAMES
from aduib_rpc.resilience.bulkhead import (
    Bulkhead,
    BulkheadConfig,
    BulkheadError,
)
from aduib_rpc.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from aduib_rpc.resilience.fallback import (
    FallbackExecutor,
    FallbackPolicy,
)
from aduib_rpc.resilience.rate_limiter import (
    RateLimiter,
    RateLimiterBase,
    RateLimiterConfig,
)
from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse

logger = logging.getLogger(__name__)


@dataclass
class ServerResilienceConfig:
    """Configuration for server-side resilience.

    Attributes:
        rate_limiter: Rate limiter configuration (per-tenant by default).
        circuit_breaker: Circuit breaker for downstream calls.
        bulkhead: Bulkhead for concurrent request limiting.
        fallback: Fallback policy for degraded operations.
        enabled: Whether resilience is enabled.
        tenant_isolated: Whether rate limiting is per-tenant.
    """

    rate_limiter: RateLimiterConfig | None = None
    circuit_breaker: CircuitBreakerConfig | None = None
    bulkhead: BulkheadConfig | None = None
    fallback: FallbackPolicy | None = None
    enabled: bool = True
    tenant_isolated: bool = True


class ServerResilienceInterceptor(ServerInterceptor):
    """Server-side interceptor that applies resilience patterns to inbound requests.

    This interceptor processes requests BEFORE they reach the handler:
    1. Checks rate limits (may reject immediately)
    2. Acquires bulkhead semaphore (may queue or reject)
    3. Stores resilience context for downstream use

    The interceptor does NOT execute the request - it only sets up
    resilience guards. The actual handler execution is wrapped by
    ResilienceHandler which applies circuit breaking and fallback.
    """

    def order(self) -> int:
        return 5

    def __init__(
        self,
        config: ServerResilienceConfig | None = None,
        *,
        rate_limiter: RateLimiterBase | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        bulkhead: Bulkhead | None = None,
        fallback_executor: FallbackExecutor | None = None,
    ) -> None:
        """Initialize the server resilience interceptor.

        Args:
            config: Resilience configuration.
            rate_limiter: Pre-configured rate limiter.
            circuit_breaker: Pre-configured circuit breaker.
            bulkhead: Pre-configured bulkhead.
            fallback_executor: Pre-configured fallback executor.
        """
        self.config = config or ServerResilienceConfig()
        self._explicit_rate_limiter = rate_limiter is not None
        self._explicit_circuit_breaker = circuit_breaker is not None
        self._explicit_bulkhead = bulkhead is not None
        self._explicit_fallback_executor = fallback_executor is not None

        # Per-tenant rate limiters (if tenant_isolated)
        self._rate_limiters: dict[str, RateLimiterBase] = {}
        self._circuit_breaker = circuit_breaker
        self._bulkhead = bulkhead
        self._fallback_executor = fallback_executor
        self._lock = asyncio.Lock()

        if rate_limiter:
            self._rate_limiters["default"] = rate_limiter

        self.refresh_from_config()

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        if not self.config.enabled:
            yield
            return

        tenant_id = ctx.request.metadata.tenant_id

        rate_limiter = await self._get_rate_limiter(tenant_id)
        if rate_limiter:
            allowed = await rate_limiter.acquire()
            if not allowed:
                code = int(ErrorCode.RATE_LIMITED)
                ctx.abort(
                    RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message=f"Rate limit exceeded for tenant: {tenant_id}",
                    )
                )
                yield
                return

        if self._bulkhead:
            try:
                acquired = await self._bulkhead.try_acquire()
            except AttributeError:
                acquired = None
            except BulkheadError as exc:
                code = int(ErrorCode.RESOURCE_EXHAUSTED)
                ctx.abort(
                    RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message=str(exc),
                    )
                )
                yield
                return
            try:
                if acquired is None:
                    await self._bulkhead.acquire()
                    acquired = True
            except BulkheadError as exc:
                code = int(ErrorCode.RESOURCE_EXHAUSTED)
                ctx.abort(
                    RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message=str(exc),
                    )
                )
                yield
                return

            if not acquired:
                code = int(ErrorCode.RESOURCE_EXHAUSTED)
                ctx.abort(
                    RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message="Bulkhead capacity exceeded",
                    )
                )
                yield
                return

            ctx.store("bulkhead_acquired", True)
            ctx.server_context.state["resilience_bulkhead_permit"] = True

        ctx.server_context.state["resilience_enabled"] = True
        ctx.server_context.state["resilience_tenant"] = tenant_id
        wrappers = ctx.load("handler_wrappers", []) or []

        def _wrap_handler(
            handler: Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]],
        ) -> Callable[[InterceptContext], AsyncIterator[AduibRpcResponse]]:
            async def _wrapped(inner_ctx: InterceptContext) -> AsyncIterator[AduibRpcResponse]:
                if inner_ctx.is_stream:
                    async for response in handler(inner_ctx):
                        yield response
                    return

                async def _invoke_downstream(
                    _request: AduibRpcRequest, _context: ServerContext
                ) -> AduibRpcResponse | None:
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

                wrapped = ResilienceHandler(
                    _invoke_downstream,
                    circuit_breaker=self._circuit_breaker,
                    fallback_executor=self._fallback_executor,
                    interceptor=self,
                )
                response = await wrapped.handle(inner_ctx.request, inner_ctx.server_context)
                if response is not None:
                    yield response

            return _wrapped

        wrappers.append(_wrap_handler)
        ctx.store("handler_wrappers", wrappers)

        try:
            yield
        finally:
            if ctx.load("bulkhead_acquired") and self._bulkhead:
                try:
                    await self._bulkhead.release()
                    ctx.server_context.state["resilience_bulkhead_permit"] = False
                except Exception:
                    logger.debug("Failed to release bulkhead permit", exc_info=True)

    async def _get_rate_limiter(self, tenant_id: str) -> RateLimiterBase | None:
        """Get or create rate limiter for a tenant."""
        if not self.config.rate_limiter:
            return None

        # If not tenant-isolated, use default
        if not self.config.tenant_isolated:
            return self._rate_limiters.get("default")

        # Create per-tenant rate limiter if needed
        if tenant_id not in self._rate_limiters:
            async with self._lock:
                if tenant_id not in self._rate_limiters:
                    self._rate_limiters[tenant_id] = self._build_rate_limiter(self.config.rate_limiter)

        return self._rate_limiters.get(tenant_id)

    async def get_rate_limiter_stats(self, tenant_id: str = "default") -> dict[str, Any] | None:
        """Get rate limiter statistics for a tenant."""
        rate_limiter = self._rate_limiters.get(tenant_id) or self._rate_limiters.get("default")
        if rate_limiter:
            return {"available_tokens": await rate_limiter.get_available_tokens()}
        return None

    def refresh_from_config(self) -> None:
        """Rebuild internal guards from the current config."""
        if not self._explicit_rate_limiter:
            self._rate_limiters.clear()
            if self.config.rate_limiter:
                self._rate_limiters["default"] = self._build_rate_limiter(self.config.rate_limiter)

        if not self._explicit_circuit_breaker:
            if self.config.circuit_breaker:
                self._circuit_breaker = CircuitBreaker("server", self.config.circuit_breaker)
            else:
                self._circuit_breaker = None

        if not self._explicit_bulkhead:
            if self.config.bulkhead:
                self._bulkhead = Bulkhead(self.config.bulkhead)
            else:
                self._bulkhead = None

        if not self._explicit_fallback_executor:
            if self.config.fallback:
                self._fallback_executor = FallbackExecutor(self.config.fallback)
            else:
                self._fallback_executor = None

    def _build_rate_limiter(self, config: RateLimiterConfig) -> RateLimiterBase:
        return RateLimiter(config)


class ResilienceHandler:
    """Wrapper that applies resilience patterns to handler execution.

    This wraps the actual service handler to apply:
    1. Circuit breaking for downstream calls
    2. Fallback on failure
    3. Bulkhead permit release

    Usage:
        handler = ResilienceHandler(
            actual_handler,
            circuit_breaker=cb,
            fallback_executor=fallback,
        )
        result = await handler.handle(request, context)
    """

    def __init__(
        self,
        handler: Callable[[AduibRpcRequest, ServerContext], Awaitable[Any]],
        *,
        circuit_breaker: CircuitBreaker | None = None,
        fallback_executor: FallbackExecutor | None = None,
        interceptor: ServerResilienceInterceptor | None = None,
    ) -> None:
        """Initialize the resilience handler wrapper.

        Args:
            handler: The actual service handler.
            circuit_breaker: Circuit breaker for downstream calls.
            fallback_executor: Fallback executor for degraded operations.
            interceptor: Reference to interceptor for bulkhead release.
        """
        self._handler = handler
        self._circuit_breaker = circuit_breaker
        self._fallback_executor = fallback_executor
        self._interceptor = interceptor

    async def handle(
        self,
        request: AduibRpcRequest,
        context: ServerContext,
    ) -> Any:
        """Execute the handler with resilience protection.

        Args:
            request: The RPC request.
            context: The server context.

        Returns:
            The handler result or fallback result.

        Raises:
            CircuitBreakerOpenError: If circuit is open and no fallback.
            Exception: Propagates handler exceptions if no fallback.
        """
        try:
            # Use circuit breaker call() if available
            if self._circuit_breaker:
                result = await self._circuit_breaker.call(self._handler, request, context)
            else:
                result = await self._handler(request, context)
            return result

        except Exception as e:
            # Try fallback
            if self._fallback_executor:
                logger.info(f"Handler failed, executing fallback: {e}")
                return await self._fallback_executor.execute(self._handler, request, context)

            # Re-raise if no fallback
            raise

        finally:
            # Bulkhead release is handled by the interceptor context.
            pass

    def __call__(self, request: AduibRpcRequest, context: ServerContext) -> Awaitable[Any]:
        """Allow the handler to be called directly."""
        return self.handle(request, context)


def with_resilience(
    circuit_breaker: CircuitBreaker | None = None,
    fallback_executor: FallbackExecutor | None = None,
    interceptor: ServerResilienceInterceptor | None = None,
) -> Callable[
    [Callable[[AduibRpcRequest, ServerContext], Awaitable[Any]]],
    ResilienceHandler,
]:
    """Decorator that wraps a handler with resilience protection.

    Args:
        circuit_breaker: Circuit breaker for downstream calls.
        fallback_executor: Fallback executor for degraded operations.
        interceptor: Reference to interceptor for bulkhead release.

    Returns:
        A decorator function.

    Usage:
        @with_resilience(circuit_breaker=cb, fallback_executor=fallback)
        async def my_handler(request, context):
            return {"result": "success"}
    """

    def decorator(handler: Callable[[AduibRpcRequest, ServerContext], Awaitable[Any]]) -> ResilienceHandler:
        return ResilienceHandler(
            handler,
            circuit_breaker=circuit_breaker,
            fallback_executor=fallback_executor,
            interceptor=interceptor,
        )

    return decorator
