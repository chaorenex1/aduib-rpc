from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable

from .registry.service_registry import ServiceRegistry

__all__ = [
    "RegistryAdapter",
    "MultiRegistry",
    "RegistryHealthChecker",
]

logger = logging.getLogger(__name__)


@dataclass
class RegistryAdapter:
    name: str
    registry: ServiceRegistry
    priority: int = 0
    enabled: bool = True


class MultiRegistry(ServiceRegistry):
    def __init__(self, adapters: list[RegistryAdapter]):
        self._adapters = list(adapters)

    async def register(self, instance) -> None:
        await self._register_all(instance)

    async def deregister(self, service_name, instance_id) -> None:
        await self._deregister_all(service_name, instance_id)

    async def list_instances(self, service_name) -> list:
        adapters = self._get_enabled_adapters()
        instances: list[Any] = []
        seen_ids: set[str] = set()

        for adapter in adapters:
            try:
                adapter_instances = await _maybe_await(
                    adapter.registry.list_instances(service_name)
                )
            except Exception:
                logger.exception(
                    "Failed to list instances from registry '%s'.",
                    adapter.name,
                )
                continue

            if not adapter_instances:
                continue

            for instance in adapter_instances:
                instance_id = getattr(instance, "instance_id", None)
                if instance_id is None:
                    instances.append(instance)
                    continue
                if instance_id in seen_ids:
                    continue
                seen_ids.add(instance_id)
                instances.append(instance)

        return instances

    async def get_all_services(self) -> list[str]:
        adapters = self._get_enabled_adapters()
        services: list[str] = []
        seen: set[str] = set()

        for adapter in adapters:
            getter = getattr(adapter.registry, "get_all_services", None)
            if getter is None:
                continue
            try:
                adapter_services = await _maybe_await(getter())
            except Exception:
                logger.exception(
                    "Failed to list services from registry '%s'.",
                    adapter.name,
                )
                continue
            for service_name in adapter_services or []:
                if service_name in seen:
                    continue
                seen.add(service_name)
                services.append(service_name)

        return services

    def _get_enabled_adapters(self) -> list[RegistryAdapter]:
        return sorted(
            (adapter for adapter in self._adapters if adapter.enabled),
            key=lambda adapter: adapter.priority,
            reverse=True,
        )

    async def _register_all(self, instance) -> None:
        adapters = self._get_enabled_adapters()
        if not adapters:
            return

        results = await asyncio.gather(
            *(self._register_adapter(adapter, instance) for adapter in adapters),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, Exception)]
        for adapter, result in zip(adapters, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Registry '%s' failed to register instance: %s",
                    adapter.name,
                    result,
                )
        if errors and len(errors) == len(results):
            raise errors[0]

    async def _deregister_all(self, service_name, instance_id) -> None:
        adapters = self._get_enabled_adapters()
        if not adapters:
            return

        results = await asyncio.gather(
            *(
                self._deregister_adapter(adapter, service_name, instance_id)
                for adapter in adapters
            ),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, Exception)]
        for adapter, result in zip(adapters, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Registry '%s' failed to deregister instance: %s",
                    adapter.name,
                    result,
                )
        if errors and len(errors) == len(results):
            raise errors[0]

    async def _register_adapter(self, adapter: RegistryAdapter, instance) -> None:
        registry = adapter.registry
        method = getattr(registry, "register", None)
        if method is None:
            method = getattr(registry, "register_service", None)
        if method is None:
            raise NotImplementedError(
                f"Registry '{adapter.name}' does not support register."
            )
        await _maybe_await(method(instance))

    async def _deregister_adapter(
        self,
        adapter: RegistryAdapter,
        service_name,
        instance_id,
    ) -> None:
        registry = adapter.registry
        method = getattr(registry, "deregister", None)
        if method is not None:
            if instance_id is None and _accepts_single_arg(method):
                await _maybe_await(method(service_name))
                return
            await _maybe_await(method(service_name, instance_id))
            return

        method = getattr(registry, "unregister_service", None)
        if method is None:
            raise NotImplementedError(
                f"Registry '{adapter.name}' does not support deregister."
            )

        if instance_id is None and _accepts_single_arg(method):
            method(service_name)
            return
        if _accepts_two_args(method):
            method(service_name, instance_id)
            return

        method(service_name)

    async def register_service(self, service_info) -> None:
        await self.register(service_info)

    def unregister_service(self, service_name: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.deregister(service_name, None))
            return
        loop.create_task(self.deregister(service_name, None))


class RegistryHealthChecker:
    def __init__(
        self,
        adapters: list[RegistryAdapter],
        interval_seconds: float = 10.0,
        failure_threshold: int = 3,
        success_threshold: int = 1,
    ):
        self._adapters = adapters
        self._interval_seconds = interval_seconds
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._health_state: dict[str, dict[str, int]] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)

    async def check_once(self) -> None:
        for adapter in self._adapters:
            healthy = await self._check_adapter(adapter)
            state = self._health_state.setdefault(
                adapter.name,
                {"failures": 0, "successes": 0},
            )
            if healthy:
                state["successes"] += 1
                state["failures"] = 0
                if (
                    not adapter.enabled
                    and state["successes"] >= self._success_threshold
                ):
                    adapter.enabled = True
                    logger.info("Registry '%s' marked healthy.", adapter.name)
            else:
                state["failures"] += 1
                state["successes"] = 0
                if adapter.enabled and state["failures"] >= self._failure_threshold:
                    adapter.enabled = False
                    logger.warning("Registry '%s' marked unhealthy.", adapter.name)

    async def _check_loop(self) -> None:
        while True:
            try:
                await self.check_once()
                await asyncio.sleep(self._interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _check_adapter(self, adapter: RegistryAdapter) -> bool:
        registry = adapter.registry
        for name in ("health_check", "check_health", "is_healthy", "ping"):
            method = getattr(registry, name, None)
            if method is None:
                continue
            try:
                result = await _maybe_await(method())
            except Exception:
                logger.exception(
                    "Health check failed for registry '%s'.",
                    adapter.name,
                )
                return False
            return _as_bool(result)

        fallback = getattr(registry, "get_all_services", None)
        if fallback is None:
            return True
        try:
            await _maybe_await(fallback())
        except Exception:
            logger.exception(
                "Health check failed for registry '%s'.",
                adapter.name,
            )
            return False
        return True


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _accepts_single_arg(method: Callable[..., Any]) -> bool:
    try:
        sig = inspect.signature(method)
    except (TypeError, ValueError):
        return False
    params = list(sig.parameters.values())
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return True
    return len(params) >= 1


def _accepts_two_args(method: Callable[..., Any]) -> bool:
    try:
        sig = inspect.signature(method)
    except (TypeError, ValueError):
        return False
    params = list(sig.parameters.values())
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return True
    return len(params) >= 2


def _as_bool(result: Any) -> bool:
    if isinstance(result, bool):
        return result
    status = getattr(result, "status", None)
    if isinstance(status, bool):
        return status
    return bool(result)
