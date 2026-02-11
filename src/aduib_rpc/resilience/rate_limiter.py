"""Asynchronous rate limiter implementations.

This module provides a single RateLimiter class that can enforce different
algorithms with the same public API. The limiter is designed for asyncio-based
code and uses asyncio primitives for coordination.

Supported algorithms:
  - Token bucket: allows bursts up to the bucket capacity while refilling at a
    steady rate.
  - Sliding window: tracks every request within a time window for precise
    limits.
  - Fixed window: uses a counter that resets every window; fastest but less
    precise.

Example:
    limiter = RateLimiter(RateLimiterConfig(rate=50.0, burst=100))
    if await limiter.acquire():
        await call_service()
    else:
        await limiter.acquire_or_wait()
        await call_service()
"""

from __future__ import annotations

import asyncio
import enum
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque
from abc import ABC, abstractmethod

from aduib_rpc.exceptions import RateLimitedError


class RateLimitAlgorithm(str, enum.Enum):
    """Supported rate limiting algorithms."""

    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


@dataclass(frozen=True, slots=True)
class RateLimiterConfig:
    """Configuration for RateLimiter.

    Attributes:
        algorithm: The rate limiting algorithm to use.
        rate: Tokens generated per second (or requests per second).
        burst: Maximum bucket capacity for token bucket.
        wait_timeout_ms: Maximum time to wait in acquire_or_wait.
    """

    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    rate: float = 100.0
    burst: int = 150
    wait_timeout_ms: int = 1000


class RateLimiterBase(ABC):
    """Abstract rate limiter interface."""

    @abstractmethod
    async def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting."""

    @abstractmethod
    async def acquire_or_wait(self, tokens: int = 1) -> None:
        """Block until tokens are available or raise RateLimitedError."""

    @abstractmethod
    async def get_available_tokens(self) -> int:
        """Return the current number of tokens that can be acquired."""

    @abstractmethod
    async def reset(self) -> None:
        """Reset the limiter to its initial state."""

    @abstractmethod
    async def update_config(self, config: RateLimiterConfig) -> None:
        """Update limiter configuration and reset state."""

    @abstractmethod
    def get_config(self) -> RateLimiterConfig:
        """Return current configuration."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by limiter."""


class RateLimiter(RateLimiterBase):
    """Asynchronous rate limiter for token bucket, sliding window, and fixed window.

    All public methods are coroutines and must be awaited. The limiter can be
    shared across tasks in the same event loop.

    Args:
        config: Optional RateLimiterConfig. Defaults are used when omitted.
    """

    _WINDOW_SIZE_S = 1.0

    def __init__(self, config: RateLimiterConfig | None = None) -> None:
        self._config = config or RateLimiterConfig()
        self._algorithm = self._config.algorithm
        self._rate = max(0.0, float(self._config.rate))
        self._burst = max(0, int(self._config.burst))
        self._wait_timeout_ms = max(0, int(self._config.wait_timeout_ms))

        self._lock = asyncio.Lock()
        self._event = asyncio.Event()
        self._event.set()

        now = self._now()
        self._bucket_tokens = float(self._burst)
        self._bucket_last = now

        self._sliding_window: Deque[tuple[float, int]] = deque()
        self._sliding_count = 0

        self._fixed_window_start = now
        self._fixed_window_count = 0

    async def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting.

        Args:
            tokens: Number of tokens to consume.

        Returns:
            True when tokens were acquired, False otherwise.

        Raises:
            ValueError: If tokens is not a positive integer.
        """

        tokens = self._normalize_tokens(tokens)
        acquired, _ = await self._try_acquire(tokens)
        return acquired

    async def acquire_or_wait(self, tokens: int = 1) -> None:
        """Block until tokens are available or raise RateLimitedError.

        Args:
            tokens: Number of tokens to consume.

        Raises:
            RateLimitedError: If the wait exceeds wait_timeout_ms; data includes retry_after_ms.
            ValueError: If tokens is not a positive integer.
        """

        tokens = self._normalize_tokens(tokens)
        timeout_s = self._wait_timeout_ms / 1000.0
        deadline = self._now() + timeout_s
        last_wait_ms: int | None = None

        while True:
            acquired, wait_ms = await self._try_acquire(tokens)
            if acquired:
                return

            if wait_ms is None:
                raise RateLimitedError(data={"retry_after_ms": 0})

            last_wait_ms = max(0, int(wait_ms))
            if timeout_s <= 0:
                raise RateLimitedError(data={"retry_after_ms": last_wait_ms})

            now = self._now()
            if now >= deadline:
                raise RateLimitedError(data={"retry_after_ms": last_wait_ms})

            remaining = max(0.0, deadline - now)
            wait_s = min(remaining, last_wait_ms / 1000.0)
            if wait_s <= 0:
                continue

            self._prepare_wait()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=wait_s)
            except asyncio.TimeoutError:
                continue

    async def get_available_tokens(self) -> int:
        """Return the current number of tokens that can be acquired.

        Returns:
            The number of available tokens for the active algorithm.
        """

        async with self._lock:
            now = self._now()
            return self._available_tokens_locked(now)

    async def reset(self) -> None:
        """Reset the limiter to its initial state."""

        async with self._lock:
            now = self._now()
            self._bucket_tokens = float(self._burst)
            self._bucket_last = now

            self._sliding_window.clear()
            self._sliding_count = 0

            self._fixed_window_start = now
            self._fixed_window_count = 0

        self._notify_waiters()

    async def update_config(self, config: RateLimiterConfig) -> None:
        """Update limiter configuration and reset state."""
        async with self._lock:
            self._config = config
            self._algorithm = self._config.algorithm
            self._rate = max(0.0, float(self._config.rate))
            self._burst = max(0, int(self._config.burst))
            self._wait_timeout_ms = max(0, int(self._config.wait_timeout_ms))
            now = self._now()
            self._bucket_tokens = float(self._burst)
            self._bucket_last = now
            self._sliding_window.clear()
            self._sliding_count = 0
            self._fixed_window_start = now
            self._fixed_window_count = 0
        self._notify_waiters()

    def get_config(self) -> RateLimiterConfig:
        return self._config

    async def close(self) -> None:
        await self.reset()

    def _now(self) -> float:
        return time.monotonic()

    def _normalize_tokens(self, tokens: int) -> int:
        try:
            value = int(tokens)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("tokens must be a positive integer") from exc
        if value <= 0:
            raise ValueError("tokens must be a positive integer")
        return value

    def _window_limit(self) -> float:
        return self._rate

    async def _try_acquire(self, tokens: int) -> tuple[bool, int | None]:
        async with self._lock:
            now = self._now()
            if self._algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                return self._try_acquire_token_bucket(tokens, now)
            if self._algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
                return self._try_acquire_sliding_window(tokens, now)
            if self._algorithm == RateLimitAlgorithm.FIXED_WINDOW:
                return self._try_acquire_fixed_window(tokens, now)
            raise ValueError(f"Unsupported algorithm: {self._algorithm}")

    def _try_acquire_token_bucket(self, tokens: int, now: float) -> tuple[bool, int | None]:
        if self._burst <= 0 or tokens > self._burst:
            return False, None

        self._refill_token_bucket(now)
        if self._bucket_tokens >= tokens:
            self._bucket_tokens -= float(tokens)
            return True, 0

        wait_ms = self._token_bucket_wait_ms(tokens)
        return False, wait_ms

    def _try_acquire_sliding_window(self, tokens: int, now: float) -> tuple[bool, int | None]:
        limit = self._window_limit()
        if limit <= 0 or tokens > limit:
            return False, None

        self._cleanup_sliding_window(now)
        if self._sliding_count + tokens <= limit:
            self._sliding_window.append((now, tokens))
            self._sliding_count += tokens
            return True, 0

        wait_ms = self._sliding_wait_ms(now, tokens, limit)
        return False, wait_ms

    def _try_acquire_fixed_window(self, tokens: int, now: float) -> tuple[bool, int | None]:
        limit = self._window_limit()
        if limit <= 0 or tokens > limit:
            return False, None

        self._rotate_fixed_window(now)
        if self._fixed_window_count + tokens <= limit:
            self._fixed_window_count += tokens
            return True, 0

        wait_ms = self._fixed_wait_ms(now)
        return False, wait_ms

    def _refill_token_bucket(self, now: float) -> None:
        if self._rate <= 0:
            self._bucket_last = now
            return

        elapsed = max(0.0, now - self._bucket_last)
        if elapsed <= 0:
            return

        before = self._bucket_tokens
        self._bucket_tokens = min(self._burst, self._bucket_tokens + elapsed * self._rate)
        self._bucket_last = now
        if self._bucket_tokens > before:
            self._notify_waiters()

    def _token_bucket_wait_ms(self, tokens: int) -> int | None:
        if self._rate <= 0:
            return None
        needed = max(0.0, float(tokens) - self._bucket_tokens)
        if needed <= 0:
            return 0
        wait_s = needed / self._rate
        return int(math.ceil(wait_s * 1000.0))

    def _cleanup_sliding_window(self, now: float) -> None:
        if not self._sliding_window:
            return

        threshold = now - self._WINDOW_SIZE_S
        before = self._sliding_count
        while self._sliding_window and self._sliding_window[0][0] <= threshold:
            _, count = self._sliding_window.popleft()
            self._sliding_count -= count

        if self._sliding_count < before:
            self._notify_waiters()

    def _sliding_wait_ms(self, now: float, tokens: int, limit: float) -> int:
        if not self._sliding_window:
            return int(self._WINDOW_SIZE_S * 1000.0)

        excess = (self._sliding_count + tokens) - limit
        if excess <= 0:
            return 0

        running = 0
        for ts, count in self._sliding_window:
            running += count
            if running >= excess:
                wait_s = (ts + self._WINDOW_SIZE_S) - now
                return int(math.ceil(max(0.0, wait_s) * 1000.0))

        return int(math.ceil(self._WINDOW_SIZE_S * 1000.0))

    def _rotate_fixed_window(self, now: float) -> None:
        elapsed = now - self._fixed_window_start
        if elapsed < self._WINDOW_SIZE_S:
            return

        windows = int(elapsed // self._WINDOW_SIZE_S)
        self._fixed_window_start += windows * self._WINDOW_SIZE_S
        if self._fixed_window_count > 0:
            self._fixed_window_count = 0
            self._notify_waiters()

    def _fixed_wait_ms(self, now: float) -> int:
        wait_s = (self._fixed_window_start + self._WINDOW_SIZE_S) - now
        return int(math.ceil(max(0.0, wait_s) * 1000.0))

    def _available_tokens_locked(self, now: float) -> int:
        if self._algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            self._refill_token_bucket(now)
            return int(max(0.0, math.floor(self._bucket_tokens)))

        if self._algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            self._cleanup_sliding_window(now)
            limit = self._window_limit()
            return int(max(0.0, math.floor(limit - self._sliding_count)))

        if self._algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            self._rotate_fixed_window(now)
            limit = self._window_limit()
            return int(max(0.0, math.floor(limit - self._fixed_window_count)))

        return 0

    def _prepare_wait(self) -> None:
        if self._event.is_set():
            self._event.clear()

    def _notify_waiters(self) -> None:
        if not self._event.is_set():
            self._event.set()
