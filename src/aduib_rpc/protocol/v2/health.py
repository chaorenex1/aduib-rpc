"""Health check models for Aduib RPC protocol v2."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class HealthStatus(StrEnum):
    """Health status values for services in protocol v2.

    Attributes:
        HEALTHY: Service is operating normally.
        UNHEALTHY: Service is not operating correctly.
        DEGRADED: Service is operating with reduced functionality.
        UNKNOWN: Health status cannot be determined.
    """

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

    @classmethod
    def from_proto(cls, value: Any) -> "HealthStatus":
        return cls._from_wire(value)

    @classmethod
    def from_thrift(cls, value: Any) -> "HealthStatus":
        return cls._from_wire(value)

    @classmethod
    def _from_wire(cls, value: Any) -> "HealthStatus":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.UNKNOWN
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "healthy":
                return cls.HEALTHY
            if key == "unhealthy":
                return cls.UNHEALTHY
            if key == "degraded":
                return cls.DEGRADED
            if key == "unknown":
                return cls.UNKNOWN
            try:
                raw = int(raw)
            except Exception:
                return cls.UNKNOWN
        try:
            num = int(raw)
        except Exception:
            return cls.UNKNOWN
        if num == 1:
            return cls.HEALTHY
        if num == 2:
            return cls.UNHEALTHY
        if num == 3:
            return cls.DEGRADED
        if num == 4:
            return cls.UNKNOWN
        return cls.UNKNOWN

    @classmethod
    def to_proto(cls, value: "HealthStatus | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def to_thrift(cls, value: "HealthStatus | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def _to_wire(cls, value: "HealthStatus | str | int | None") -> int:
        if value is None:
            return 4
        if isinstance(value, cls):
            if value == cls.HEALTHY:
                return 1
            if value == cls.UNHEALTHY:
                return 2
            if value == cls.DEGRADED:
                return 3
            if value == cls.UNKNOWN:
                return 4
            return 4
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "healthy":
                return 1
            if key == "unhealthy":
                return 2
            if key == "degraded":
                return 3
            if key == "unknown":
                return 4
            try:
                raw = int(raw)
            except Exception:
                return 4
        try:
            num = int(raw)
        except Exception:
            return 4
        if 0 <= num <= 4:
            return num
        return 4


class HealthCheckRequest(BaseModel):
    """Request payload for a health check.

    Attributes:
        service: Optional service name to query. None means overall status.
    """

    service: str = None


class HealthCheckResponse(BaseModel):
    """Response payload for a health check.

    Attributes:
        status: Overall health status for the service or system.
        services: Optional per-service status map.
    """

    status: HealthStatus = HealthStatus.UNKNOWN
    services: dict[str, HealthStatus] | None = None
