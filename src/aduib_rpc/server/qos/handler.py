"""QoS handler for timeout execution and idempotency caching.

Per spec v2 section 2.3:
- timeout_ms: Hard timeout for request execution
- idempotency_key: Deduplicate identical requests

Implementation:
- Uses asyncio.timeout() for hard timeout enforcement
- In-memory LRU cache for idempotency (Redis can be added later)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Awaitable, Callable

from aduib_rpc.protocol.v2.errors import ErrorCode
from aduib_rpc.protocol.v2.qos import QosConfig
from aduib_rpc.protocol.v2.types import AduibRpcRequest, AduibRpcResponse, RpcError
from aduib_rpc.resilience.retry_policy import RetryExecutor, RetryPolicy

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 30000  # 30 seconds
MAX_TIMEOUT_MS = 300000     # 5 minutes


class IdempotencyCache:
    """In-memory LRU cache for idempotent request responses.

    For production, consider using Redis for distributed caching.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """Initialize the cache.

        Args:
            max_size: Maximum number of cached responses.
            ttl_seconds: Time-to-live for cache entries in seconds.
        """
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        # Singleflight: ensure at most one coroutine computes a given key at once.
        self._inflight_locks: dict[str, asyncio.Lock] = {}
        self._inflight_lock: asyncio.Lock = asyncio.Lock()

    def get(self, key: str) -> AduibRpcResponse | None:
        """Get cached response if exists and not expired.

        Args:
            key: The idempotency key.

        Returns:
            Cached response or None if not found/expired.
        """
        entry = self._cache.get(key)
        if entry is None:
            return None

        if time.time() - entry.timestamp > self._ttl_seconds:
            # Expired
            del self._cache[key]
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return entry.response

    def set(self, key: str, response: AduibRpcResponse) -> None:
        """Cache a response.

        Args:
            key: The idempotency key.
            response: The response to cache.
        """
        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._cache.popitem(last=False)

        self._cache[key] = _CacheEntry(response=response, timestamp=time.time())

    async def get_or_compute(
        self,
        key: str,
        factory: Callable[[], Awaitable[AduibRpcResponse]],
    ) -> AduibRpcResponse:
        # 1. 先检查缓存
        cached = self.get(key)
        if cached is not None:
            return cached

        # 2. 获取 per-key 锁
        async with self._inflight_lock:
            if key not in self._inflight_locks:
                self._inflight_locks[key] = asyncio.Lock()
            key_lock = self._inflight_locks[key]

        # 3. 在锁内执行
        async with key_lock:
            # Double-check
            cached = self.get(key)
            if cached is not None:
                return cached

            result = await factory()
            # Keep the previous caching behavior: only cache non-None responses.
            if result is not None:
                self.set(key, result)
            return result

    def has(self, key: str) -> bool:
        """Check if key exists (including expired entries).

        Args:
            key: The idempotency key.

        Returns:
            True if key exists in cache.
        """
        return key in self._cache

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()


class _CacheEntry:
    """A cache entry with timestamp."""

    def __init__(self, response: AduibRpcResponse, timestamp: float):
        self.response = response
        self.timestamp = timestamp


# Global default cache instance
_default_cache = IdempotencyCache()


def get_default_cache() -> IdempotencyCache:
    """Get the global default idempotency cache."""
    return _default_cache


class QosHandler:
    """Handler that enforces QoS policies on requests.

    Features:
    - Hard timeout using asyncio.timeout()
    - Idempotency caching using idempotency_key
    - Concurrent request detection for same idempotency key
    """

    def __init__(
        self,
        cache: IdempotencyCache | None = None,
        default_timeout_ms: int | None = None,
    ):
        """Initialize the QoS handler.

        Args:
            cache: Idempotency cache instance. Uses default if None.
            default_timeout_ms: Default timeout if not specified in request.
        """
        self._cache = cache or _default_cache
        # Ensure there is a default timeout value.
        self._default_timeout_ms = (
            default_timeout_ms if default_timeout_ms is not None else DEFAULT_TIMEOUT_MS
        )

    async def handle_request(
        self,
        request: AduibRpcRequest,
        handler: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> AduibRpcResponse:
        """Handle a request with QoS enforcement.

        Args:
            request: The RPC request.
            handler: The actual request handler.
            *args: Additional positional args for handler.
            **kwargs: Additional keyword args for handler.

        Returns:
            The response from handler or cache.

        Raises:
            RpcTimeoutError: If timeout is exceeded.
        """
        qos = self._extract_qos(request)
        idempotency_key = qos.idempotency_key if qos else None
        # Use request timeout if specified, otherwise use default
        timeout_ms = self._resolve_timeout_ms(qos)
        if timeout_ms is None:
            timeout_ms = self._default_timeout_ms

        async def _execute_once() -> AduibRpcResponse:
            if timeout_ms is not None:
                return await self._execute_with_timeout(
                    timeout_ms / 1000,
                    handler,
                    *args,
                    **kwargs,
                )
            return await handler(*args, **kwargs)

        # Use singleflight idempotency caching to avoid TOCTOU races.
        if idempotency_key:
            async def _factory() -> AduibRpcResponse:
                return await self._execute_with_retry(_execute_once, qos)

            cached_or_fresh = await self._cache.get_or_compute(idempotency_key, _factory)
            logger.debug("Idempotency singleflight served key: %s", idempotency_key)
            return cached_or_fresh

        return await self._execute_with_retry(_execute_once, qos)

    async def handle_stream(
        self,
        request: AduibRpcRequest,
        handler: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ):
        """Handle a streaming request with QoS timeout enforcement."""
        qos = self._extract_qos(request)
        if qos:
            if qos.retry is not None:
                logger.debug("Streaming ignores retry policy for request_id=%s", request.id)
            if qos.idempotency_key:
                logger.debug("Streaming ignores idempotency_key for request_id=%s", request.id)

        timeout_ms = self._resolve_timeout_ms(qos)
        if timeout_ms is None:
            async for item in handler(*args, **kwargs):
                yield item
            return

        try:
            async with asyncio.timeout(timeout_ms / 1000):
                async for item in handler(*args, **kwargs):
                    yield item
        except TimeoutError:
            from aduib_rpc.exceptions import RpcTimeoutError

            raise RpcTimeoutError(
                code=ErrorCode.RPC_TIMEOUT,
                message=f"Request exceeded timeout of {timeout_ms / 1000:.3f}s",
            )

    async def _execute_with_retry(
        self,
        handler: Callable[[], Any],
        qos: QosConfig | None,
    ) -> AduibRpcResponse:
        if qos is None or qos.retry is None:
            return await handler()

        retry = qos.retry
        policy = RetryPolicy(
            max_attempts=retry.max_attempts,
            initial_delay_ms=retry.initial_delay_ms,
            max_delay_ms=retry.max_delay_ms,
            backoff_multiplier=retry.backoff_multiplier,
            retryable_codes=set(retry.retryable_codes) if retry.retryable_codes else None,
        )
        executor = RetryExecutor(policy)
        return await executor.execute(handler)

    async def _execute_with_timeout(
        self,
        timeout_seconds: float,
        handler: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> AduibRpcResponse:
        """Execute handler with timeout.

        Args:
            timeout_seconds: Timeout in seconds.
            handler: The handler to execute.
            *args: Handler args.
            **kwargs: Handler kwargs.

        Returns:
            The handler response.

        Raises:
            RpcTimeoutError: If timeout is exceeded.
        """
        try:
            async with asyncio.timeout(timeout_seconds):
                return await handler(*args, **kwargs)
        except TimeoutError:
            from aduib_rpc.exceptions import RpcTimeoutError

            logger.warning("Request exceeded timeout of %.3fs", timeout_seconds)
            raise RpcTimeoutError(
                code=ErrorCode.RPC_TIMEOUT,
                message=f"Request exceeded timeout of {timeout_seconds:.3f}s",
            )

    def _extract_qos(self, request: AduibRpcRequest) -> QosConfig | None:
        """Extract QoS config from request.

        Args:
            request: The RPC request.

        Returns:
            QosConfig if present, None otherwise.
        """
        if request.qos is None:
            return None

        if isinstance(request.qos, QosConfig):
            return request.qos

        if isinstance(request.qos, dict):
            try:
                return QosConfig.model_validate(request.qos)
            except Exception:
                logger.warning("Invalid QoS config in request: %s", request.qos)
                return None

        return None

    def _resolve_timeout_ms(self, qos: QosConfig | None) -> int | None:
        if qos and qos.timeout_ms is not None:
            return min(int(qos.timeout_ms), MAX_TIMEOUT_MS)
        return None


async def with_qos(
    request: AduibRpcRequest,
    handler: Callable[..., Any],
    *args: Any,
    cache: IdempotencyCache | None = None,
    default_timeout_ms: int | None = None,
    **kwargs: Any,
) -> AduibRpcResponse:
    """Convenience function to handle a request with QoS enforcement.

    Args:
        request: The RPC request.
        handler: The handler function.
        *args: Handler args.
        cache: Optional idempotency cache.
        default_timeout_ms: Default timeout if not in request.
        **kwargs: Handler kwargs.

    Returns:
        The response from handler or cache.
    """
    qos_handler = QosHandler(cache=cache, default_timeout_ms=default_timeout_ms)
    return await qos_handler.handle_request(request, handler, *args, **kwargs)


def with_timeout(
    timeout_ms: int | None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to add timeout to an async function.

    Args:
        timeout_ms: Timeout in milliseconds. None means no timeout.

    Returns:
        Decorator function.

    Example:
        @with_timeout(5000)  # 5 second timeout
        async def my_handler(request):
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if timeout_ms is None:
                return await func(*args, **kwargs)

            try:
                async with asyncio.timeout(timeout_ms / 1000):
                    return await func(*args, **kwargs)
            except TimeoutError:
                from aduib_rpc.exceptions import RpcTimeoutError

                raise RpcTimeoutError(
                    code=ErrorCode.RPC_TIMEOUT,
                    message=f"Request exceeded timeout of {timeout_ms}ms",
                )

        return wrapper

    return decorator

