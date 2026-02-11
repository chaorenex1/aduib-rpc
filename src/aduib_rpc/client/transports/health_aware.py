from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from aduib_rpc.utils.constant import LoadBalancePolicy
from aduib_rpc.client import ClientConfig, ClientRequestInterceptor
from aduib_rpc.client.midwares import ClientContext
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.discover.entities import ServiceInstance

from aduib_rpc.discover.load_balance import LoadBalancer, LoadBalancerFactory
from aduib_rpc.types import AduibRpcRequest, AduibRpcResponse
from aduib_rpc.server.tasks import (
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEvent,
    TaskQueryRequest,
    TaskQueryResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskSubscribeRequest,
)
from aduib_rpc.server.rpc_execution.method_registry import MethodName
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthCheckResponse
from aduib_rpc.discover.health import (
    HealthCheckConfig,
    HealthCheckResult,
    HealthChecker,
    HealthStatus,
)
from aduib_rpc.discover.registry.health_aware_registry import HealthAwareRegistry, HealthAwareServiceInstance

TransportProducer = Callable[
    [str, ClientConfig, list[ClientRequestInterceptor]],
    ClientTransport,
]

TransportFactory = Callable[[str], ClientTransport]

logger = logging.getLogger(__name__)


class HealthAwareClientTransport(ClientTransport):
    """Health-aware client transport that selects healthy instances per request."""

    def __init__(
        self,
        base_transport_factory: TransportFactory,
        *,
        default_url: str | None = None,
        instances: list[ServiceInstance] | None = None,
        registry: object | None = None,
        health_registry: HealthAwareRegistry | None = None,
        health_checker: HealthChecker | Callable[[ServiceInstance], Awaitable[HealthCheckResult]] | None = None,
        health_config: HealthCheckConfig | None = None,
        cache_ttl_s: float | None = None,
        load_balancer: LoadBalancer | None = None,
        lb_policy: LoadBalancePolicy | None = None,
        lb_key: str | None = None,
        allow_unhealthy_fallback: bool = True,
    ) -> None:
        self._transport_factory = base_transport_factory
        self._default_url = default_url
        self._instances = list(instances) if instances else None
        self._registry = registry
        self._health_registry = health_registry
        self._health_checker = health_checker
        self._health_config = health_config or getattr(health_registry, "_config", None) or HealthCheckConfig()
        self._cache_ttl_ms = int((cache_ttl_s or self._health_config.interval_seconds) * 1000)
        self._allow_unhealthy_fallback = allow_unhealthy_fallback
        self._load_balancer = load_balancer
        self._lb_key = lb_key
        if self._load_balancer is None and lb_policy is not None:
            self._load_balancer = LoadBalancerFactory.get_load_balancer(lb_policy)

        self._health_cache: dict[str, HealthAwareServiceInstance] = {}
        self._transport_cache: dict[str, ClientTransport] = {}
        self._transport_lock = asyncio.Lock()

    @classmethod
    def wrap_transport_producer(
        cls,
        base_producer: TransportProducer,
        *,
        instances: list[ServiceInstance] | None = None,
        registry: object | None = None,
        health_registry: HealthAwareRegistry | None = None,
        health_checker: HealthChecker | Callable[[ServiceInstance], Awaitable[HealthCheckResult]] | None = None,
        health_config: HealthCheckConfig | None = None,
        cache_ttl_s: float | None = None,
        load_balancer: LoadBalancer | None = None,
        lb_policy: LoadBalancePolicy | None = None,
        lb_key: str | None = None,
        allow_unhealthy_fallback: bool = True,
    ) -> TransportProducer:
        """Return a transport producer that wraps another producer with health checks."""

        def _producer(url: str, config: ClientConfig, interceptors: list[ClientRequestInterceptor]) -> ClientTransport:
            return cls(
                lambda target_url: base_producer(target_url, config, interceptors),
                default_url=url,
                instances=instances,
                registry=registry,
                health_registry=health_registry,
                health_checker=health_checker,
                health_config=health_config,
                cache_ttl_s=cache_ttl_s,
                load_balancer=load_balancer,
                lb_policy=lb_policy,
                lb_key=lb_key,
                allow_unhealthy_fallback=allow_unhealthy_fallback,
            )

        return _producer

    async def completion(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        transport = await self._select_transport(request, context)
        return await transport.completion(request, context=context)

    async def call(self, request: AduibRpcRequest, *, context: ClientContext) -> AduibRpcResponse:
        transport = await self._select_transport(request, context)
        return await transport.call(request, context=context)

    async def completion_stream(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        transport = await self._select_transport(request, context)
        async for response in transport.completion_stream(request, context=context):
            yield response

    async def call_client_stream(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> AduibRpcResponse:
        iterator = requests.__aiter__()
        try:
            first = await iterator.__anext__()
        except StopAsyncIteration:
            raise ValueError("request stream is empty")

        async def _replay():
            yield first
            async for item in iterator:
                yield item

        transport = await self._select_transport(first, context)
        return await transport.call_client_stream(_replay(), context=context)

    async def call_bidirectional(
        self,
        requests,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        iterator = requests.__aiter__()
        try:
            first = await iterator.__anext__()
        except StopAsyncIteration:
            raise ValueError("request stream is empty")

        async def _replay():
            yield first
            async for item in iterator:
                yield item

        transport = await self._select_transport(first, context)
        async for response in transport.call_bidirectional(_replay(), context=context):
            yield response

    async def call_server_stream(
        self,
        request: AduibRpcRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[AduibRpcResponse, None]:
        transport = await self._select_transport(request, context)
        async for response in transport.call_server_stream(request, context=context):
            yield response

    async def health_check(self, request: HealthCheckRequest, *, context: ClientContext) -> HealthCheckResponse:
        service_name = None
        health_req = None
        if isinstance(request, HealthCheckRequest):
            health_req = request
            service_name = request.service
        elif isinstance(request, dict):
            health_req = HealthCheckRequest.model_validate(request)
            service_name = health_req.service
        elif request is not None:
            health_req = HealthCheckRequest.model_validate(request)
            service_name = getattr(request, "service", None)
        transport = await self._select_transport_for_service(service_name)
        return await transport.health_check(health_req, context=context)

    async def health_watch(
        self,
        request: HealthCheckRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[HealthCheckResponse, None]:
        service_name = None
        health_req = None
        if isinstance(request, HealthCheckRequest):
            health_req = request
            service_name = request.service
        elif isinstance(request, dict):
            health_req = HealthCheckRequest.model_validate(request)
            service_name = health_req.service
        elif request is not None:
            health_req = HealthCheckRequest.model_validate(request)
            service_name = getattr(request, "service", None)
        transport = await self._select_transport_for_service(service_name)
        async for item in transport.health_watch(health_req, context=context):
            yield item

    async def task_submit(
        self,
        request: TaskSubmitRequest,
        *,
        context: ClientContext,
    ) -> TaskSubmitResponse:
        submit = request if isinstance(request, TaskSubmitRequest) else TaskSubmitRequest.model_validate(request)
        try:
            parsed = MethodName.parse_compat(str(submit.target_method))
            service_name = parsed.service
        except Exception:
            service_name = None
        transport = await self._select_transport_for_service(service_name)
        return await transport.task_submit(submit, context=context)

    async def task_query(
        self,
        request: TaskQueryRequest,
        *,
        context: ClientContext,
    ) -> TaskQueryResponse:
        service_name = _service_name_from_task_request(request)
        transport = await self._select_transport_for_service(service_name)
        return await transport.task_query(request, context=context)

    async def task_cancel(
        self,
        request: TaskCancelRequest,
        *,
        context: ClientContext,
    ) -> TaskCancelResponse:
        service_name = _service_name_from_task_request(request)
        transport = await self._select_transport_for_service(service_name)
        return await transport.task_cancel(request, context=context)

    async def task_subscribe(
        self,
        request: TaskSubscribeRequest,
        *,
        context: ClientContext,
    ) -> AsyncGenerator[TaskEvent, None]:
        service_name = _service_name_from_task_request(request)
        transport = await self._select_transport_for_service(service_name)
        async for item in transport.task_subscribe(request, context=context):
            yield item

    async def _select_transport_for_service(self, service_name: str | None) -> ClientTransport:
        instances = await self._list_healthy_instances(service_name)
        if not instances:
            if not self._default_url:
                raise ValueError("No healthy instance available and no default_url configured.")
            return await self._get_transport_for_url(self._default_url, cache_key="__default__")
        if self._load_balancer is not None:
            instance = self._load_balancer.select_instance(instances, key=self._lb_key)
        else:
            instance = instances[0]
        return await self._get_transport_for_instance(instance)

    async def _select_transport(self, request: AduibRpcRequest, context: ClientContext) -> ClientTransport:
        instance = await self._select_instance(request, context)
        if instance is None:
            if not self._default_url:
                raise ValueError("No healthy instance available and no default_url configured.")
            return await self._get_transport_for_url(self._default_url, cache_key="__default__")
        return await self._get_transport_for_instance(instance)

    async def _select_instance(self, request: AduibRpcRequest, context: ClientContext) -> ServiceInstance | None:
        service_name = self._resolve_service_name(request, context)
        instances = await self._list_healthy_instances(service_name)
        if not instances:
            return None
        if self._load_balancer is not None:
            return self._load_balancer.select_instance(instances, key=self._lb_key)
        return instances[0]

    def _resolve_service_name(self, request: AduibRpcRequest, context: ClientContext) -> str | None:
        return request.name

    async def _list_healthy_instances(self, service_name: str | None) -> list[ServiceInstance]:
        instances = await self._list_instances(service_name)

        if self._health_registry is not None:
            if instances:
                await self._refresh_health_registry(instances)
            healthy = await self._maybe_await(self._health_registry.list_healthy_instances(service_name or ""))
            if healthy:
                return healthy
            if self._allow_unhealthy_fallback and instances:
                logger.warning("No healthy instances found; falling back to all instances.")
                return instances
            return []

        if not instances:
            return []

        if self._health_checker is not None:
            await self._refresh_health_cache(instances)
            healthy = [inst for inst in instances if self._is_cached_healthy(inst)]
            if healthy:
                return healthy
            if self._allow_unhealthy_fallback:
                logger.warning("No healthy instances found; falling back to all instances.")
                return instances
            return []

        return instances

    async def _list_instances(self, service_name: str | None) -> list[ServiceInstance]:
        if service_name and self._registry and hasattr(self._registry, "list_instances"):
            result = self._registry.list_instances(service_name)
            result = await self._maybe_await(result)
            return list(result or [])
        if service_name and self._registry is None and self._health_registry is not None:
            base_registry = getattr(self._health_registry, "_base_registry", None)
            if base_registry is not None and hasattr(base_registry, "list_instances"):
                result = base_registry.list_instances(service_name)
                result = await self._maybe_await(result)
                return list(result or [])
        if self._instances is None:
            return []
        if service_name is None:
            return list(self._instances)
        return [inst for inst in self._instances if inst.service_name == service_name]

    async def _get_transport_for_instance(self, instance: ServiceInstance) -> ClientTransport:
        key = instance.instance_id
        return await self._get_transport_for_url(instance.url, cache_key=key)

    async def _get_transport_for_url(self, url: str, *, cache_key: str) -> ClientTransport:
        existing = self._transport_cache.get(cache_key)
        if existing is not None:
            return existing
        async with self._transport_lock:
            existing = self._transport_cache.get(cache_key)
            if existing is not None:
                return existing
            created = self._transport_factory(url)
            self._transport_cache[cache_key] = created
            return created

    async def _refresh_health_cache(self, instances: list[ServiceInstance]) -> None:
        check_fn = self._resolve_check_fn()
        if check_fn is None:
            return
        tasks = []
        for inst in instances:
            entry = self._health_cache.get(self._health_key(inst))
            if entry is None or self._is_stale(entry):
                tasks.append(self._check_instance(check_fn, inst))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _refresh_health_registry(self, instances: list[ServiceInstance]) -> None:
        check_method = getattr(self._health_registry, "_check_instance", None)
        cache = getattr(self._health_registry, "_health_cache", None)
        if check_method is None or not isinstance(cache, dict):
            return
        tasks = []
        now_ms = int(time.time() * 1000)
        for inst in instances:
            key = f"{inst.host}:{inst.port}"
            entry = cache.get(key)
            last_check = getattr(entry, "last_check", None)
            checked_at = getattr(last_check, "checked_at_ms", None)
            if checked_at is None or now_ms - int(checked_at) >= self._cache_ttl_ms:
                tasks.append(check_method(inst))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _resolve_check_fn(
        self,
    ) -> Callable[[ServiceInstance], Awaitable[HealthCheckResult]] | None:
        if self._health_checker is None:
            return None
        check_attr = getattr(self._health_checker, "check", None)
        if check_attr is None:
            return self._health_checker  # type: ignore[return-value]
        return check_attr

    async def _maybe_await(self, result):
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def _check_instance(
        self,
        check_fn: Callable[[ServiceInstance], Awaitable[HealthCheckResult]],
        instance: ServiceInstance,
    ) -> None:
        start = time.monotonic()
        try:
            result = await check_fn(instance)
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=str(exc),
            )
        self._update_health_entry(instance, result)

    def _update_health_entry(self, instance: ServiceInstance, result: HealthCheckResult) -> None:
        entry = self._health_cache.get(self._health_key(instance))
        if entry is None:
            entry = HealthAwareServiceInstance(instance=instance)
            self._health_cache[self._health_key(instance)] = entry
        entry.last_check = result

        if result.status == HealthStatus.HEALTHY:
            entry.consecutive_successes += 1
            entry.consecutive_failures = 0
            if entry.consecutive_successes >= self._health_config.healthy_threshold:
                entry.status = HealthStatus.HEALTHY
        else:
            entry.consecutive_failures += 1
            entry.consecutive_successes = 0
            if entry.consecutive_failures >= self._health_config.unhealthy_threshold:
                entry.status = HealthStatus.UNHEALTHY

    def _is_cached_healthy(self, instance: ServiceInstance) -> bool:
        entry = self._health_cache.get(self._health_key(instance))
        return entry is not None and entry.status == HealthStatus.HEALTHY

    def _is_stale(self, entry: HealthAwareServiceInstance) -> bool:
        last_check = entry.last_check
        if last_check is None:
            return True
        return int(time.time() * 1000) - last_check.checked_at_ms >= self._cache_ttl_ms

    def _health_key(self, instance: ServiceInstance) -> str:
        return instance.instance_id


def _service_name_from_task_request(
    request: TaskQueryRequest | TaskCancelRequest | TaskSubscribeRequest,
) -> str | None:
    return getattr(request, "service", None) or getattr(request, "service_name", None)
