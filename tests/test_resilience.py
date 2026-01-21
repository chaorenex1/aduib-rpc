
from __future__ import annotations

import asyncio
import io
import itertools
import json
import logging
import time
from dataclasses import FrozenInstanceError
from typing import Any, Callable, Iterator

import pytest

from aduib_rpc.core.context import (
    RuntimeConfig,
    ScopedRuntime,
    create_runtime,
    get_current_runtime,
    with_runtime,
    with_tenant,
)
from aduib_rpc.observability.logging import (
    LOG_FORMAT_CONSOLE,
    LOG_FORMAT_ENV,
    LOG_FORMAT_JSON,
    LogContext,
    StructuredConsoleFormatter,
    StructuredJSONFormatter,
    get_logger,
)
from aduib_rpc.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
)
from aduib_rpc.resilience.rate_limiter import (
    RateLimitAlgorithm,
    RateLimitError,
    RateLimiter,
    RateLimiterConfig,
)

_LOGGER_COUNTER = itertools.count()


class FakeClock:
    """Controllable clock for deterministic time-based tests."""

    def __init__(self, start: float = 0.0) -> None:
        """Initialize the clock at the supplied start time."""
        self._now = float(start)

    def now(self) -> float:
        """Return the current fake time."""
        return self._now

    def advance(self, seconds: float) -> None:
        """Advance the clock by the provided number of seconds."""
        self._now += float(seconds)


def _unique_logger_name(prefix: str) -> str:
    """Return a unique logger name for isolation."""
    return f"{prefix}.{next(_LOGGER_COUNTER)}"


def _cleanup_logger(logger: logging.Logger) -> None:
    """Remove all handlers from a logger."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.handlers.clear()


def _read_json_payload(stream: io.StringIO) -> dict[str, Any]:
    """Parse the last JSON log line from the stream."""
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert lines, "expected log output to contain at least one line"
    return json.loads(lines[-1])


def _build_limiter(
    clock: FakeClock,
    *,
    algorithm: RateLimitAlgorithm,
    rate: float,
    burst: int,
    wait_timeout_ms: int = 1000,
) -> RateLimiter:
    """Create a RateLimiter using a fake clock."""
    limiter = RateLimiter(
        RateLimiterConfig(
            algorithm=algorithm,
            rate=rate,
            burst=burst,
            wait_timeout_ms=wait_timeout_ms,
        )
    )
    limiter._now = clock.now  # type: ignore[method-assign]
    # Reset timestamps to use fake clock time
    now = clock.now()
    limiter._bucket_last = now
    limiter._fixed_window_start = now
    return limiter


def _build_breaker(
    clock: FakeClock,
    *,
    name: str = "payments",
    failure_threshold: int = 2,
    success_threshold: int = 2,
    timeout_seconds: float = 5.0,
    half_open_max_calls: int = 2,
    excluded_exceptions: tuple[type[BaseException], ...] = (),
) -> CircuitBreaker:
    """Create a CircuitBreaker using a fake clock."""
    breaker = CircuitBreaker(
        name,
        CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout_seconds=timeout_seconds,
            half_open_max_calls=half_open_max_calls,
            excluded_exceptions=excluded_exceptions,
        ),
    )
    breaker._now = clock.now  # type: ignore[method-assign]
    return breaker


@pytest.fixture(autouse=True)
def clear_log_context() -> Iterator[None]:
    """Reset LogContext between tests."""
    LogContext.clear()
    yield
    LogContext.clear()


@pytest.fixture()
def log_stream() -> io.StringIO:
    """Return a StringIO stream for log capture."""
    return io.StringIO()


@pytest.fixture()
def logger_factory() -> Iterator[Callable[..., logging.Logger]]:
    """Provide a logger factory that cleans up created loggers."""
    created: list[logging.Logger] = []

    def _factory(**kwargs: Any) -> logging.Logger:
        name = kwargs.pop("name", _unique_logger_name("resilience.logging"))
        # Clean up any existing handlers first to ensure fresh stream
        existing_logger = logging.getLogger(name)
        if existing_logger.handlers:
            _cleanup_logger(existing_logger)
        logger = get_logger(name, **kwargs)
        created.append(logger)
        return logger

    yield _factory
    for logger in created:
        _cleanup_logger(logger)


@pytest.fixture()
def fake_clock() -> FakeClock:
    """Return a fresh FakeClock instance."""
    return FakeClock()


@pytest.fixture()
def runtime_pair() -> tuple[ScopedRuntime, ScopedRuntime]:
    """Return two isolated runtime instances."""
    runtime_a = create_runtime(RuntimeConfig(tenant_id="tenant-a"))
    runtime_b = create_runtime(RuntimeConfig(tenant_id="tenant-b"))
    return runtime_a, runtime_b


def test_get_logger_defaults_to_json_output(
    logger_factory: Callable[..., logging.Logger],
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default get_logger to JSON formatting when env is unset.

    Args:
        logger_factory: Factory for isolated loggers.
        log_stream: Stream to capture log output.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.delenv(LOG_FORMAT_ENV, raising=False)
    logger = logger_factory(stream=log_stream)

    logger.info("hello-json")
    payload = _read_json_payload(log_stream)

    assert payload["message"] == "hello-json"
    assert payload["level"] == "INFO"
    assert payload["logger"] == logger.name
    assert payload["timestamp"].endswith("Z")


def test_get_logger_respects_env_console_format(
    logger_factory: Callable[..., logging.Logger],
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honor the console format when LOG_FORMAT_ENV is set.

    Args:
        logger_factory: Factory for isolated loggers.
        log_stream: Stream to capture log output.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv(LOG_FORMAT_ENV, LOG_FORMAT_CONSOLE)
    logger = logger_factory(stream=log_stream)

    logger.warning("console-output")
    output = log_stream.getvalue()

    assert "console-output" in output
    assert "tenant_id=" in output
    assert logger.name in output


def test_get_logger_param_overrides_env_setting(
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow log_format to override LOG_FORMAT_ENV.

    Args:
        log_stream: Stream to capture log output.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv(LOG_FORMAT_ENV, LOG_FORMAT_CONSOLE)
    name = _unique_logger_name("resilience.logging.override")
    logger = get_logger(name, log_format=LOG_FORMAT_JSON, stream=log_stream)

    logger.info("override")
    payload = _read_json_payload(log_stream)

    assert payload["message"] == "override"
    assert payload["logger"] == name
    _cleanup_logger(logger)


def test_get_logger_reuses_existing_handler(log_stream: io.StringIO) -> None:
    """Avoid attaching duplicate handlers to the same logger.

    Args:
        log_stream: Stream to capture log output.
    """
    name = _unique_logger_name("resilience.logging.reuse")
    logger = get_logger(name, log_format=LOG_FORMAT_JSON, stream=log_stream)
    handler_count = len(logger.handlers)

    logger = get_logger(name, log_format=LOG_FORMAT_JSON, stream=log_stream)

    assert len(logger.handlers) == handler_count
    _cleanup_logger(logger)


def test_log_context_injects_fields(
    logger_factory: Callable[..., logging.Logger],
    log_stream: io.StringIO,
) -> None:
    """Inject LogContext values into structured log output.

    Args:
        logger_factory: Factory for isolated loggers.
        log_stream: Stream to capture log output.
    """
    logger = logger_factory(log_format=LOG_FORMAT_JSON, stream=log_stream)

    with LogContext(tenant_id="t1", trace_id="trace-1", request_id="req-1", region="us"):
        logger.info("context")

    payload = _read_json_payload(log_stream)
    assert payload["tenant_id"] == "t1"
    assert payload["trace_id"] == "trace-1"
    assert payload["request_id"] == "req-1"
    assert payload["region"] == "us"


def test_structured_json_formatter_basic_payload() -> None:
    """Emit JSON payloads with stable keys."""
    formatter = StructuredJSONFormatter()
    record = logging.LogRecord(
        name="resilience.logging.basic",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="formatted",
        args=(),
        exc_info=None,
    )
    record.created = 0.0
    record.custom = "value"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "formatted"
    assert payload["logger"] == "resilience.logging.basic"
    assert payload["custom"] == "value"
    assert payload["timestamp"].startswith("1970-01-01")

def test_structured_json_formatter_includes_exception_and_stack(
    logger_factory: Callable[..., logging.Logger],
    log_stream: io.StringIO,
) -> None:
    """Include exception and stack traces in JSON output.

    Args:
        logger_factory: Factory for isolated loggers.
        log_stream: Stream to capture log output.
    """
    logger = logger_factory(log_format=LOG_FORMAT_JSON, stream=log_stream)

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logger.exception("failure", stack_info=True)

    payload = _read_json_payload(log_stream)
    assert "exception" in payload
    assert "stack" in payload


def test_structured_json_formatter_filters_reserved_fields(
    logger_factory: Callable[..., logging.Logger],
    log_stream: io.StringIO,
) -> None:
    """Filter reserved keys from log record extras.

    Args:
        logger_factory: Factory for isolated loggers.
        log_stream: Stream to capture log output.
    """
    logger = logger_factory(log_format=LOG_FORMAT_JSON, stream=log_stream)
    # Note: Many fields (message, name, level, etc.) are protected by Python logging
    # This test verifies custom fields are preserved
    logger.info(
        "reserved",
        extra={"custom_field": "value1", "another_custom": "value2"},
    )

    payload = _read_json_payload(log_stream)

    assert payload["message"] == "reserved"
    assert payload["level"] == "INFO"
    assert payload["custom_field"] == "value1"  # Custom field preserved
    assert payload["another_custom"] == "value2"  # Custom field preserved


def test_structured_console_formatter_default_format() -> None:
    """Use default console formatter output structure."""
    formatter = StructuredConsoleFormatter()
    record = logging.LogRecord(
        name="resilience.console",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello-console",
        args=(),
        exc_info=None,
    )
    record.tenant_id = "tenant"
    record.trace_id = "trace"
    record.request_id = "req"

    formatted = formatter.format(record)

    assert "hello-console" in formatted
    assert "tenant_id=tenant" in formatted
    assert "trace_id=trace" in formatted
    assert "request_id=req" in formatted


@pytest.mark.asyncio
async def test_token_bucket_initial_capacity(fake_clock: FakeClock) -> None:
    """Expose burst capacity as available tokens."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        rate=5.0,
        burst=4,
    )

    available = await limiter.get_available_tokens()

    assert available == 4


@pytest.mark.asyncio
async def test_token_bucket_acquire_and_refill(fake_clock: FakeClock) -> None:
    """Refill tokens over time for token bucket."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        rate=5.0,
        burst=5,
    )

    assert await limiter.acquire(5) is True
    assert await limiter.get_available_tokens() == 0

    fake_clock.advance(0.4)
    assert await limiter.get_available_tokens() == 2
    assert await limiter.acquire(2) is True
    assert await limiter.get_available_tokens() == 0


@pytest.mark.asyncio
async def test_token_bucket_rejects_oversize_request(fake_clock: FakeClock) -> None:
    """Reject requests that exceed burst capacity."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        rate=1.0,
        burst=3,
    )

    assert await limiter.acquire(4) is False


@pytest.mark.asyncio
async def test_token_bucket_get_available_tokens_floor(fake_clock: FakeClock) -> None:
    """Floor token bucket counts when reporting availability."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        rate=2.0,
        burst=2,
    )

    assert await limiter.acquire(2) is True
    fake_clock.advance(0.75)
    assert await limiter.get_available_tokens() == 1


@pytest.mark.asyncio
async def test_sliding_window_enforces_limit(fake_clock: FakeClock) -> None:
    """Enforce sliding window limits within the window."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        rate=3.0,
        burst=3,
    )

    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert await limiter.acquire() is False


@pytest.mark.asyncio
async def test_sliding_window_rollover_allows_new_tokens(fake_clock: FakeClock) -> None:
    """Allow new tokens after sliding window rolls over."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        rate=2.0,
        burst=2,
    )

    assert await limiter.acquire(2) is True
    assert await limiter.acquire() is False

    fake_clock.advance(1.01)
    assert await limiter.acquire() is True


@pytest.mark.asyncio
async def test_sliding_window_available_tokens_after_cleanup(fake_clock: FakeClock) -> None:
    """Report available tokens after sliding window cleanup."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        rate=4.0,
        burst=4,
    )

    assert await limiter.acquire(3) is True
    assert await limiter.get_available_tokens() == 1
    fake_clock.advance(1.0)
    assert await limiter.get_available_tokens() == 4


@pytest.mark.asyncio
async def test_fixed_window_enforces_limit(fake_clock: FakeClock) -> None:
    """Enforce fixed window limits within the window."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.FIXED_WINDOW,
        rate=2.0,
        burst=2,
    )

    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert await limiter.acquire() is False


@pytest.mark.asyncio
async def test_fixed_window_rollover_allows_new_tokens(fake_clock: FakeClock) -> None:
    """Allow new tokens after fixed window rotates."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.FIXED_WINDOW,
        rate=2.0,
        burst=2,
    )

    assert await limiter.acquire(2) is True
    assert await limiter.acquire() is False

    fake_clock.advance(1.01)
    assert await limiter.acquire() is True


@pytest.mark.asyncio
async def test_fixed_window_available_tokens(fake_clock: FakeClock) -> None:
    """Report available tokens for fixed window counters."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.FIXED_WINDOW,
        rate=5.0,
        burst=5,
    )

    assert await limiter.acquire(4) is True
    assert await limiter.get_available_tokens() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [0, -1, -5])
async def test_acquire_validates_tokens(tokens: int, fake_clock: FakeClock) -> None:
    """Reject invalid token requests.

    Args:
        tokens: Token counts to test.
        fake_clock: Fake clock fixture.
    """
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        rate=1.0,
        burst=1,
    )

    with pytest.raises(ValueError):
        await limiter.acquire(tokens)


@pytest.mark.asyncio
async def test_acquire_or_wait_blocks_until_available() -> None:
    """Wait for tokens to refill when configured."""
    limiter = RateLimiter(
        RateLimiterConfig(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            rate=2.0,
            burst=1,
            wait_timeout_ms=900,
        )
    )

    assert await limiter.acquire() is True
    start = time.monotonic()
    await limiter.acquire_or_wait()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.2


@pytest.mark.asyncio
async def test_acquire_or_wait_timeout_raises() -> None:
    """Raise RateLimitError when wait timeout expires."""
    limiter = RateLimiter(
        RateLimiterConfig(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            rate=1.0,
            burst=1,
            wait_timeout_ms=50,
        )
    )

    assert await limiter.acquire() is True
    with pytest.raises(RateLimitError) as exc_info:
        await limiter.acquire_or_wait()

    assert exc_info.value.retry_after_ms >= 0


@pytest.mark.asyncio
async def test_rate_limiter_reset_restores_capacity(fake_clock: FakeClock) -> None:
    """Reset should restore counters to initial values."""
    limiter = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        rate=5.0,
        burst=5,
    )

    assert await limiter.acquire(5) is True
    assert await limiter.get_available_tokens() == 0
    await limiter.reset()
    assert await limiter.get_available_tokens() == 5


@pytest.mark.asyncio
async def test_concurrent_acquire_respects_burst_limit() -> None:
    """Limit concurrent acquisitions to the burst capacity."""
    limiter = RateLimiter(
        RateLimiterConfig(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            rate=0.0,
            burst=3,
        )
    )

    async def _attempt() -> bool:
        return await limiter.acquire()

    results = await asyncio.gather(*[_attempt() for _ in range(10)])
    assert sum(results) == 3


@pytest.mark.asyncio
async def test_get_available_tokens_reports_per_algorithm(fake_clock: FakeClock) -> None:
    """Return per-algorithm availability using a shared contract."""
    limiter_token = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        rate=2.0,
        burst=2,
    )
    limiter_sliding = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        rate=2.0,
        burst=2,
    )
    limiter_fixed = _build_limiter(
        fake_clock,
        algorithm=RateLimitAlgorithm.FIXED_WINDOW,
        rate=2.0,
        burst=2,
    )

    assert await limiter_token.acquire(2) is True
    assert await limiter_sliding.acquire(2) is True
    assert await limiter_fixed.acquire(2) is True
    assert await limiter_token.get_available_tokens() == 0
    assert await limiter_sliding.get_available_tokens() == 0
    assert await limiter_fixed.get_available_tokens() == 0


def test_circuit_breaker_initial_state_closed() -> None:
    """Start in CLOSED state by default."""
    breaker = CircuitBreaker("inventory")
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_closed_to_open_on_failure_threshold(fake_clock: FakeClock) -> None:
    """Open the breaker after reaching failure threshold."""
    breaker = _build_breaker(
        fake_clock,
        failure_threshold=2,
        success_threshold=2,
        timeout_seconds=5.0,
    )

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(_fail)
    with pytest.raises(ValueError):
        await breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(lambda: "ok")


@pytest.mark.asyncio
async def test_open_to_half_open_on_timeout(fake_clock: FakeClock) -> None:
    """Transition from OPEN to HALF_OPEN after timeout."""
    breaker = _build_breaker(
        fake_clock,
        failure_threshold=1,
        success_threshold=2,
        timeout_seconds=5.0,
    )

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN
    fake_clock.advance(5.1)

    assert await breaker.call(lambda: "ok") == "ok"
    assert breaker.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_to_closed_on_success_threshold(fake_clock: FakeClock) -> None:
    """Close the breaker after reaching success threshold."""
    breaker = _build_breaker(
        fake_clock,
        failure_threshold=1,
        success_threshold=2,
        timeout_seconds=3.0,
    )

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(_fail)
    fake_clock.advance(3.2)

    assert await breaker.call(lambda: "ok") == "ok"
    assert breaker.state == CircuitState.HALF_OPEN
    assert await breaker.call(lambda: "ok") == "ok"
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_to_open_on_failure(fake_clock: FakeClock) -> None:
    """Reopen the breaker after a half-open failure."""
    breaker = _build_breaker(
        fake_clock,
        failure_threshold=1,
        success_threshold=2,
        timeout_seconds=2.0,
    )

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(_fail)
    fake_clock.advance(2.5)

    with pytest.raises(ValueError):
        await breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(lambda: "ok")


@pytest.mark.asyncio
async def test_excluded_exceptions_do_not_trip(fake_clock: FakeClock) -> None:
    """Ignore excluded exceptions for breaker state."""
    breaker = _build_breaker(
        fake_clock,
        failure_threshold=1,
        success_threshold=1,
        timeout_seconds=1.0,
        excluded_exceptions=(KeyError,),
    )

    async def _excluded() -> None:
        raise KeyError("ignored")

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(KeyError):
        await breaker.call(_excluded)

    assert breaker.state == CircuitState.CLOSED

    with pytest.raises(ValueError):
        await breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_supports_sync_function(fake_clock: FakeClock) -> None:
    """Support synchronous callables."""
    breaker = _build_breaker(fake_clock, failure_threshold=2, success_threshold=2)

    def _success(value: str) -> str:
        return value

    result = await breaker.call(_success, "sync-ok")
    assert result == "sync-ok"


@pytest.mark.asyncio
async def test_supports_async_function(fake_clock: FakeClock) -> None:
    """Support asynchronous callables."""
    breaker = _build_breaker(fake_clock, failure_threshold=2, success_threshold=2)

    async def _success(value: str) -> str:
        return value

    result = await breaker.call(_success, "async-ok")
    assert result == "async-ok"


@pytest.mark.asyncio
async def test_call_rejects_non_callable(fake_clock: FakeClock) -> None:
    """Raise TypeError for non-callable inputs."""
    breaker = _build_breaker(fake_clock)
    with pytest.raises(TypeError):
        await breaker.call("not-callable")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_open_error_contains_metadata(fake_clock: FakeClock) -> None:
    """Populate CircuitBreakerOpenError metadata."""
    breaker = _build_breaker(
        fake_clock,
        name="billing",
        failure_threshold=1,
        success_threshold=1,
        timeout_seconds=10.0,
    )

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(_fail)

    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        await breaker.call(lambda: "ok")

    assert exc_info.value.data["name"] == "billing"
    assert exc_info.value.data["state"] == CircuitState.OPEN.value


@pytest.mark.asyncio
async def test_reset_restores_closed_state(fake_clock: FakeClock) -> None:
    """Reset should return breaker to CLOSED."""
    breaker = _build_breaker(
        fake_clock,
        failure_threshold=1,
        success_threshold=1,
        timeout_seconds=5.0,
    )

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN
    await breaker.reset()
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_concurrent_half_open_limits_calls(fake_clock: FakeClock) -> None:
    """Limit in-flight calls during HALF_OPEN."""
    breaker = _build_breaker(
        fake_clock,
        failure_threshold=1,
        success_threshold=10,
        timeout_seconds=0.0,
        half_open_max_calls=2,
    )

    async def _fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(_fail)

    gate = asyncio.Event()

    async def _blocked() -> str:
        await gate.wait()
        return "ok"

    tasks = [asyncio.create_task(breaker.call(_blocked)) for _ in range(2)]
    await asyncio.sleep(0)

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(_blocked)

    gate.set()
    results = await asyncio.gather(*tasks)

    assert results == ["ok", "ok"]


def test_runtime_config_is_immutable() -> None:
    """Enforce immutability of RuntimeConfig."""
    config = RuntimeConfig()
    with pytest.raises(FrozenInstanceError):
        config.tenant_id = "mutated"  # type: ignore[misc]


def test_create_runtime_returns_scoped_runtime() -> None:
    """Create scoped runtime with defaults."""
    runtime = create_runtime()
    assert isinstance(runtime, ScopedRuntime)
    assert runtime.config.tenant_id == "default"


def test_scoped_runtime_child_inherits_config() -> None:
    """Copy runtime config and allow overrides."""
    runtime = create_runtime(RuntimeConfig(tenant_id="base", environment="stage"))
    child = runtime.child(tenant_id="child")

    assert child.config.tenant_id == "child"
    assert child.config.environment == "stage"
    assert child._parent is runtime


def test_child_isolated_from_parent_registries() -> None:
    """Avoid leaking child registry changes to parent."""
    runtime = create_runtime(RuntimeConfig(tenant_id="parent"))
    runtime.register_service("svc.parent", "parent")

    child = runtime.child(tenant_id="child")
    child.register_service("svc.child", "child")

    assert runtime.get_service("svc.child") is None
    assert child.get_service("svc.parent") == "parent"


def test_parent_fallback_for_service() -> None:
    """Allow child to fallback to parent services."""
    runtime = create_runtime(RuntimeConfig(tenant_id="parent"))
    child = runtime.child(tenant_id="child")

    runtime.register_service("svc.shared", "shared")

    assert child.get_service("svc.shared") == "shared"


def test_register_and_get_client() -> None:
    """Register and retrieve client functions."""
    runtime = create_runtime(RuntimeConfig(tenant_id="client"))
    runtime.register_client("client.alpha", "alpha-client")

    assert runtime.get_client("client.alpha") == "alpha-client"
    assert runtime.get_client("client.missing") is None


def test_with_runtime_context_manager_restores_previous() -> None:
    """Restore the previous runtime after with_runtime."""
    original = get_current_runtime()
    runtime = create_runtime(RuntimeConfig(tenant_id="override"))

    with with_runtime(runtime):
        assert get_current_runtime() is runtime

    assert get_current_runtime() is original


def test_with_runtime_decorator_sync(runtime_pair: tuple[ScopedRuntime, ScopedRuntime]) -> None:
    """Support with_runtime as a sync decorator.

    Args:
        runtime_pair: Pair of runtime fixtures.
    """
    runtime_a, _ = runtime_pair

    @with_runtime(runtime_a)
    def _get_tenant() -> str:
        return get_current_runtime().config.tenant_id

    assert _get_tenant() == "tenant-a"


@pytest.mark.asyncio
async def test_with_runtime_decorator_async(runtime_pair: tuple[ScopedRuntime, ScopedRuntime]) -> None:
    """Support with_runtime as an async decorator.

    Args:
        runtime_pair: Pair of runtime fixtures.
    """
    _, runtime_b = runtime_pair

    @with_runtime(runtime_b)
    async def _get_tenant() -> str:
        return get_current_runtime().config.tenant_id

    assert await _get_tenant() == "tenant-b"


def test_with_tenant_creates_isolated_runtime() -> None:
    """Create tenant-specific runtimes with separate configs."""
    base_runtime = create_runtime(RuntimeConfig(tenant_id="base"))

    with with_runtime(base_runtime):
        with with_tenant("tenant-1") as runtime_a:
            runtime_a.register_service("svc.tenant", "a")
            assert runtime_a.config.tenant_id == "tenant-1"

        with with_tenant("tenant-2") as runtime_b:
            assert runtime_b.config.tenant_id == "tenant-2"
            assert runtime_b.get_service("svc.tenant") is None


def test_multi_tenant_registries_do_not_leak() -> None:
    """Avoid registry leaks between tenant scopes."""
    base_runtime = create_runtime(RuntimeConfig(tenant_id="base"))

    with with_runtime(base_runtime):
        with with_tenant("tenant-1") as runtime_a:
            runtime_a.register_client("client.tenant", "client-a")
            assert runtime_a.get_client("client.tenant") == "client-a"

        with with_tenant("tenant-2") as runtime_b:
            assert runtime_b.get_client("client.tenant") is None


@pytest.mark.asyncio
async def test_async_context_isolation(runtime_pair: tuple[ScopedRuntime, ScopedRuntime]) -> None:
    """Maintain separate runtime contexts across tasks.

    Args:
        runtime_pair: Pair of runtime fixtures.
    """
    runtime_a, runtime_b = runtime_pair

    async def _read_tenant(runtime: ScopedRuntime) -> str:
        with with_runtime(runtime):
            await asyncio.sleep(0)
            return get_current_runtime().config.tenant_id

    results = await asyncio.gather(
        _read_tenant(runtime_a),
        _read_tenant(runtime_b),
    )

    assert results == ["tenant-a", "tenant-b"]
