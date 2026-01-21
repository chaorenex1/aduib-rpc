"""QoS configuration types for Aduib RPC protocol v2."""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, ValidationInfo, field_validator


class Priority(IntEnum):
    """Priority levels used for request scheduling."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class RetryConfig(BaseModel):
    """Retry policy configuration using exponential backoff.

    The delay for a given attempt is computed as:
        delay = min(
            initial_delay_ms * (backoff_multiplier ** attempt),
            max_delay_ms,
        )

    Attributes:
        max_attempts: Maximum number of retry attempts.
        initial_delay_ms: Initial delay between retries in milliseconds.
        max_delay_ms: Upper bound for the retry delay in milliseconds.
        backoff_multiplier: Exponential backoff multiplier.
        retryable_codes: Optional list of retryable error codes.
    """

    max_attempts: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 10000
    backoff_multiplier: float = 2.0
    retryable_codes: list[int] | None = None

    @field_validator("max_attempts")
    @classmethod
    def validate_max_attempts(cls, value: int) -> int:
        """Ensure the maximum number of attempts is at least 1."""

        if value < 1:
            raise ValueError("max_attempts must be >= 1")
        return value

    @field_validator("initial_delay_ms")
    @classmethod
    def validate_initial_delay_ms(cls, value: int) -> int:
        """Ensure the initial delay is positive."""

        if value <= 0:
            raise ValueError("initial_delay_ms must be > 0")
        return value

    @field_validator("max_delay_ms")
    @classmethod
    def validate_max_delay_ms(cls, value: int, info: ValidationInfo) -> int:
        """Ensure the maximum delay is not below the initial delay."""

        initial_delay_ms = info.data.get("initial_delay_ms")
        if initial_delay_ms is not None and value < initial_delay_ms:
            raise ValueError("max_delay_ms must be >= initial_delay_ms")
        return value

    @field_validator("backoff_multiplier")
    @classmethod
    def validate_backoff_multiplier(cls, value: float) -> float:
        """Ensure the backoff multiplier is at least 1.0."""

        if value < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        return value


class QosConfig(BaseModel):
    """Quality of service configuration for an RPC request.

    Attributes:
        priority: Scheduling priority for the request.
        timeout_ms: Timeout in milliseconds. None means no timeout.
        retry: Optional retry configuration.
        idempotency_key: Optional idempotency key for deduplication.
    """

    priority: Priority = Priority.NORMAL
    timeout_ms: int | None = None
    retry: RetryConfig | None = None
    idempotency_key: str | None = None

    @field_validator("timeout_ms")
    @classmethod
    def validate_timeout_ms(cls, value: int | None) -> int | None:
        """Ensure timeout is positive when provided."""

        if value is not None and value <= 0:
            raise ValueError("timeout_ms must be > 0 when provided")
        return value


__all__ = ["Priority", "RetryConfig", "QosConfig"]
