from __future__ import annotations

from typing import Any, Awaitable, Callable

import anyio


def run(coro_fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    """Run an async callable from sync code.

    This is a small wrapper around anyio.run/anyio.from_thread.run.

    It avoids calling anyio.run() from an existing event loop and provides
    a single place to adapt behavior across environments.
    """

    try:
        return anyio.run(coro_fn, *args, **kwargs)
    except RuntimeError as e:
        if "anyio.run() cannot be called from a running event loop" in str(e):
            return anyio.from_thread.run(coro_fn, *args, **kwargs)
        raise

