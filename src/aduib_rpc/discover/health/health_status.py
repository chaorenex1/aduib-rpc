from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from enum import StrEnum


class HealthStatus(StrEnum):
    """Health states for service instances."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

    @classmethod
    def to_health_status(cls, status: str) -> HealthStatus:
        for health_status in cls:
            if health_status.value == status:
                return health_status
        return HealthStatus.UNKNOWN


@dataclass
class HealthCheckResult:
    """Represents the outcome of a health check."""

    status: HealthStatus
    latency_ms: float
    message: str | None = None
    checked_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class HealthCheckConfig:
    """Configuration for periodic health checks."""

    interval_seconds: float = 10.0
    timeout_seconds: float = 5.0
    healthy_threshold: int = 2
    unhealthy_threshold: int = 3
    path: str = "/health"
