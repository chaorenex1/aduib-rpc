import inspect
import logging
from typing import Any, cast

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry import ServiceRegistry
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes
from aduib_rpc.utils.net_utils import NetUtils

logger = logging.getLogger(__name__)


def registry(name: str):
    """Decorator to register a service registry implementation."""

    def decorator(cls: Any):
        if name:
            ServiceRegistryFactory.register_registry(name, cls)
        else:
            logger.warning("No registry name specified. Skipping registration.")
        return cls

    return decorator


class ServiceRegistryFactory:
    """Factory class for creating ServiceRegistry instances."""

    registry_classes: dict[str, Any] = {}
    registry_instances: dict[str, ServiceRegistry] = {}
    service_info: ServiceInstance | None = None

    @classmethod
    def from_service_registry(cls, registry_type: str, *args, **kwargs) -> ServiceRegistry:
        """Creates (or returns a cached) ServiceRegistry instance.

        Args:
            registry_type: The type/name of the registry to create.
        Returns:
            An instance of the ServiceRegistry.
        """
        if registry_type in cls.registry_instances:
            return cls.registry_instances[registry_type]

        registry_class = cls.registry_classes.get(registry_type)
        if not registry_class:
            raise ValueError(f"Service registry '{registry_type}' not found.")

        sig = inspect.signature(registry_class.__init__)
        param_names = [p for p in sig.parameters.keys() if p != 'self']

        valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        valid_args = []
        for i, a in enumerate(args):
            if i >= len(param_names):
                break
            if param_names[i] in valid_kwargs:
                continue
            valid_args.append(a)

        instance: ServiceRegistry = registry_class(*valid_args, **valid_kwargs)
        cls.registry_instances[registry_type] = instance
        return instance

    @classmethod
    def register_registry(cls, name: str, service_registry) -> None:
        """Registers a ServiceRegistry class with the factory."""
        cls.registry_classes[name] = service_registry

    @classmethod
    def list_registries(cls) -> list[ServiceRegistry]:
        """Lists all created ServiceRegistry instances."""
        return list(cls.registry_instances.values())

    @classmethod
    def start_service_discovery(cls, config: dict[str, Any]) -> ServiceRegistry | None:
        discovery_enabled = config.get('DISCOVERY_SERVICE_ENABLED', False)
        if not discovery_enabled:
            logger.warning(
                "Service discovery disabled. Set DISCOVERY_SERVICE_ENABLED=true to enable.")
            return None

        registry_type = config.get('DISCOVERY_SERVICE_TYPE')
        if not registry_type:
            raise ValueError("Service registry type not specified. Use DISCOVERY_SERVICE_TYPE")

        service_registry = cls.from_service_registry(registry_type, **config)
        logger.info(f"Starting service discovery: {registry_type}")
        return service_registry

    @classmethod
    async def start_service_registry(cls, config: dict[str, Any]) -> ServiceInstance | None:
        discovery_enabled = config.get('DISCOVERY_SERVICE_ENABLED', False)
        if not discovery_enabled:
            logger.warning(
                "Service registry disabled. Set DISCOVERY_SERVICE_ENABLED=true to enable.")
            return None

        registry_type = config.get('DISCOVERY_SERVICE_TYPE')
        if not registry_type:
            raise ValueError("Service registry type not specified. Use DISCOVERY_SERVICE_TYPE")

        registry_instance = cls.from_service_registry(registry_type, **config)
        logger.info(f"Starting service registry: {registry_type}")

        ip, port = NetUtils.get_ip_and_free_port()
        cls.service_info = ServiceInstance(
            service_name=config.get('APP_NAME', 'aduib-rpc'),
            host=ip,
            port=port,
            protocol=AIProtocols.AduibRpc,
            weight=1,
            scheme=config.get('SERVICE_TRANSPORT_SCHEME', TransportSchemes.GRPC),
        )
        service_info = cast(ServiceInstance, cls.service_info)
        registry_instance = cast(ServiceRegistry, registry_instance)
        await registry_instance.register_service(service_info)
        return service_info
