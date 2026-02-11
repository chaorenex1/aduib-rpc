"""End-to-end app entry for service registry + discovery + calling.

This module is intentionally *thin*: it orchestrates existing primitives
(registry, resolver, server factory, client factory) into a single workflow.

Design goals:
- No transport-specific code in callers.
- Works with in-memory registry for local dev/tests.
- Minimizes API changes in existing modules.
- V2 out-of-the-box: server starts with v2 negotiation enabled, and registry
  entries advertise v2 capabilities so v2 clients can pick sensible defaults.

Contract
- Input: registry (or registry type+config) and one or more ServiceInstance.
- Action: async register -> start server(s) -> resolve -> create client(s).
- Output: handles that allow stopping servers and making client calls.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any, TYPE_CHECKING

from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.client.service_resolver import RegistryServiceResolver, ResolvedService
from aduib_rpc.config import AduibRpcConfig, ConfigSourceProvider, load_config
from aduib_rpc.discover import ServiceCapabilities
from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.entities.service_instance import HealthStatus
from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.registry.service_registry import ServiceRegistry
from aduib_rpc.discover.service.aduibrpc_service_factory import AduibServiceFactory
from aduib_rpc.resilience import Cache
from aduib_rpc.server import get_runtime, update_runtime
from aduib_rpc.server.context import ServerInterceptor
from aduib_rpc.server.tasks.provider import TaskManagerProvider
from aduib_rpc.server.tasks.task_manager import TaskManagerConfig
from aduib_rpc.utils.constant import LoadBalancePolicy, AIProtocols, TransportSchemes

logger = logging.getLogger(__name__)

_GLOBAL_RPC_APP: "RpcApp | None" = None

if TYPE_CHECKING:
    from aduib_rpc.security.permission_provider import PermissionProvider


class ServeMode(StrEnum):
    DISCOVERY_ONLY = "discovery_only"
    REGISTRATION_ONLY = "registration_only"
    REGISTRATION_AND_DISCOVERY = "registration_and_discovery"


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


class RpcApp:
    """Orchestrates registry + server start + discovery + client creation.

    v2-by-default behavior:
    - `register()` injects v2 capability metadata into ServiceInstance.metadata
      (unless already present).
    - `start_servers()` attaches VersionNegotiationInterceptor by default.

    This keeps older call sites working, but makes new usage get v2-negotiation
    without additional plumbing.
    """

    registries: list[ServiceRegistry]
    resolver_policy: LoadBalancePolicy = LoadBalancePolicy.WeightedRoundRobin

    config: AduibRpcConfig
    instance: ServiceInstance
    factory: AduibServiceFactory

    def __init__(self, *, registries: list[ServiceRegistry]) -> None:
        self.registries = registries
        self.config = AduibRpcConfig()
        self.health_registries: list["HealthAwareRegistry"] = []
        self.health_registry: "HealthAwareRegistry | None" = None
        self._health_checker: "HealthChecker | None" = None
        self._base_registries: list[ServiceRegistry] | None = None
        self._service_factories: list[AduibServiceFactory] = []
        self.permission_provider: "PermissionProvider | None" = None
        self.cache: Cache | None = None

    def set_permission_provider(self, provider) -> None:
        from aduib_rpc.security.permission_provider import PermissionProvider

        if not isinstance(provider, PermissionProvider):
            raise TypeError("provider must be a PermissionProvider")
        provider.apply(self)

    def set_cache_provider(self, cache: Cache) -> None:
        self.cache = cache

    def get_client_id(self) -> str:
        from aduib_rpc.utils.id_utils import IdUtils

        return IdUtils.generate_client_id(prefix="aduib-rpc-client-")

    def _build_default_interceptors(self) -> list[ServerInterceptor]:
        interceptors: list[ServerInterceptor] = []

        from aduib_rpc.server.interceptors.version_negotiation import VersionNegotiationInterceptor

        interceptors.append(
            VersionNegotiationInterceptor(
                server_versions=list(self.config.protocol.protocol_versions),
                default_version=self.config.protocol.default_version,
            )
        )

        # Load OTel interceptor (tracing + metrics)
        cfg = self.config or AduibRpcConfig()
        if cfg.telemetry.enabled:
            try:
                from aduib_rpc.server.interceptors.telemetry import OTelServerInterceptor
                from aduib_rpc.telemetry import configure_telemetry

                # Initialize telemetry (tracing + metrics)
                configure_telemetry(cfg.telemetry)

                interceptors.append(OTelServerInterceptor())
                logger.info("OTel interceptor loaded")
            except ImportError as e:
                logger.warning("OTel interceptor not available: %s", e)
            except Exception:
                logger.exception("Failed to build OTel interceptor")

        if cfg.resilience.enabled:
            try:
                from aduib_rpc.server.interceptors.resilience import (
                    ServerResilienceConfig,
                    ServerResilienceInterceptor,
                )

                resilience_config = ServerResilienceConfig(
                    rate_limiter=cfg.resilience.rate_limiter,
                    circuit_breaker=cfg.resilience.circuit_breaker,
                    fallback=cfg.resilience.fallback,
                    enabled=cfg.resilience.enabled,
                )
                interceptors.append(ServerResilienceInterceptor(resilience_config))
                logger.info("Resilience interceptor loaded")
            except ImportError as e:
                logger.warning("Resilience interceptor not available: %s", e)
            except Exception:
                logger.exception("Failed to build Resilience interceptor")
        if cfg.qos.enabled:
            try:
                from aduib_rpc.server.qos import QosHandler
                from aduib_rpc.server.interceptors import QosInterceptor

                interceptors.append(
                    QosInterceptor(
                        qos_handler=QosHandler(
                            self.cache, self.config.qos.timeout_ms, self.config.qos.idempotency_ttl_s
                        )
                    )
                )
                logger.info("QoS interceptor loaded")
            except ImportError as e:
                logger.warning("QoS interceptor not available: %s", e)
            except Exception:
                logger.exception("Failed to build QoS interceptor")

        audit_config = None
        audit_logger = None
        try:
            from aduib_rpc.telemetry import AuditConfig, AuditLogger

            audit_config = AuditConfig(
                enabled=cfg.telemetry.audit_enabled,
                log_level=logging.getLevelName(cfg.telemetry.log_level),
                include_params=cfg.telemetry.audit_include_params,
                include_response=cfg.telemetry.audit_include_response,
                export_to_telemetry=cfg.telemetry.enabled,
                otlp_endpoint=cfg.telemetry.otlp_endpoint,
            )
            audit_logger = AuditLogger(config=audit_config)
        except ImportError as e:
            logger.warning("Audit logger not available: %s", e)
        except Exception:
            logger.exception("Failed to build Audit logger")

        if cfg.security.rbac_enabled or cfg.security.audit_enabled or cfg.security.require_auth:
            try:
                from aduib_rpc.server.interceptors.security import SecurityInterceptor

                provider = getattr(self, "permission_provider", None)
                interceptors.append(
                    SecurityInterceptor(
                        config=cfg.security,
                        audit_logger=audit_logger,
                        token_validator=getattr(provider, "token_validator", None),
                        permission_validator=getattr(provider, "permission_validator", None),
                    )
                )
                logger.info("Security interceptor loaded")
            except ImportError as e:
                logger.warning("Security interceptor not available: %s", e)
                if cfg.security.require_auth:
                    raise RuntimeError(
                        "Security interceptor is required (require_auth=True) but is not available"
                    ) from e
            except Exception as e:
                logger.exception("Failed to build Security interceptor")
                if cfg.security.require_auth:
                    raise RuntimeError(
                        "Security interceptor is required (require_auth=True) but failed to initialize"
                    ) from e

        if cfg.telemetry.audit_enabled and audit_config is not None:
            try:
                from aduib_rpc.server.interceptors import AuditInterceptor

                interceptors.append(AuditInterceptor(config=audit_config))
                logger.info("Audit interceptor loaded")
            except ImportError as e:
                logger.warning("Audit interceptor not available: %s", e)
            except Exception:
                logger.exception("Failed to build Audit interceptor")
        from aduib_rpc.server.interceptors import TenantInterceptor

        interceptors.append(TenantInterceptor())
        logger.info("Tenant interceptor loaded")
        from aduib_rpc.server.interceptors import QosInterceptor

        interceptors.append(QosInterceptor())
        logger.info("QoS interceptor loaded")
        # sort by order
        interceptors.sort(key=lambda x: x.order())
        return interceptors

    async def enable_health_checks(self) -> None:
        if not self.registries:
            return
        config = self.config.health_check
        if config is None:
            return
        if self._base_registries is None:
            self._base_registries = list(self.registries)
        if self._health_checker is None:
            from aduib_rpc.discover.health.health_check import DefaultHealthChecker

            self._health_checker = DefaultHealthChecker(
                config=self.config, client_factory=AduibRpcClientFactory.build_health_client_factory(self.config.client)
            )
        self.health_registries = []
        for registry in self._base_registries:
            try:
                from aduib_rpc.discover.registry.health_aware_registry import HealthAwareRegistry

                if isinstance(registry, HealthAwareRegistry):
                    health_registry = registry
                else:
                    health_registry = HealthAwareRegistry(registry, self._health_checker, config)
                await health_registry.start()
                self.health_registries.append(health_registry)
                try:
                    from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory

                    for key, instance in ServiceRegistryFactory.registry_instances.items():
                        if instance is registry:
                            ServiceRegistryFactory.registry_instances[key] = health_registry
                except Exception:
                    logger.exception("Failed to build ServiceRegistry instance")
                    raise
            except Exception:
                logger.exception(
                    "Failed to enable health checks for registry %s",
                    type(registry).__name__,
                )
        if self.health_registries:
            self.health_registry = self.health_registries[0]
            self.registries = list(self.health_registries)

    @classmethod
    def from_registry_type(cls, registry_type: str = "in_memory", **config: Any) -> "RpcApp":
        registry = ServiceRegistryFactory.from_service_registry(registry_type, **config)
        return cls(registries=[registry])

    @property
    def resolver(self) -> RegistryServiceResolver:
        return RegistryServiceResolver(self.registries, policy=self.resolver_policy)

    async def register(self, inst: ServiceInstance) -> None:
        for reg in self.registries:
            await reg.register_service(inst)

    async def discover_async(self, service_name: str, lb_key: str | None) -> ResolvedService | None:
        return await self.resolver.resolve(service_name, lb_key=lb_key)

    def discover(self, service_name: str, lb_key: str | None) -> ResolvedService | None:
        from aduib_rpc.utils.anyio_compat import run as anyio_run

        return anyio_run(self.discover_async, service_name, lb_key)

    async def start_servers(
        self,
        instance: ServiceInstance,
        *,
        server_kwargs: dict[str, Any] | None = None,
        interceptors=None,
        task_manager=None,
    ):
        """Start servers in background tasks.

        For gRPC servers, run_server() blocks until termination, so we always
        spawn tasks.

        Defaults:
        - Attaches VersionNegotiationInterceptor that prefers v2.
        """

        server_kwargs = server_kwargs or {}
        if interceptors is None:
            interceptors = self._build_default_interceptors()

        factory = AduibServiceFactory(
            service_instance=instance,
            interceptors=interceptors,
            task_manager=task_manager,
            server_tls=self.config.security.mtls.to_server_tls_config(),
        )
        self.factory = factory
        self._service_factories.append(factory)
        await factory.run_server(**server_kwargs)

    async def shutdown(self, *, grace: float = 5.0) -> None:
        """Best-effort shutdown of servers and background health checks."""
        for registry in list(self.health_registries):
            try:
                stop = getattr(registry, "stop", None)
                if callable(stop):
                    await stop()
            except Exception:
                logger.exception("Failed to stop health registry")

        for factory in list(self._service_factories):
            await self._stop_factory(factory, grace)

    async def _stop_factory(self, factory: AduibServiceFactory, grace: float) -> None:
        import inspect

        server = None
        try:
            server = factory.get_server()
        except Exception:
            server = getattr(factory, "server", None)
        if server is None:
            return

        stop = getattr(server, "stop", None)
        if callable(stop):
            try:
                result = stop(grace)
                if inspect.isawaitable(result):
                    await result
                return
            except Exception:
                logger.exception("Failed to stop server cleanly")

        shutdown = getattr(server, "shutdown", None)
        if callable(shutdown):
            try:
                result = shutdown()
                if inspect.isawaitable(result):
                    await result
                return
            except Exception:
                logger.exception("Failed to shutdown server cleanly")

        if hasattr(server, "should_exit"):
            try:
                server.should_exit = True
            except Exception:
                logger.exception("Failed to signal server shutdown")

    def create_client(self, resolved: ResolvedService):
        from aduib_rpc.client.config import ClientConfig as BaseClientConfig

        client_config = BaseClientConfig(
            httpx_client=self.config.client.httpx_client,
            grpc_channel_factory=self.config.client.grpc_channel_factory,
            supported_transports=list(self.config.client.supported_transports),
            pooling_enabled=self.config.client.pooling_enabled,
            http_timeout=self.config.client.http_timeout,
            grpc_timeout=self.config.client.grpc_timeout,
        )

        client_factory = AduibRpcClientFactory(config=client_config)
        if self._health_checker or self.health_registry:
            try:
                from aduib_rpc.client.transports.health_aware import (
                    HealthAwareClientTransport,
                )

                producer = client_factory._registry.get(resolved.scheme)
                if producer is not None:
                    wrapped = HealthAwareClientTransport.wrap_transport_producer(
                        producer,
                        registry=(
                            self._base_registries[0]
                            if self._base_registries
                            else (self.registries[0] if self.registries else None)
                        ),
                        health_registry=self.health_registry,
                        health_checker=self._health_checker,
                        health_config=self.config.health_check,
                        lb_policy=self.resolver_policy,
                        lb_key=resolved.get_lb_value(),
                    )
                    client_factory.register(resolved.scheme, wrapped)
            except Exception:
                pass

        return client_factory.create(
            resolved.url, server_preferred=resolved.scheme, interceptors=get_runtime().interceptors
        )


def get_global_app() -> RpcApp:
    """Return the global RpcApp instance once initialized."""

    if _GLOBAL_RPC_APP is None:
        raise RuntimeError("Global RpcApp is not initialized. Call run_serve first.")
    return _GLOBAL_RPC_APP


def set_global_app(app: RpcApp) -> RpcApp:
    """Explicitly set the global RpcApp instance."""

    global _GLOBAL_RPC_APP
    _GLOBAL_RPC_APP = app
    return app


def reset_global_app() -> None:
    """Reset the global RpcApp instance (primarily for tests)."""

    global _GLOBAL_RPC_APP
    _GLOBAL_RPC_APP = None


async def run_serve(
    *,
    serve_mode: ServeMode = ServeMode.REGISTRATION_AND_DISCOVERY,
    service_name: str,
    # New: auto-import modules that contain @service classes.
    service_modules: list[str],
    # New: defaults for auto instance assembly.
    service_host: str = "127.0.0.1",
    service_port: int = 0,
    service_scheme: TransportSchemes = TransportSchemes.GRPC,
    service_weight: int = 1,
    service_metadata: dict[str, str] = None,
    registry_type: str = "in_memory",
    registry_config: dict[str, Any] | None = None,
    config: str | AduibRpcConfig | None = None,
    config_source_type: str | None = None,
    config_source_config: dict[str, Any] | None = None,
    task_manager_enable: bool = True,
    task_manager_type: str = "in-memory",
    task_manager_config: TaskManagerConfig | None = None,
    server_kwargs: dict[str, Any] | None = None,
    resolver_policy: LoadBalancePolicy = LoadBalancePolicy.WeightedRoundRobin,
    permission_provider: "PermissionProvider | None" = None,
    cache_provider: Cache | None = None,
) -> RpcApp:
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

    Config loading:
    - If `config` is provided, use it as the base (string path or AduibRpcConfig).
    - If `config_source_type` is provided, load/update the base via the loader.

    Returns (app, running_services, resolved_service).
    """
    runtime = get_runtime()

    from aduib_rpc.utils.service_loader import import_service_modules

    # Load config if provided, then optionally overlay via config source.
    config_obj: AduibRpcConfig | None = None
    if isinstance(config, AduibRpcConfig):
        config_obj = config
    else:
        if config is not None:
            try:
                config_obj = load_config(config)
            except Exception as e:
                logger.warning(f"Failed to load AduibRpcConfig from {config}: {e}, proceeding with defaults.")

    if config_obj is None:
        config_obj = AduibRpcConfig()

    if config_source_type:
        try:
            source_kwargs = dict(config_source_config or {})
            source_kwargs.setdefault("target", config_obj)
            loaded = await ConfigSourceProvider.load_config(config_source_type, **source_kwargs)
            if isinstance(loaded, tuple):
                loaded_config = loaded[0]
            else:
                loaded_config = loaded
            if isinstance(loaded_config, AduibRpcConfig):
                config_obj = loaded_config
        except Exception as e:
            logger.warning(
                f"Failed to load AduibRpcConfig from source={config_source_type}: {e}, proceeding with defaults."
            )
    runtime.set_config(config_obj)

    metadata: dict[str, str] = {}
    if service_metadata:
        metadata.update(service_metadata)

    capabilities = ServiceCapabilities()
    match service_scheme:
        case TransportSchemes.GRPC | TransportSchemes.GRPCS:
            capabilities.streaming = True
            capabilities.bidirectional = True
        case TransportSchemes.JSONRPC | TransportSchemes.JSONRPCS | TransportSchemes.HTTP | TransportSchemes.HTTPS:
            capabilities.streaming = True
            capabilities.bidirectional = False
        case TransportSchemes.THRIFT:
            capabilities.streaming = False
            capabilities.bidirectional = False
        case _:
            raise ValueError(f"Unsupported service scheme: {service_scheme}")

    update_runtime(runtime)

    capabilities.methods = runtime.batch_to_method_descriptors()
    instance: ServiceInstance = ServiceInstance.create(
        service_name=service_name,
        host=service_host,
        port=int(service_port),
        protocol=AIProtocols.AduibRpc,
        weight=service_weight,
        scheme=service_scheme,
        metadata=metadata,
        health=HealthStatus.HEALTHY,
        capabilities=capabilities,
    )
    instance.metadata.update(metadata)

    app = RpcApp.from_registry_type(registry_type, **(registry_config or {}))
    app.resolver_policy = resolver_policy
    if permission_provider is not None:
        app.set_permission_provider(permission_provider)
    if cache_provider is not None:
        app.set_cache_provider(cache_provider)
    await app.enable_health_checks()
    if serve_mode in {
        ServeMode.REGISTRATION_ONLY,
        ServeMode.REGISTRATION_AND_DISCOVERY,
    }:
        await app.register(instance)

    task_manager_none = None
    if task_manager_enable:
        if task_manager_config is None:
            raise ValueError("task_manager_config must be provided if task_manager_enable is True")

        task_manager_none = TaskManagerProvider.from_task_source_instance(task_manager_type, config=task_manager_config)

    resolved = await app.discover_async(service_name, lb_key=None)
    if resolved is None:
        raise RuntimeError(f"Failed to discover service: {service_name}")

    app.config = config_obj
    from aduib_rpc.server import set_service_info

    set_service_info(instance)
    import_service_modules(service_modules)

    if serve_mode in {
        ServeMode.REGISTRATION_ONLY,
        ServeMode.REGISTRATION_AND_DISCOVERY,
    }:
        await app.start_servers(
            instance,
            server_kwargs=server_kwargs,
            task_manager=task_manager_none,
        )
    return app
