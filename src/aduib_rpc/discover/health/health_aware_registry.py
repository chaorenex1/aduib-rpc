from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aduib_rpc.discover.entities.service_instance import ServiceInstance

from .health_checker import HealthChecker
from .health_status import HealthCheckConfig, HealthCheckResult, HealthStatus

__all__ = [
    "HealthAwareServiceInstance",
    "HealthAwareRegistry",
]


@dataclass
class HealthAwareServiceInstance:
    """Service instance with health tracking state."""

    instance: ServiceInstance
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: HealthCheckResult | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class HealthAwareRegistry:
    """Health-aware registry wrapper with periodic checks."""

    def __init__(
        self,
        base_registry,
        checker: HealthChecker,
        config: HealthCheckConfig,
    ):
        self._base_registry = base_registry
        self._checker = checker
        self._config = config
        self._health_cache: dict[str, HealthAwareServiceInstance] = {}
        self._check_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the health check loop."""
        self._check_task = asyncio.create_task(self._health_check_loop())

    async def stop(self) -> None:
        """Stop the health check loop."""
        if self._check_task:
            self._check_task.cancel()
            await asyncio.gather(self._check_task, return_exceptions=True)

    def list_healthy_instances(self, service_name: str) -> list[ServiceInstance]:
        """List healthy instances for the given service."""
        all_instances = self._base_registry.list_instances(service_name)
        healthy_instances: list[ServiceInstance] = []

        for instance in all_instances:
            key = f"{instance.host}:{instance.port}"
            health_instance = self._health_cache.get(key)
            if health_instance is None or health_instance.status == HealthStatus.HEALTHY:
                healthy_instances.append(instance)

        return healthy_instances

    async def _health_check_loop(self) -> None:
        """Background loop for health checking."""
        while True:
            try:
                for service_name in self._get_all_service_names():
                    instances = self._base_registry.list_instances(service_name)
                    for instance in instances:
                        await self._check_instance(instance)
                await asyncio.sleep(self._config.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _check_instance(self, instance: ServiceInstance) -> None:
        """Check a single service instance."""
        key = f"{instance.host}:{instance.port}"
        result = await self._checker.check(instance)

        if key not in self._health_cache:
            self._health_cache[key] = HealthAwareServiceInstance(instance=instance)

        health_instance = self._health_cache[key]
        health_instance.last_check = result

        if result.status == HealthStatus.HEALTHY:
            health_instance.consecutive_successes += 1
            health_instance.consecutive_failures = 0
            if health_instance.consecutive_successes >= self._config.healthy_threshold:
                health_instance.status = HealthStatus.HEALTHY
        else:
            health_instance.consecutive_failures += 1
            health_instance.consecutive_successes = 0
            if health_instance.consecutive_failures >= self._config.unhealthy_threshold:
                health_instance.status = HealthStatus.UNHEALTHY

    def _get_all_service_names(self) -> list[str]:
        """Return all registered service names (registry-specific)."""
        return []
