"""Resilience middleware for client-side request processing.

This module provides integration between the client request flow and the
resilience patterns (circuit breaker, rate limiting, fallback).

Example:
    from aduib_rpc.client.interceptors.resilience import ResilienceMiddleware, ResilienceConfig

    config = ResilienceConfig(
        circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
        rate_limiter=RateLimiterConfig(rate=1000),
    )
    middleware = ResilienceMiddleware(config)
"""
from __future__ import annotations

from dataclasses import dataclass

from aduib_rpc.resilience.circuit_breaker import (
    CircuitBreakerConfig,
)
from aduib_rpc.resilience.fallback import (
    FallbackPolicy,
)
from aduib_rpc.resilience.rate_limiter import (
    RateLimiterConfig,
)
from aduib_rpc.resilience.retry_policy import RetryPolicy


@dataclass
class ResilienceConfig:
    """Configuration for resilience middleware.

    Attributes:
        circuit_breaker: Circuit breaker configuration.
        rate_limiter: Rate limiter configuration.
        retry: Retry policy configuration (forwarded to server QoS; not executed here).
        fallback: Fallback policy for when circuit is open.
        enabled: Whether resilience features are enabled.
    """

    circuit_breaker: CircuitBreakerConfig | None = None
    rate_limiter: RateLimiterConfig | None = None
    retry: RetryPolicy | None = None
    fallback: FallbackPolicy | None = None
    enabled: bool = True

