"""Bulkhead pattern implementation for concurrency isolation.

This module provides a bulkhead pattern that limits concurrent operations
to prevent resource exhaustion. The bulkhead uses asyncio.Semaphore to
control parallelism and asyncio.Queue to manage waiting tasks.

When the semaphore is exhausted and the queue is full, BulkheadError is
raised rather than blocking indefinitely, preventing cascading failures.

Typical usage:
    bulkhead = Bulkhead(BulkheadConfig(max_concurrent=10))
    result = await bulkhead.execute(fetch_data, user_id)

Manual acquire/release:
    bulkhead = Bulkhead()
    await bulkhead.acquire()
    try:
        # Critical section with limited concurrency
        result = await operation()
    finally:
        await bulkhead.release()

Concurrency notes:
    - The semaphore limits active operations to max_concurrent.
    - The queue holds up to queue_depth waiting tasks.
    - Tasks wait up to max_wait seconds for a slot before timing out.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from aduib_rpc.exceptions import RpcException

T = TypeVar("T")
CallableResult = Callable[..., T | Awaitable[T]]


@dataclass(frozen=True, slots=True)
class BulkheadConfig:
    """Configuration for Bulkhead.

    Attributes:
        max_concurrent: Maximum number of parallel operations allowed.
        max_wait: Maximum seconds to wait for a slot before timing out.
        queue_depth: Maximum number of tasks waiting in the queue.
    """

    max_concurrent: int = 10
    max_wait: float = 30.0
    queue_depth: int = 5


@dataclass
class BulkheadError(RpcException):
    """Raised when bulkhead queue is full or wait timeout elapses."""

    code: int = 5030
    message: str = "Bulkhead queue exhausted"


class Bulkhead:
    """Bulkhead for limiting concurrent operations.

    The bulkhead pattern isolates limited resources by preventing too many
    operations from executing simultaneously. This protects both the service
    and its dependencies from overload.

    Properties:
        available_slots: Current number of available execution slots.
        active_count: Current number of executing operations.

    Example:
        bulkhead = Bulkhead(BulkheadConfig(max_concurrent=5))
        async def protected_call(url):
            return await bulkhead.execute(fetch, url)
    """

    def __init__(self, config: BulkheadConfig | None = None) -> None:
        """Initialize the bulkhead.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self._config = config or BulkheadConfig()
        self._max_concurrent = max(1, int(self._config.max_concurrent))
        self._max_wait = max(0.0, float(self._config.max_wait))
        self._queue_depth = max(0, int(self._config.queue_depth))

        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._queue: asyncio.Queue[None] = asyncio.Queue(maxsize=self._queue_depth)
        self._lock = asyncio.Lock()
        self._active: int = 0

    async def execute(
        self,
        func: CallableResult[T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute func with bulkhead protection.

        Args:
            func: Sync or async callable to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            Result of func.

        Raises:
            BulkheadError: If queue is full or wait timeout elapses.
            Exception: Any exception raised by func.
        """
        if not callable(func):
            raise TypeError("func must be callable")

        await self._acquire_slot()
        await self._increment_active()
        try:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        finally:
            await self._release_slot()
            await self._decrement_active()

    async def acquire(self) -> None:
        """Manually acquire a slot in the bulkhead.

        Raises:
            BulkheadError: If queue is full or wait timeout elapses.
        """
        await self._acquire_slot()
        await self._increment_active()

    async def try_acquire(self) -> bool:
        """Try to acquire a slot without waiting.

        Returns:
            True if a slot was acquired, False if bulkhead is full.

        Raises:
            BulkheadError: If the queue check fails unexpectedly.
        """
        # Check if semaphore has availability without blocking
        if self._semaphore.locked():
            # All slots are taken and queue would block
            return False

        # Also check queue capacity
        if self._queue.full():
            return False

        # Try to acquire immediately
        try:
            await self._acquire_slot()
            await self._increment_active()
            return True
        except BulkheadError:
            return False

    async def release(self) -> None:
        """Manually release a slot acquired with acquire()."""
        await self._release_slot()
        await self._decrement_active()

    @property
    def available_slots(self) -> int:
        """Current number of available execution slots."""
        return max(0, self._max_concurrent - self._active)

    @property
    def active_count(self) -> int:
        """Current number of executing operations."""
        return self._active

    async def _acquire_slot(self) -> None:
        """Acquire a semaphore slot with queue timeout."""
        try:
            # Try to put a placeholder in the queue first
            await asyncio.wait_for(
                self._queue.put(None),
                timeout=self._max_wait,
            )
        except asyncio.TimeoutError as exc:
            raise BulkheadError(
                code=5030,
                message=f"Bulkhead wait timeout after {self._max_wait}s",
            ) from exc

        # Now wait for the semaphore
        await self._semaphore.acquire()

    async def _release_slot(self) -> None:
        """Release a semaphore slot and queue slot."""
        self._semaphore.release()
        # Clear a slot from the queue for the next waiter
        try:
            self._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    async def _increment_active(self) -> None:
        """Increment the active operation counter."""
        async with self._lock:
            self._active += 1

    async def _decrement_active(self) -> None:
        """Decrement the active operation counter."""
        async with self._lock:
            self._active = max(0, self._active - 1)
