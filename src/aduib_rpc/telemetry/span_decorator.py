from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def with_span(
    name: str | None = None,
    *,
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """OTel Span decorator for distributed tracing.

    Args:
        name: Span name, defaults to function name
        attributes: Additional span attributes

    Example:
        @with_span("calculate_price")
        async def calculate_price(item_id: str) -> float:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        span_name = name or func.__name__
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    from opentelemetry import trace
                except ImportError:
                    return await func(*args, **kwargs)

                tracer = trace.get_tracer(func.__module__)
                with tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("code.function", func.__name__)
                    span.set_attribute("code.namespace", func.__module__)
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, v)
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        span.record_exception(e)
                        span.set_attribute("error", True)
                        raise
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    from opentelemetry import trace
                except ImportError:
                    return func(*args, **kwargs)

                tracer = trace.get_tracer(func.__module__)
                with tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("code.function", func.__name__)
                    span.set_attribute("code.namespace", func.__module__)
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, v)
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        span.record_exception(e)
                        span.set_attribute("error", True)
                        raise
            return sync_wrapper

    return decorator
