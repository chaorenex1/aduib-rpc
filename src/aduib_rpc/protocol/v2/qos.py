"""QoS configuration types for Aduib RPC protocol v2."""

from __future__ import annotations

import dataclasses
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, field_validator

from aduib_rpc.resilience import RetryPolicy


class Priority(IntEnum):
    """Priority levels used for request scheduling."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

    @classmethod
    def from_proto(cls, value: Any) -> "Priority":
        return cls._from_wire(value)

    @classmethod
    def from_thrift(cls, value: Any) -> "Priority":
        return cls._from_wire(value)

    @classmethod
    def _from_wire(cls, value: Any) -> "Priority":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.NORMAL
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "low":
                return cls.LOW
            if key == "normal":
                return cls.NORMAL
            if key == "high":
                return cls.HIGH
            if key == "critical":
                return cls.CRITICAL
            try:
                raw = int(raw)
            except Exception:
                return cls.NORMAL
        try:
            num = int(raw)
        except Exception:
            return cls.NORMAL
        if num == 1:
            return cls.LOW
        if num == 2:
            return cls.NORMAL
        if num == 3:
            return cls.HIGH
        if num >= 4:
            return cls.CRITICAL
        return cls.NORMAL

    @classmethod
    def to_proto(cls, value: "Priority | int | str | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def to_thrift(cls, value: "Priority | int | str | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def _to_wire(cls, value: "Priority | int | str | None") -> int:
        if value is None:
            return 0
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "low":
                return 1
            if key == "normal":
                return 2
            if key == "high":
                return 3
            if key == "critical":
                return 4
            try:
                raw = int(raw)
            except Exception:
                return 0
        try:
            num = int(raw)
        except Exception:
            return 0
        if num <= 0:
            return 1
        if num == 1:
            return 2
        if num == 2:
            return 3
        return 4

from dataclasses import dataclass
@dataclass
class QosConfig:
    """Quality of service configuration for an RPC request.

    Attributes:
        priority: Scheduling priority for the request.
        timeout_ms: Timeout in milliseconds. None means no timeout.
        retry: Optional retry configuration.
        idempotency_key: Optional idempotency key for deduplication.
    """
    enabled: bool = False
    priority: Priority = Priority.NORMAL
    timeout_ms: int = 60000
    idempotency_ttl_s: int = 300
    retry: RetryPolicy | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.retry, dict):
            self.retry = RetryPolicy(**self.retry)
