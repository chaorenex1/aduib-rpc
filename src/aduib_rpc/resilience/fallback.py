"""Fallback handling for resilient service calls.

This module provides an asyncio-friendly fallback executor that can guard
both synchronous and asynchronous callables. When a call fails, the executor
checks a fallback policy and dispatches to one or more handlers that attempt
to provide a substitute result.

Available handlers:
    - StaticValueFallback: always returns a fixed value.
    - CachedValueFallback: returns the last successful result captured by the executor.
    - CallableFallback: delegates to a user-supplied callable (sync or async).
    - ChainFallback: tries multiple handlers in order until one succeeds.

Concurrency notes:
    - CachedValueFallback uses a thread lock to protect cached values.
    - Handlers are invoked outside any locks.
"""

from __future__ import annotations

import inspect
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, TypeVar

from aduib_rpc.exceptions import RpcException

T = TypeVar("T")
CallableResult = Callable[..., T | Awaitable[T]]

_NO_CACHE = object()


class FallbackHandler(ABC):
    """Abstract interface for fallback handlers."""

    @abstractmethod
    def can_handle(self, error: Exception) -> bool:
        """Return True if this handler can process the error."""

    @abstractmethod
    async def handle(self, error: Exception, context: dict[str, Any]) -> Any:
        """Handle the error and return a fallback result."""


class StaticValueFallback(FallbackHandler):
    """Fallback handler that always returns a static value."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def can_handle(self, error: Exception) -> bool:
        """Return True because this handler always applies."""

        return True

    async def handle(self, error: Exception, context: dict[str, Any]) -> Any:
        """Return the configured static value."""

        return self._value


class CachedValueFallback(FallbackHandler):
    """Fallback handler that returns the last successful execution result."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: Any = _NO_CACHE
        self._has_cache = False

    @property
    def has_cache(self) -> bool:
        """Return True when a cached value is available."""

        with self._lock:
            return self._has_cache

    def clear_cache(self) -> None:
        """Clear the cached value."""

        with self._lock:
            self._value = _NO_CACHE
            self._has_cache = False

    def can_handle(self, error: Exception) -> bool:
        """Return True only when a cached value is available."""

        return self.has_cache

    async def handle(self, error: Exception, context: dict[str, Any]) -> Any:
        """Return the cached value or raise if none is available."""

        with self._lock:
            if not self._has_cache:
                raise LookupError("Cached fallback has no value")
            return self._value

    def _update_cache(self, value: Any) -> None:
        """Store a successful result for later fallback use."""

        with self._lock:
            self._value = value
            self._has_cache = True


class CallableFallback(FallbackHandler):
    """Fallback handler that delegates to a callable or coroutine function."""

    def __init__(self, func: Callable[..., Any], *, pass_error: bool = False) -> None:
        if not callable(func):
            raise TypeError("func must be callable")
        self._func = func
        self._pass_error = bool(pass_error)

    def can_handle(self, error: Exception) -> bool:
        """Return True because the callable can attempt a fallback."""

        return True

    async def handle(self, error: Exception, context: dict[str, Any]) -> Any:
        """Invoke the callable to compute a fallback result."""

        if self._pass_error:
            result = self._func(error, context)
        else:
            result = self._func(context)

        if inspect.isawaitable(result):
            return await result
        return result


class ChainFallback(FallbackHandler):
    """Fallback handler that tries multiple handlers in order."""

    def __init__(self, handlers: tuple[FallbackHandler, ...]) -> None:
        self.handlers = tuple(handlers)

    def can_handle(self, error: Exception) -> bool:
        """Return True if any handler can process the error."""

        return any(handler.can_handle(error) for handler in self.handlers)

    async def handle(self, error: Exception, context: dict[str, Any]) -> Any:
        """Try handlers in order until one succeeds."""

        last_exc: Exception | None = None
        for handler in self.handlers:
            if not handler.can_handle(error):
                continue
            try:
                return await handler.handle(error, context)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue

        if last_exc is not None:
            raise last_exc

        raise FallbackExhaustedError(data={"reason": "No handler could handle error"}, cause=error)


@dataclass(frozen=True, slots=True)
class FallbackPolicy:
    """Configuration for fallback behavior.

    Attributes:
        handlers: Ordered fallback handlers to attempt.
        fallback_on: Exception types that trigger fallback. None means all.
        propagate_original_error: Whether to raise the original error when fallbacks fail.
        include_context: Whether to include call context in handler invocations.
    """

    handlers: tuple[FallbackHandler, ...]
    fallback_on: tuple[type[Exception], ...] | None = None
    propagate_original_error: bool = True
    include_context: bool = True


@dataclass
class FallbackExhaustedError(RpcException):
    """Raised when all fallback handlers fail or are exhausted."""

    code: int = 5040
    message: str = "All fallback handlers exhausted"


class FallbackExecutor:
    """Execute callables and apply fallback handlers on failure."""

    def __init__(self, policy: FallbackPolicy) -> None:
        self._policy = policy
        self._handlers = tuple(policy.handlers)
        self._fallback_on = tuple(policy.fallback_on) if policy.fallback_on is not None else None
        self._propagate_original_error = bool(policy.propagate_original_error)
        self._include_context = bool(policy.include_context)

    async def execute(
        self,
        func: CallableResult[T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute func and apply fallbacks when it fails."""

        if not callable(func):
            raise TypeError("func must be callable")

        try:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001
            if not self._should_fallback(exc):
                raise

            context = self._build_context(func, args, kwargs) if self._include_context else {}
            handler_error: Exception | None = None

            for handler in self._handlers:
                if not handler.can_handle(exc):
                    continue
                try:
                    return await handler.handle(exc, context)
                except Exception as handler_exc:  # noqa: BLE001
                    handler_error = handler_exc
                    continue

            if self._propagate_original_error:
                raise

            raise self._build_exhausted_error(exc, handler_error)
        else:
            self._record_success(result)
            return result

    def _should_fallback(self, error: Exception) -> bool:
        """Return True when the error matches fallback criteria."""

        if self._fallback_on is None:
            return True
        return isinstance(error, self._fallback_on)

    def _build_context(
        self,
        func: CallableResult[T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a context dictionary for fallback handlers."""

        return {"func": func, "args": args, "kwargs": kwargs}

    def _record_success(self, value: Any) -> None:
        """Update cached fallback handlers with the latest successful value."""

        for handler in self._iter_cached_handlers(self._handlers):
            handler._update_cache(value)

    def _iter_cached_handlers(
        self, handlers: tuple[FallbackHandler, ...]
    ) -> Iterable[CachedValueFallback]:
        for handler in handlers:
            if isinstance(handler, CachedValueFallback):
                yield handler
            elif isinstance(handler, ChainFallback):
                yield from self._iter_cached_handlers(handler.handlers)

    def _build_exhausted_error(
        self, original_error: Exception, handler_error: Exception | None
    ) -> FallbackExhaustedError:
        data = {
            "original_error": type(original_error).__name__,
            "handler_error": type(handler_error).__name__ if handler_error else None,
        }
        cause = handler_error or original_error
        return FallbackExhaustedError(data=data, cause=cause)
