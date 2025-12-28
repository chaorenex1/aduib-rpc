from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from aduib_rpc.client.call_options import RetryOptions

_T = TypeVar("_T")


def _sleep_s(attempt: int, *, backoff_ms: int, max_backoff_ms: int, jitter: float) -> float:
    base = min(max_backoff_ms, backoff_ms * (2 ** max(0, attempt - 1)))
    # jitter in [-(j*base), +(j*base)]
    delta = (random.random() * 2 - 1) * (jitter * base)
    return max(0.0, (base + delta) / 1000.0)


def _should_retry_http(exc: Exception) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # common retryable statuses
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}
    if isinstance(exc, httpx.RequestError):
        return True
    return False


async def retry_async(
    op: Callable[[], Awaitable[_T]],
    *,
    retry: RetryOptions,
    idempotent: bool,
) -> _T:
    if not retry.enabled:
        return await op()
    if retry.idempotent_required and not idempotent:
        return await op()

    last_exc: Exception | None = None
    for attempt in range(1, retry.max_attempts + 1):
        try:
            return await op()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if not _should_retry_http(e):
                raise
            if attempt >= retry.max_attempts:
                raise
            await asyncio.sleep(_sleep_s(attempt, backoff_ms=retry.backoff_ms, max_backoff_ms=retry.max_backoff_ms, jitter=retry.jitter))

    assert last_exc is not None
    raise last_exc
