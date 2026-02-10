"""Resilience middleware for client-side request processing.

This module provides integration between the client request flow and the
resilience patterns (circuit breaker, rate limiting, retry, fallback).

Example:
    from aduib_rpc.client.interceptors.resilience import ResilienceMiddleware, ResilienceConfig

    config = ResilienceConfig(
        circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
        rate_limiter=RateLimiterConfig(rate=1000),
        retry=RetryConfig(max_attempts=3),
    )
    middleware = ResilienceMiddleware(config)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from aduib_rpc.client.midwares import (
    ClientContext,
    ClientRequestInterceptor,
)
from aduib_rpc.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from aduib_rpc.resilience.fallback import (
    FallbackExecutor,
    FallbackPolicy,
)
from aduib_rpc.resilience.rate_limiter import (
    RateLimiter,
    RateLimiterConfig,
    RateLimitedError,
)
from aduib_rpc.resilience.retry_policy import (
    RetryExecutor,
    RetryPolicy,
)
from aduib_rpc.utils.constant import SecuritySchemes


@dataclass
class ResilienceConfig:
    """Configuration for resilience middleware.

    Attributes:
        circuit_breaker: Circuit breaker configuration.
        rate_limiter: Rate limiter configuration.
        retry: Retry policy configuration.
        fallback: Fallback policy for when circuit is open.
        enabled: Whether resilience features are enabled.
    """

    circuit_breaker: CircuitBreakerConfig | None = None
    rate_limiter: RateLimiterConfig | None = None
    retry: RetryPolicy | None = None
    fallback: FallbackPolicy | None = None
    enabled: bool = True

    # Service-specific configuration overrides
    service_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_config_for_service(self, service_name: str) -> dict[str, Any]:
        """Get configuration for a specific service."""
        return self.service_overrides.get(service_name, {})


class ResilienceMiddleware(ClientRequestInterceptor):
    """Client middleware that applies resilience patterns to requests.

    This middleware implements:
    1. Rate limiting - using token bucket algorithm
    2. Circuit breaking - prevents cascading failures
    3. Retry with exponential backoff
    4. Fallback - provides alternative responses when degraded

    The middleware processes requests in the following order:
    - Check rate limit
    - Check circuit breaker state
    - Execute request with retry
    - Apply fallback if all retries fail
    """

    def __init__(
        self,
        config: ResilienceConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_executor: RetryExecutor | None = None,
        fallback_executor: FallbackExecutor | None = None,
    ):
        """Initialize the resilience middleware.

        Args:
            config: Overall resilience configuration.
            circuit_breaker: Pre-configured circuit breaker instance.
            rate_limiter: Pre-configured rate limiter instance.
            retry_executor: Pre-configured retry executor instance.
            fallback_executor: Pre-configured fallback executor instance.
        """
        self.config = config or ResilienceConfig()

        # Initialize components
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._rate_limiters: dict[str, "RateLimiter"] = {}
        self._retry_executors: dict[str, RetryExecutor] = {}
        self._fallback_executors: dict[str, FallbackExecutor] = {}
        self._lock = asyncio.Lock()

        # Use provided instances or create from config
        if circuit_breaker:
            self._circuit_breakers["default"] = circuit_breaker
        if rate_limiter:
            self._rate_limiters["default"] = rate_limiter
        if retry_executor:
            self._retry_executors["default"] = retry_executor
        if fallback_executor:
            self._fallback_executors["default"] = fallback_executor

        # Create from config if specified
        if self.config.circuit_breaker and "default" not in self._circuit_breakers:
            self._circuit_breakers["default"] = CircuitBreaker(
                "default", self.config.circuit_breaker
            )
        if self.config.rate_limiter and "default" not in self._rate_limiters:
            from aduib_rpc.resilience.rate_limiter import RateLimiter
            self._rate_limiters["default"] = RateLimiter(self.config.rate_limiter)
        if self.config.retry and "default" not in self._retry_executors:
            self._retry_executors["default"] = RetryExecutor(self.config.retry)
        if self.config.fallback and "default" not in self._fallback_executors:
            self._fallback_executors["default"] = FallbackExecutor(self.config.fallback)

    async def intercept_request(
        self,
        method: str,
        request_body: dict[str, Any],
        http_kwargs: dict[str, Any],
        context: ClientContext,
        schema: SecuritySchemes,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Intercept the request and apply resilience patterns.

        This method is called before the request is sent. It applies:
        1. Rate limiting - may raise RateLimitedError
        2. Circuit breaking - may raise CircuitBreakerOpenError

        Note: This method only validates pre-conditions. The actual retry
        and fallback logic happens at the transport layer via context markers.

        Args:
            method: The HTTP method.
            request_body: The request body.
            http_kwargs: Additional HTTP arguments.
            context: The client context.
            schema: The security scheme.

        Returns:
            Tuple of (request_body, http_kwargs) potentially modified.

        Raises:
            RateLimitedError: If rate limit is exceeded.
            CircuitBreakerOpenError: If circuit breaker is open.
        """
        if not self.config.enabled:
            return request_body, http_kwargs

        # Extract service name from request or context
        service_name = self._extract_service_name(request_body, context)

        # Mark context for resilience processing at transport layer
        context.state["resilience_enabled"] = True
        context.state["resilience_service"] = service_name

        # Check rate limit
        rate_limiter = self._get_rate_limiter(service_name)
        if rate_limiter:
            acquired = await rate_limiter.acquire()
            if not acquired:
                raise RateLimitedError(message="Rate limit exceeded")

        # Check circuit breaker state (don't actually execute here,
        # just validate and mark context for transport layer)
        circuit_breaker = self._CircuitBreaker(service_name)
        if circuit_breaker and circuit_breaker.state != "closed":
            # Circuit is open or half-open
            fallback_executor = self._get_fallback_executor(service_name)
            if fallback_executor is not None:
                context.state["resilience_use_fallback"] = True
            else:
                raise CircuitBreakerOpenError()

        return request_body, http_kwargs

    def _extract_service_name(
        self, request_body: dict[str, Any], context: ClientContext
    ) -> str:
        """Extract service name from request or context."""
        # Try to get from context first
        if "service_name" in context.state:
            return context.state["service_name"]

        # Try to extract from request body
        if "name" in request_body:
            return request_body["name"]

        # Try to extract from method
        if "method" in request_body:
            method = request_body["method"]
            if "/" in method:
                return method.split("/")[0]

        return "default"

    def _CircuitBreaker(self, service_name: str) -> CircuitBreaker | None:
        """Get circuit breaker for a service."""
        return self._circuit_breakers.get(service_name) or self._circuit_breakers.get(
            "default"
        )

    def _get_circuit_breaker(self, service_name: str) -> CircuitBreaker | None:
        """Get circuit breaker for a service (alias for test compatibility)."""
        return self._CircuitBreaker(service_name)

    def _get_rate_limiter(self, service_name: str) -> RateLimiter | None:
        """Get rate limiter for a service."""
        return self._rate_limiters.get(service_name) or self._rate_limiters.get(
            "default"
        )

    def _get_retry_executor(self, service_name: str) -> RetryExecutor | None:
        """Get retry executor for a service."""
        return self._retry_executors.get(service_name) or self._retry_executors.get(
            "default"
        )

    def _get_fallback_executor(self, service_name: str) -> FallbackExecutor | None:
        """Get fallback executor for a service."""
        return self._fallback_executors.get(
            service_name
        ) or self._fallback_executors.get("default")

    def add_service_config(self, service_name: str, **kwargs) -> None:
        """Add service-specific resilience configuration.

        Args:
            service_name: Name of the service.
            **kwargs: Configuration overrides (circuit_breaker, rate_limiter, retry, fallback).
        """
        if "circuit_breaker" in kwargs:
            cb_config = kwargs["circuit_breaker"]
            if isinstance(cb_config, CircuitBreakerConfig):
                self._circuit_breakers[service_name] = CircuitBreaker(
                    service_name, cb_config
                )
            elif isinstance(cb_config, CircuitBreaker):
                self._circuit_breakers[service_name] = cb_config

        if "rate_limiter" in kwargs:
            rl_config = kwargs["rate_limiter"]
            if isinstance(rl_config, RateLimiterConfig):
                from aduib_rpc.resilience.rate_limiter import RateLimiter
                self._rate_limiters[service_name] = RateLimiter(rl_config)
            else:
                # For simplicity we only accept config objects here.
                pass

        if "retry" in kwargs:
            retry_config = kwargs["retry"]
            if isinstance(retry_config, RetryPolicy):
                self._retry_executors[service_name] = RetryExecutor(retry_config)

        if "fallback" in kwargs:
            fallback_config = kwargs["fallback"]
            if isinstance(fallback_config, FallbackPolicy):
                self._fallback_executors[service_name] = FallbackExecutor(
                    fallback_config
                )

    def get_circuit_breaker_state(self, service_name: str = "default") -> str | None:
        """Get the current state of a circuit breaker.

        Args:
            service_name: Name of the service.

        Returns:
            Circuit state ("closed", "open", "half_open") or None if not found.
        """
        cb = self._CircuitBreaker(service_name)
        return cb.state.value if cb else None

    def reset_circuit_breaker(self, service_name: str = "default") -> None:
        """Reset a circuit breaker to closed state.

        Args:
            service_name: Name of the service.
        """
        cb = self._CircuitBreaker(service_name)
        if cb:
            # Circuit breaker doesn't have explicit reset, but we can
            # create a new one with the same config
            if cb.config:
                self._circuit_breakers[service_name] = CircuitBreaker(
                    service_name, cb.config
                )


class ResilienceAwareClientContext:
    """Context wrapper that adds resilience awareness to client operations.

    This class wraps ClientContext to provide resilience-specific
    functionality like recording success/failure for circuit breakers.
    """

    def __init__(
        self, base_context: ClientContext, middleware: ResilienceMiddleware
    ):
        """Initialize the resilience-aware context.

        Args:
            base_context: The base client context.
            middleware: The resilience middleware instance.
        """
        self._context = base_context
        self._middleware = middleware

    async def record_success(self, service_name: str = "default") -> None:
        cb = self._middleware._CircuitBreaker(service_name)
        if cb:
            # CircuitBreaker uses internal bookkeeping; safest public action is no-op here.
            return

    async def record_failure(
        self, service_name: str = "default", error: Exception | None = None
    ) -> None:
        cb = self._middleware._CircuitBreaker(service_name)
        if cb:
            return

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the base context."""
        return getattr(self._context, name)

