from __future__ import annotations

import time
from abc import ABC, abstractmethod

from aduib_rpc.discover.entities.service_instance import ServiceInstance

from .health_status import HealthCheckConfig, HealthCheckResult, HealthStatus

__all__ = [
    "HealthChecker",
    "HttpHealthChecker",
    "GrpcHealthChecker",
]


class HealthChecker(ABC):
    """Base interface for health check implementations."""

    @abstractmethod
    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        """Run a health check against the given instance."""
        raise NotImplementedError


class HttpHealthChecker(HealthChecker):
    """HTTP-based health checker."""

    def __init__(self, config: HealthCheckConfig):
        self._config = config
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import httpx

            timeout = getattr(self._config, "timeout", self._config.timeout_seconds)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        start = time.monotonic()
        try:
            client = await self._get_client()
            url = f"{instance.scheme}://{instance.host}:{instance.port}{self._config.path}"
            response = await client.get(url)
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code == 200:
                return HealthCheckResult(HealthStatus.HEALTHY, latency_ms)
            if response.status_code == 503:
                return HealthCheckResult(
                    HealthStatus.DEGRADED,
                    latency_ms,
                    "Service degraded",
                )
            return HealthCheckResult(
                HealthStatus.UNHEALTHY,
                latency_ms,
                f"HTTP {response.status_code}",
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                HealthStatus.UNHEALTHY,
                latency_ms,
                str(exc),
            )


class GrpcHealthChecker(HealthChecker):
    """gRPC health checker using the standard health service."""

    def __init__(self, config: HealthCheckConfig):
        self._config = config

    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        start = time.monotonic()
        channel = None
        try:
            import grpc
            from grpc.health.v1 import health_pb2, health_pb2_grpc

            channel = grpc.aio.insecure_channel(f"{instance.host}:{instance.port}")
            stub = health_pb2_grpc.HealthStub(channel)
            timeout = getattr(self._config, "timeout", self._config.timeout_seconds)
            response = await stub.Check(
                health_pb2.HealthCheckRequest(),
                timeout=timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.status == health_pb2.HealthCheckResponse.SERVING:
                return HealthCheckResult(HealthStatus.HEALTHY, latency_ms)
            return HealthCheckResult(
                HealthStatus.UNHEALTHY,
                latency_ms,
                f"Status: {response.status}",
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                HealthStatus.UNHEALTHY,
                latency_ms,
                str(exc),
            )
        finally:
            if channel is not None:
                await channel.close()
