"""End-to-end app entry for service registry + discovery + calling.

This module is intentionally *thin*: it orchestrates existing primitives
(registry, resolver, server factory, client factory) into a single workflow.

Design goals:
- No transport-specific code in callers.
- Works with in-memory registry for local dev/tests.
- Minimizes API changes in existing modules.

Contract
- Input: registry (or registry type+config) and one or more ServiceInstance.
- Action: async register -> start server(s) -> resolve -> create client(s).
- Output: handles that allow stopping servers and making client calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable

from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.client.service_resolver import RegistryServiceResolver, ResolvedService
from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.registry.service_registry import ServiceRegistry
from aduib_rpc.discover.service.aduibrpc_service_factory import AduibServiceFactory
from aduib_rpc.utils.constant import LoadBalancePolicy


# --- new helpers: build ServiceInstance from imported @service modules ---

def _unique_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _extract_service_names_from_runtime() -> list[str]:
    """Return logical service names registered via @service("...").

    The decorator registers keys like "{service_name}.{ClassName}" into runtime.
    We normalize them back to the logical `service_name`.
    """

    from aduib_rpc.server.rpc_execution.runtime import get_runtime

    runtime = get_runtime()
    keys = list(runtime.service_instances.keys())

    # Fallback to persistent catalogs if runtime was reset.
    if not keys:
        try:
            from aduib_rpc.server.rpc_execution.service_call import _SERVICE_CATALOG  # type: ignore

            keys = list(_SERVICE_CATALOG.keys())
        except Exception:
            keys = []

    logical: list[str] = []
    for k in keys:
        # k is typically "MyService.MyService" (service + class)
        if not k:
            continue
        logical.append(k.split(".", 1)[0])

    return _unique_keep_order(logical)


async def _auto_instances_from_services(
    *,
    host: str,
    port_start: int,
    scheme,
    weight: int = 1,
    metadata: dict[str, str] | None = None,
) -> list[ServiceInstance]:
    """Create instances for each discovered logical service name.

    Notes:
    - If port_start is 0, we allocate free ports.
    - scheme should be a TransportSchemes value (kept untyped here to avoid cycle).
    """

    from aduib_rpc.utils.net_utils import NetUtils
    from aduib_rpc.utils.constant import AIProtocols

    service_names = _extract_service_names_from_runtime()
    if not service_names:
        return []

    instances: list[ServiceInstance] = []
    next_port = port_start

    for name in service_names:
        if port_start == 0:
            _ip, free_port = NetUtils.get_ip_and_free_port()
            use_port = free_port
        else:
            use_port = next_port
            next_port += 1

        instances.append(
            ServiceInstance(
                service_name=name,
                host=host,
                port=int(use_port),
                protocol=AIProtocols.AduibRpc,
                weight=weight,
                scheme=scheme,
                metadata=metadata or {},
            )
        )

    return instances


def _service_names_to_instances_single_endpoint(
    service_names: list[str],
    *,
    host: str,
    port: int,
    scheme,
    weight: int = 1,
    metadata: dict[str, str] | None = None,
):
    """Strategy B: one network endpoint, many logical service names.

    Registry registration is per service_name, so we register N ServiceInstance
    entries that all point to the same host:port.
    """

    from aduib_rpc.utils.constant import AIProtocols

    return [
        ServiceInstance(
            service_name=name,
            host=host,
            port=int(port),
            protocol=AIProtocols.AduibRpc,
            weight=weight,
            scheme=scheme,
            metadata=metadata or {},
        )
        for name in service_names
    ]


async def _allocate_host_port(*, host: str, port: int) -> tuple[str, int]:
    """Allocate a concrete (host, port).

    If port==0, pick a free local port.
    """

    if port != 0:
        return host, int(port)

    from aduib_rpc.utils.net_utils import NetUtils

    ip, free_port = NetUtils.get_ip_and_free_port()
    # Respect caller-provided host unless it's empty.
    return (host or ip), int(free_port)


@dataclass
class RunningService:
    """A started server plus the service instance it serves."""

    instance: ServiceInstance
    factory: AduibServiceFactory
    task: asyncio.Task[None]

    async def stop(self, grace: float = 2.0) -> None:
        """Best-effort stop.

        Notes:
        - gRPC uses grpc.aio server with .stop().
        - uvicorn servers started via .serve() are canceled by task cancel.
        """
        server = self.factory.get_server()
        if server is not None and hasattr(server, "stop"):
            try:
                res = server.stop(grace)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                # best-effort
                pass

        if not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


@dataclass(frozen=True)
class RpcApp:
    """Orchestrates registry + server start + discovery + client creation."""

    registries: list[ServiceRegistry]
    resolver_policy: LoadBalancePolicy = LoadBalancePolicy.WeightedRoundRobin
    lb_key: str | None = None

    @classmethod
    def from_registry_type(cls, registry_type: str = "in_memory", **config: Any) -> "RpcApp":
        registry = ServiceRegistryFactory.from_service_registry(registry_type, **config)
        return cls(registries=[registry])

    @property
    def resolver(self) -> RegistryServiceResolver:
        return RegistryServiceResolver(self.registries, policy=self.resolver_policy, key=self.lb_key)

    async def register(self, instances: Iterable[ServiceInstance]) -> None:
        for inst in instances:
            for reg in self.registries:
                await reg.register_service(inst)

    def discover(self, service_name: str) -> ResolvedService | None:
        return self.resolver.resolve(service_name)

    async def start_servers(
        self,
        instances: Iterable[ServiceInstance],
        *,
        server_kwargs: dict[str, Any] | None = None,
    ) -> list[RunningService]:
        """Start servers in background tasks.

        For gRPC servers, run_server() blocks until termination, so we always
        spawn tasks.
        """
        server_kwargs = server_kwargs or {}
        running: list[RunningService] = []
        for inst in instances:
            factory = AduibServiceFactory(service_instance=inst)
            task = asyncio.create_task(factory.run_server(**server_kwargs))
            running.append(RunningService(instance=inst, factory=factory, task=task))
        # Give servers a brief moment to bind ports before clients call.
        await asyncio.sleep(server_kwargs.get("startup_delay", 0.1))
        return running

    def create_client(self, resolved: ResolvedService, *, stream: bool = False):
        return AduibRpcClientFactory.create_client(
            resolved.url,
            stream=stream,
            server_preferred=resolved.scheme,
        )


async def run_end_to_end(
    *,
    registry_type: str = "in_memory",
    registry_config: dict[str, Any] | None = None,
    # If instances is omitted, we build them from imported @service modules.
    instances: list[ServiceInstance] | None = None,
    call_service_name: str,
    server_kwargs: dict[str, Any] | None = None,
    # New: auto-import modules that contain @service classes.
    service_modules: list[str] | None = None,
    # New: defaults for auto instance assembly.
    default_host: str = "127.0.0.1",
    default_port_start: int = 0,
    default_scheme=None,
    default_weight: int = 1,
    default_metadata: dict[str, str] | None = None,
    # New: auto assembly mode.
    auto_mode: str = "single_endpoint",
    # New: allow skipping server start (useful for unit tests).
    start_server: bool = True,
) -> tuple[RpcApp, list[RunningService], ResolvedService]:
    """One-shot full workflow helper.

    Two modes:
    1) Explicit instances: pass `instances=[ServiceInstance(...), ...]`.
    2) @service import mode: pass `service_modules=["pkg.services"]` and omit
       `instances`.

    Auto assembly strategies:
    - auto_mode="single_endpoint" (Strategy B, recommended):
      Import all @service modules, extract logical service names, allocate ONE
      host:port, start ONE server, but register that same endpoint under each
      logical service_name.
    - auto_mode="per_service" (Strategy A):
      Allocate one endpoint per logical service name.

    Returns (app, running_services, resolved_service).
    """

    if service_modules:
        from aduib_rpc.utils.service_loader import import_service_modules

        import_service_modules(service_modules)

    if instances is None:
        if default_scheme is None:
            from aduib_rpc.utils.constant import TransportSchemes

            default_scheme = TransportSchemes.GRPC

        service_names = _extract_service_names_from_runtime()
        if not service_names:
            raise RuntimeError(
                "No ServiceInstance provided and no @service registrations found. "
                "Pass `instances=` or import modules via `service_modules=`."
            )

        if auto_mode == "single_endpoint":
            host, port = await _allocate_host_port(host=default_host, port=default_port_start)
            instances = _service_names_to_instances_single_endpoint(
                service_names,
                host=host,
                port=port,
                scheme=default_scheme,
                weight=default_weight,
                metadata=default_metadata,
            )
        elif auto_mode == "per_service":
            instances = await _auto_instances_from_services(
                host=default_host,
                port_start=default_port_start,
                scheme=default_scheme,
                weight=default_weight,
                metadata=default_metadata,
            )
        else:
            raise ValueError(f"Unsupported auto_mode: {auto_mode!r}")

    app = RpcApp.from_registry_type(registry_type, **(registry_config or {}))
    await app.register(instances)

    running: list[RunningService] = []
    if start_server:
        if instances and auto_mode == "single_endpoint" and service_modules and instances is not None:
            # Strategy B: all instances share the same endpoint, so start a single server.
            server_instance = instances[0]
            running = await app.start_servers([server_instance], server_kwargs=server_kwargs)
        else:
            running = await app.start_servers(instances, server_kwargs=server_kwargs)

    resolved = app.discover(call_service_name)
    if resolved is None:
        raise RuntimeError(f"Failed to discover service: {call_service_name}")
    return app, running, resolved

