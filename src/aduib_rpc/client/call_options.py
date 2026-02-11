from __future__ import annotations

from typing import Any


def resolve_timeout_s(
    *,
    config_timeout_s: float | None,
    meta: dict[str, Any] | None,
    context_http_kwargs: dict[str, Any] | None,
) -> float | None:
    # Priority: context.http_kwargs.timeout > meta.timeout_ms/timeout_s > config
    if context_http_kwargs and "timeout" in context_http_kwargs and context_http_kwargs["timeout"] is not None:
        t = context_http_kwargs["timeout"]
        try:
            return float(t)
        except Exception:
            return config_timeout_s

    if meta:
        if meta.get("timeout_ms") is not None:
            try:
                return float(meta["timeout_ms"]) / 1000.0
            except Exception:
                return config_timeout_s
        if meta.get("timeout_s") is not None:
            try:
                return float(meta["timeout_s"])
            except Exception:
                return config_timeout_s

    return config_timeout_s

