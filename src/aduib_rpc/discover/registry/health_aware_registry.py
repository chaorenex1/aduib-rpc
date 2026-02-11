from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, cast

from aduib_rpc.discover import HealthChecker
from aduib_rpc.discover.entities.service_instance import ServiceInstance

from aduib_rpc.discover.health.health_status import HealthCheckConfig, HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


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
        *,
        allow_unhealthy_fallback: bool = True,
    ):
        self._base_registry = base_registry
        self._checker = checker
        self._config = config
        self._allow_unhealthy_fallback = allow_unhealthy_fallback
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

    async def register_service(self, service_info: ServiceInstance) -> None:
        """Register a service via the underlying registry."""
        if hasattr(self._base_registry, "register_service"):
            result = self._base_registry.register_service(service_info)
            if inspect.isawaitable(result):
                await result

    async def unregister_service(self, service_name: str) -> None:
        """Unregister a service via the underlying registry."""
        if hasattr(self._base_registry, "unregister_service"):
            result = self._base_registry.unregister_service(service_name)
            if inspect.isawaitable(result):
                await result

    async def list_instances(self, service_name: str) -> list[ServiceInstance]:
        """List instances (healthy preferred) for the given service."""
        return await self.list_healthy_instances(service_name)

    async def discover_service(self, service_name: str) -> ServiceInstance | None:
        """Return a single healthy instance (best-effort)."""
        instances = await self.list_healthy_instances(service_name)
        return instances[0] if instances else None

    async def list_healthy_instances(self, service_name: str) -> list[ServiceInstance]:
        """List healthy instances for the given service."""
        all_instances = []
        if hasattr(self._base_registry, "list_instances"):
            result = self._base_registry.list_instances(service_name)
            if inspect.isawaitable(result):
                all_instances = await result
            else:
                all_instances = result
        all_instances = list(all_instances or [])
        healthy_instances: list[ServiceInstance] = []

        for instance in all_instances:
            key = f"{instance.host}:{instance.port}"
            health_instance = self._health_cache.get(key)
            if health_instance is None:
                healthy_instances.append(instance)
                continue
            if health_instance.status == HealthStatus.HEALTHY:
                healthy_instances.append(instance)
                continue
            if (
                health_instance.status == HealthStatus.UNKNOWN
                and health_instance.last_check is not None
                and health_instance.last_check.status == HealthStatus.HEALTHY
            ):
                healthy_instances.append(instance)

        if healthy_instances:
            return healthy_instances
        if self._allow_unhealthy_fallback:
            return list(all_instances)
        return []

    async def _health_check_loop(self) -> None:
        """Background loop for health checking."""
        while True:
            try:
                service_names = await self._get_all_service_names()
                logger.debug(f"Health check loop: checking services {service_names}")
                for service_name in service_names:
                    result = self._base_registry.list_instances(service_name)
                    instances = await result if inspect.isawaitable(result) else result
                    for instance in instances or []:
                        await self._check_instance(instance)
                await asyncio.sleep(self._config.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _check_instance(self, instance: ServiceInstance) -> None:
        """Check a single service instance."""
        key = f"{instance.host}:{instance.port}"

        checker_dict = getattr(self._checker, "__dict__", {})
        if isinstance(self._checker, HealthChecker):
            check_attr = self._checker.check
        elif isinstance(checker_dict, dict) and "check" in checker_dict and callable(checker_dict["check"]):
            check_attr = checker_dict["check"]
        elif callable(self._checker):
            check_attr = self._checker  # type: ignore[assignment]
        else:
            check_attr = getattr(self._checker, "check", None)
            if not callable(check_attr):
                raise TypeError("Health checker must be async callable or implement check().")

        check_fn = cast(Callable[[ServiceInstance], Awaitable[HealthCheckResult]], check_attr)
        result = await check_fn(instance)

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

    async def _get_all_service_names(self) -> list[str]:
        """Return all registered service names (registry-specific)."""
        from aduib_rpc.server import get_service_info

        return [get_service_info().service_name]
