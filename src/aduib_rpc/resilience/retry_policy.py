"""Enhanced retry policy implementation for resilient calls."""

from __future__ import annotations

import asyncio
import enum
import inspect
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from aduib_rpc.exceptions import RpcException

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState

T = TypeVar("T")
CallableResult = Callable[..., T | Awaitable[T]]


class RetryStrategy(str, enum.Enum):
    """Retry delay calculation strategies."""

    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


class RetryCondition(str, enum.Enum):
    """Retry trigger conditions."""

    ALWAYS = "always"
    ON_ERROR = "on_error"
    ON_SPECIFIC_CODES = "on_specific_codes"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Configuration for retrying failed calls."""

    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    initial_delay_ms: int = 100
    max_delay_ms: int = 10000
    backoff_multiplier: float = 2.0
    jitter: float = 0.1
    retryable_codes: set[int] | None = None
    respect_circuit_breaker: bool = True


class RetryExecutor:
    """Execute sync or async callables with a retry policy."""

    def __init__(self, policy: RetryPolicy) -> None:
        self._policy = policy
        self._max_attempts = max(1, int(policy.max_attempts))
        self._strategy = policy.strategy
        self._initial_delay_ms = max(0, int(policy.initial_delay_ms))
        self._max_delay_ms = max(self._initial_delay_ms, int(policy.max_delay_ms))
        self._backoff_multiplier = max(1.0, float(policy.backoff_multiplier))
        self._jitter = max(0.0, min(1.0, float(policy.jitter)))
        self._retryable_codes = set(policy.retryable_codes) if policy.retryable_codes is not None else None
        self._respect_circuit_breaker = bool(policy.respect_circuit_breaker)
        self._retry_condition = RetryCondition.ON_SPECIFIC_CODES if self._retryable_codes is not None else RetryCondition.ON_ERROR

    async def execute(
        self,
        func: CallableResult[T],
        *args: Any,
        circuit_breaker: CircuitBreaker | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute func with retries according to the policy."""

        if not callable(func):
            raise TypeError("func must be callable")

        last_exc: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._invoke(func, *args, circuit_breaker=circuit_breaker, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not self._should_retry(attempt, exc):
                    raise
                delay_s = await self._compute_delay(attempt)
                if delay_s > 0:
                    await asyncio.sleep(delay_s)

        assert last_exc is not None
        raise last_exc

    def _should_retry(self, attempt: int, error: Exception) -> bool:
        if attempt >= self._max_attempts:
            return False
        return self._is_retryable_error(error)

    async def _compute_delay(self, attempt: int) -> float:
        base_ms = float(self._initial_delay_ms)
        if self._strategy == RetryStrategy.EXPONENTIAL:
            exponent = max(0, attempt - 1)
            base_ms = self._initial_delay_ms * (self._backoff_multiplier**exponent)
        elif self._strategy == RetryStrategy.LINEAR:
            base_ms = self._initial_delay_ms * attempt
        elif self._strategy == RetryStrategy.FIXED:
            base_ms = float(self._initial_delay_ms)

        base_ms = min(float(self._max_delay_ms), float(base_ms))
        if self._jitter > 0 and base_ms > 0:
            delta = (random.random() * 2 - 1) * (self._jitter * base_ms)
            base_ms = max(0.0, base_ms + delta)

        return base_ms / 1000.0

    def _is_retryable_error(self, error: Exception) -> bool:
        if isinstance(error, CircuitBreakerOpenError):
            return False

        if self._retry_condition == RetryCondition.ALWAYS:
            return True

        if self._retry_condition == RetryCondition.ON_SPECIFIC_CODES:
            if isinstance(error, RpcException) and self._retryable_codes is not None:
                return error.code in self._retryable_codes
            return False

        return True

    async def _invoke(
        self,
        func: CallableResult[T],
        *args: Any,
        circuit_breaker: CircuitBreaker | None,
        **kwargs: Any,
    ) -> T:
        if circuit_breaker is not None and self._respect_circuit_breaker:
            return await circuit_breaker.call(func, *args, **kwargs)

        result = func(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
