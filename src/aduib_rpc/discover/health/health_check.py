from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from aduib_rpc.discover.entities.service_instance import ServiceInstance
from aduib_rpc.discover.health.health_status import HealthCheckResult, HealthStatus
from aduib_rpc.protocol.v2.health import HealthCheckRequest
from aduib_rpc.utils.constant import TransportSchemes

if TYPE_CHECKING:
    from aduib_rpc.config import AduibRpcConfig
    from aduib_rpc.client.client_factory import AduibRpcClientFactory

logger = logging.getLogger(__name__)


class HealthChecker(ABC):
    """Base interface for health check implementations."""

    @abstractmethod
    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        """Run a health check against the given instance."""
        raise NotImplementedError


class DefaultHealthChecker(HealthChecker):
    """Default health checker that calls the remote HealthService Check."""

    def __init__(
        self,
        *,
        config: AduibRpcConfig,
        interceptors: list[Any] | None = None,
        client_factory: "AduibRpcClientFactory | None" = None,
    ) -> None:
        self._config = config
        self._interceptors = interceptors
        self._client_factory = client_factory
        self._client_cache: dict[str, object] = {}

    def _get_client(self, instance: ServiceInstance):
        key = getattr(instance, "instance_id", None) or instance.url
        cached = self._client_cache.get(key)
        if cached is not None:
            return cached
        interceptors = self._interceptors
        if interceptors is None:
            from aduib_rpc.server import get_runtime

            interceptors = get_runtime().interceptors
        try:
            client = self._client_factory.create(
                instance.url,
                server_preferred=instance.scheme,
                interceptors=interceptors,
            )
        except Exception:
            if instance.scheme in {TransportSchemes.GRPC, TransportSchemes.GRPCS}:
                from aduib_rpc.client.client_factory import AduibRpcClientFactory

                client = AduibRpcClientFactory.create_client(
                    instance.url,
                    server_preferred=TransportSchemes.GRPC,
                    interceptors=interceptors,
                )
            else:
                raise
        self._client_cache[key] = client
        return client

    async def check(self, instance: ServiceInstance) -> HealthCheckResult:
        start = time.monotonic()
        try:
            client = self._get_client(instance)
            request = (
                HealthCheckRequest(service=instance.service_name) if instance.service_name else HealthCheckRequest()
            )
            payload = await client.health_check(request)
            if isinstance(payload, dict):
                raw_status = payload.get("status")
            else:
                raw_status = getattr(payload, "status", None)
            raw_value = getattr(raw_status, "value", raw_status)
            value = str(raw_value).lower() if raw_value is not None else ""
            status = HealthStatus.to_health_status(value)
            latency_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "Health check for %s: status=%s, latency=%.6fms",
                instance.url,
                status,
                latency_ms,
            )
            return HealthCheckResult(status=status, latency_ms=latency_ms)
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=str(exc),
            )
