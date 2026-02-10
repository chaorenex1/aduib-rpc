"""Circuit breaker implementation for resilient service calls.

This module provides an asyncio-friendly circuit breaker that can guard both
synchronous and asynchronous callables. The breaker tracks consecutive failures
and opens when the failure threshold is reached, preventing additional calls
until a timeout elapses. After the timeout, it transitions to a half-open state
to probe recovery with a limited number of calls.

State transitions:
  - CLOSED -> OPEN: failures reach the failure_threshold.
  - OPEN -> HALF_OPEN: timeout_seconds elapses since the breaker opened.
  - HALF_OPEN -> CLOSED: successes reach the success_threshold.
  - HALF_OPEN -> OPEN: any failure in half-open reopens the breaker.

Typical usage with an async callable:
    breaker = CircuitBreaker("inventory")
    result = await breaker.call(fetch_inventory, item_id)

Typical usage with a synchronous callable:
    breaker = CircuitBreaker("billing")
    result = await breaker.call(blocking_charge, invoice_id)

Excluded exceptions:
    Some exceptions should not count toward failure thresholds (for example,
    validation errors). Use excluded_exceptions in CircuitBreakerConfig to
    indicate these cases. Excluded exceptions are re-raised and do not modify
    circuit counts or transitions.

Concurrency notes:
    - State transitions are guarded by an asyncio.Lock.
    - User callables run outside the lock to avoid blocking other callers.
    - The lock scope is intentionally small to keep contention low.

Timing notes:
    - timeout_seconds uses time.monotonic() so wall-clock jumps do not affect
      the state machine.
    - OPEN -> HALF_OPEN transitions are evaluated lazily on incoming calls.
"""

from __future__ import annotations

import asyncio
import enum
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from aduib_rpc.exceptions import CircuitBreakerOpenError

T = TypeVar("T")
CallableResult = Callable[..., T | Awaitable[T]]


class CircuitState(str, enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    """Configuration for CircuitBreaker.

    Attributes:
        failure_threshold: Consecutive failures required to open the breaker.
        success_threshold: Consecutive successes required to close the breaker.
        timeout_seconds: Time the breaker stays open before probing recovery.
        half_open_max_calls: Maximum in-flight calls allowed in half-open.
        excluded_exceptions: Exception types that do not count as failures.
    """

    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 30.0
    half_open_max_calls: int = 3
    excluded_exceptions: tuple[type[BaseException], ...] = ()


class CircuitBreaker:
    """Circuit breaker for sync and async callables.

    The breaker is designed for asyncio applications and uses an asyncio.Lock
    to guard state transitions. Use call() to execute operations through the
    breaker. The state property exposes the current circuit state.

    Notes:
        - Failures are counted consecutively while in CLOSED.
        - In HALF_OPEN, successes are counted toward success_threshold.
        - In-flight half-open calls are limited by half_open_max_calls.
        - Excluded exceptions do not affect breaker state.

    Args:
        name: Human-readable circuit breaker identifier.
        config: Optional CircuitBreakerConfig. Defaults are used when omitted.
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self._failure_threshold = max(1, int(self.config.failure_threshold))
        self._success_threshold = max(1, int(self.config.success_threshold))
        self._timeout_seconds = max(0.0, float(self.config.timeout_seconds))
        self._half_open_max_calls = max(1, int(self.config.half_open_max_calls))
        self._excluded_exceptions = tuple(self.config.excluded_exceptions or ())

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = 0

        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Return the current state of the circuit breaker."""

        return self._state

    async def call(self, func: CallableResult[T], *args: Any, **kwargs: Any) -> T:
        """Execute a callable through the circuit breaker.

        The breaker enforces state transitions before invoking the callable.
        When the breaker is open, CircuitBreakerOpenError is raised. Calls in
        half-open are limited by half_open_max_calls.

        Args:
            func: Callable or coroutine function to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            The result of func.

        Raises:
            CircuitBreakerOpenError: If the breaker rejects the call.
            Exception: Any exception raised by func.
            TypeError: If func is not callable.
        """

        if not callable(func):
            raise TypeError("func must be callable")

        call_state = await self._before_call()

        try:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            if self._is_excluded_exception(exc):
                await self._record_ignored(call_state)
                raise
            await self._record_failure(call_state)
            raise

        await self._record_success(call_state)
        return result

    async def reset(self) -> None:
        """Reset the breaker to the CLOSED state and clear counters."""

        async with self._lock:
            self._enter_closed_locked(self._now())

    async def _before_call(self) -> CircuitState:
        """Evaluate the current state and decide whether to allow a call.

        Returns:
            The state the call started under.

        Raises:
            CircuitBreakerOpenError: If the breaker rejects the call.
        """

        async with self._lock:
            now = self._now()
            self._maybe_transition_to_half_open_locked(now)

            if self._state == CircuitState.OPEN:
                raise self._build_open_error(now)

            if self._state == CircuitState.HALF_OPEN:
                if not self._acquire_half_open_slot_locked():
                    raise self._build_open_error(now)
                return CircuitState.HALF_OPEN

            return CircuitState.CLOSED

    async def _record_success(self, call_state: CircuitState) -> None:
        """Record a successful call and update the breaker state.

        Args:
            call_state: The state the call started under.
        """

        async with self._lock:
            if call_state == CircuitState.HALF_OPEN:
                self._release_half_open_slot_locked()
                if self._state == CircuitState.HALF_OPEN:
                    self._success_count += 1
                    if self._success_count >= self._success_threshold:
                        self._enter_closed_locked(self._now())
                    return
                if self._state == CircuitState.CLOSED:
                    self._failure_count = 0
                return

            if self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def _record_failure(self, call_state: CircuitState) -> None:
        """Record a failed call and update the breaker state.

        Args:
            call_state: The state the call started under.
        """

        async with self._lock:
            if call_state == CircuitState.HALF_OPEN:
                self._release_half_open_slot_locked()
                if self._state == CircuitState.HALF_OPEN:
                    self._enter_open_locked(self._now())
                    return
                if self._state == CircuitState.CLOSED:
                    self._failure_count += 1
                    if self._failure_count >= self._failure_threshold:
                        self._enter_open_locked(self._now())
                return

            if self._state != CircuitState.CLOSED:
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._enter_open_locked(self._now())

    async def _record_ignored(self, call_state: CircuitState) -> None:
        """Record an excluded exception without affecting breaker counts.

        Args:
            call_state: The state the call started under.
        """

        async with self._lock:
            if call_state == CircuitState.HALF_OPEN:
                self._release_half_open_slot_locked()

    def _now(self) -> float:
        """Return a monotonic timestamp."""

        return time.monotonic()

    def _open_timeout_elapsed(self, now: float) -> bool:
        """Return True if the open timeout has elapsed."""

        if self._opened_at is None:
            return False
        return (now - self._opened_at) >= self._timeout_seconds

    def _maybe_transition_to_half_open_locked(self, now: float) -> None:
        """Transition from OPEN to HALF_OPEN if the timeout has elapsed."""

        if self._state != CircuitState.OPEN:
            return
        if self._timeout_seconds <= 0 or self._open_timeout_elapsed(now):
            self._enter_half_open_locked(now)

    def _enter_open_locked(self, now: float) -> None:
        """Move the breaker into the OPEN state."""

        if self._state != CircuitState.OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = now
        self._failure_count = self._failure_threshold
        self._success_count = 0
        self._half_open_in_flight = 0

    def _enter_half_open_locked(self, now: float) -> None:
        """Move the breaker into the HALF_OPEN state."""

        self._state = CircuitState.HALF_OPEN
        self._opened_at = None
        self._failure_count = 0
        self._success_count = 0
        self._half_open_in_flight = 0

    def _enter_closed_locked(self, now: float) -> None:
        """Move the breaker into the CLOSED state."""

        self._state = CircuitState.CLOSED
        self._opened_at = None
        self._failure_count = 0
        self._success_count = 0
        self._half_open_in_flight = 0

    def _acquire_half_open_slot_locked(self) -> bool:
        """Attempt to reserve a half-open call slot."""

        if self._half_open_in_flight >= self._half_open_max_calls:
            return False
        self._half_open_in_flight += 1
        return True

    def _release_half_open_slot_locked(self) -> None:
        """Release a previously reserved half-open call slot."""

        if self._half_open_in_flight > 0:
            self._half_open_in_flight -= 1

    def _is_excluded_exception(self, exc: Exception) -> bool:
        """Return True if the exception should be ignored for failure counts."""

        if not self._excluded_exceptions:
            return False
        return isinstance(exc, self._excluded_exceptions)

    def _build_open_error(self, now: float) -> CircuitBreakerOpenError:
        """Create a CircuitBreakerOpenError with retry metadata."""

        retry_after_ms = 0
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            remaining = max(0.0, self._timeout_seconds - (now - self._opened_at))
            retry_after_ms = int(remaining * 1000.0)

        data: dict[str, Any] = {
            "name": self.name,
            "state": self._state.value,
            "retry_after_ms": retry_after_ms,
        }
        return CircuitBreakerOpenError(message="Circuit breaker open", data=data)
