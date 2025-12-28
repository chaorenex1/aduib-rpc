from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RetryOptions:
    enabled: bool = False
    max_attempts: int = 1
    backoff_ms: int = 200
    max_backoff_ms: int = 2000
    jitter: float = 0.1
    idempotent_required: bool = True


@dataclass(frozen=True, slots=True)
class CallOptions:
    timeout_s: float | None
    retry: RetryOptions


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return False


def resolve_timeout_s(*, config_timeout_s: float | None, meta: dict[str, Any] | None, context_http_kwargs: dict[str, Any] | None) -> float | None:
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


def resolve_retry_options(*, meta: dict[str, Any] | None, defaults: RetryOptions) -> RetryOptions:
    if not meta:
        return defaults

    enabled = _coerce_bool(meta.get("retry_enabled")) if "retry_enabled" in meta else defaults.enabled
    max_attempts = int(meta.get("retry_max_attempts", defaults.max_attempts))
    backoff_ms = int(meta.get("retry_backoff_ms", defaults.backoff_ms))
    max_backoff_ms = int(meta.get("retry_max_backoff_ms", defaults.max_backoff_ms))
    jitter = float(meta.get("retry_jitter", defaults.jitter))

    # Default safe: require idempotent unless explicitly disabled.
    idempotent_required = _coerce_bool(meta.get("retry_require_idempotent")) if "retry_require_idempotent" in meta else defaults.idempotent_required

    # Guard rails
    if max_attempts < 1:
        max_attempts = 1
    if max_attempts > 10:
        max_attempts = 10

    return RetryOptions(
        enabled=enabled,
        max_attempts=max_attempts,
        backoff_ms=max(0, backoff_ms),
        max_backoff_ms=max(0, max_backoff_ms),
        jitter=max(0.0, min(1.0, jitter)),
        idempotent_required=idempotent_required,
    )


def resolve_call_options(*, config_timeout_s: float | None, meta: dict[str, Any] | None, context_http_kwargs: dict[str, Any] | None, retry_defaults: RetryOptions | None = None) -> CallOptions:
    retry_defaults = retry_defaults or RetryOptions()
    timeout_s = resolve_timeout_s(config_timeout_s=config_timeout_s, meta=meta, context_http_kwargs=context_http_kwargs)
    retry = resolve_retry_options(meta=meta, defaults=retry_defaults)
    return CallOptions(timeout_s=timeout_s, retry=retry)

