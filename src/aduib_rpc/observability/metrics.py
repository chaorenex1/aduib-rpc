from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import threading

__all__ = [
    "MetricLabels",
    "Metric",
    "Counter",
    "Histogram",
    "Gauge",
    "RpcMetrics",
]


@dataclass
class MetricLabels:
    service: str = ""
    method: str = ""
    status: str = ""
    error_code: str = ""


class Metric(ABC):

    @abstractmethod
    async def record(self, value: float, labels: MetricLabels) -> None:
        raise NotImplementedError


class Counter(Metric):

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[str, str, str, str], float] = {}
        self._lock = threading.Lock()

    async def record(self, value: float, labels: MetricLabels) -> None:
        key = (labels.service, labels.method, labels.status, labels.error_code)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + value

    async def inc(self, labels: MetricLabels) -> None:
        await self.record(1.0, labels)

    def get(self) -> dict[tuple[str, str, str, str], float]:
        with self._lock:
            return dict(self._values)


class Histogram(Metric):

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

    def __init__(
        self,
        name: str,
        description: str,
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._observations: dict[tuple[str, str, str], list[float]] = {}
        self._lock = threading.Lock()

    async def record(self, value: float, labels: MetricLabels) -> None:
        key = (labels.service, labels.method, labels.status)
        with self._lock:
            observations = self._observations.get(key)
            if observations is None:
                observations = []
                self._observations[key] = observations
            observations.append(value)

    async def get_percentile(self, labels: MetricLabels, percentile: float) -> float:
        key = (labels.service, labels.method, labels.status)
        with self._lock:
            observations = list(self._observations.get(key, []))
        if not observations:
            return 0.0
        observations.sort()
        if percentile < 0:
            percentile = 0.0
        elif percentile > 100:
            percentile = 100.0
        index = int(len(observations) * percentile / 100)
        if index >= len(observations):
            index = len(observations) - 1
        return observations[index]


class Gauge(Metric):

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    async def record(self, value: float, labels: MetricLabels) -> None:
        key = (labels.service, labels.method)
        with self._lock:
            self._values[key] = value

    async def set(self, value: float, labels: MetricLabels) -> None:
        await self.record(value, labels)

    async def inc(self, labels: MetricLabels, delta: float = 1.0) -> None:
        key = (labels.service, labels.method)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + delta

    async def dec(self, labels: MetricLabels, delta: float = 1.0) -> None:
        await self.inc(labels, -delta)


class RpcMetrics:

    request_total = Counter(
        "aduib_rpc_requests_total",
        "Total number of RPC requests",
    )
    request_duration = Histogram(
        "aduib_rpc_request_duration_seconds",
        "RPC request duration in seconds",
    )
    request_size = Histogram(
        "aduib_rpc_request_size_bytes",
        "RPC request size in bytes",
        buckets=(100, 1000, 10000, 100000, 1000000),
    )
    response_size = Histogram(
        "aduib_rpc_response_size_bytes",
        "RPC response size in bytes",
        buckets=(100, 1000, 10000, 100000, 1000000),
    )
    active_requests = Gauge(
        "aduib_rpc_active_requests",
        "Number of active RPC requests",
    )
    circuit_breaker_state = Gauge(
        "aduib_rpc_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    )

    @classmethod
    async def record_request(
        cls,
        service: str,
        method: str,
        status: str,
        duration_seconds: float,
        request_size: int = 0,
        response_size: int = 0,
        error_code: str = "",
    ) -> None:
        labels = MetricLabels(
            service=service,
            method=method,
            status=status,
            error_code=error_code,
        )
        await cls.request_total.inc(labels)
        await cls.request_duration.record(duration_seconds, labels)
        if request_size:
            await cls.request_size.record(float(request_size), labels)
        if response_size:
            await cls.response_size.record(float(response_size), labels)
