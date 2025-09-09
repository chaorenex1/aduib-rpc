import inspect
import logging
from typing import Any

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry import ServiceRegistry
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes
from aduib_rpc.utils.net_utils import NetUtils

logger = logging.getLogger(__name__)


def registry(name: str):
    """Decorator to register a request executor class."""

    def decorator(cls: Any):
        if name:
            ServiceRegistryFactory.register_registry(name, cls)
        else:
            logger.warning("No method specified for service registry. Skipping registration.")
        return cls

    return decorator


class ServiceRegistryFactory:
    """Factory class for creating ServiceRegistry instances."""
    registry_cache: dict[str, Any] = {}
    service_info: ServiceInstance = None

    @classmethod
    def from_service_registry(cls, registry_type: str, *args, **kwargs) -> ServiceRegistry:
        """Creates a ServiceRegistry instance from the registry cache.
        Args:
            registry_type: The type of the registry to create.
        Returns:
            An instance of the ServiceRegistry.
        """
        registry_class = cls.registry_cache.get(registry_type)
        if not registry_class:
            raise ValueError(f"Service registry '{registry_type}' not found in registry cache.")
        sig = inspect.signature(registry_class.__init__)
        vaild_args = {k: v for k, v in zip(sig.parameters, args) if k != 'self'}
        valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        registry = registry_class(*vaild_args, **valid_kwargs)
        cls.registry_cache[registry_type] = registry
        return registry

    @classmethod
    def register_registry(cls, name: str, service_registry) -> None:
        """Registers a ServiceRegistry instance with the factory.
        Args:
            name: The name of the registry.
            service_registry: An instance of a class that implements the ServiceRegistry interface.
        """
        cls.registry_cache[name] = service_registry

    @classmethod
    def list_registries(cls) -> list[ServiceRegistry]:
        """Lists all registered ServiceRegistry instances.

        Returns:
            A list of registered ServiceRegistry instances.
        """
        return [v for v in cls.registry_cache.values() if not inspect.isclass(v)]

    @classmethod
    def start_service_discovery(cls, config: dict[str, Any]) -> ServiceRegistry | None:
        """Starts a ServiceRegistry instance.

        Args:
            config: A dictionary containing configuration for the registry.
        """
        discovery_enabled = config.get('DISCOVERY_SERVICE_ENABLED', False)
        if not discovery_enabled:
            logger.warning(
                "Service registry disabled. Service registry not enabled. using key: DISCOVERY_SERVICE_ENABLED")
            return None
        registry_type = config.get('DISCOVERY_SERVICE_TYPE', None)
        if not registry_type:
            raise ValueError("Service registry type not specified. using key: DISCOVERY_SERVICE_TYPE")
        service_registry = cls.from_service_registry(registry_type, **config)
        logger.info(f"Starting service discovery: {registry_type}")
        return service_registry

    @classmethod
    async def start_service_registry(cls, config: dict[str, Any]) -> ServiceInstance | None:
        """Starts a ServiceRegistry instance.

        Args:
            config: A dictionary containing configuration for the registry.
        """
        discovery_enabled = config.get('DISCOVERY_SERVICE_ENABLED', False)
        if not discovery_enabled:
            logger.warning(
                "Service registry disabled. Service registry not enabled. using key: DISCOVERY_SERVICE_ENABLED")
            return None
        registry_type = config.get('DISCOVERY_SERVICE_TYPE', None)
        if not registry_type:
            raise ValueError("Service registry type not specified. using key: DISCOVERY_SERVICE_TYPE")
        registry_instance = cls.from_service_registry(registry_type, **config)
        logger.info(f"Starting service registry: {registry_type}")
        ip, port = NetUtils.get_ip_and_free_port()
        cls.service_info = ServiceInstance(service_name=config.get('APP_NAME', 'aduib-rpc'), host=ip, port=port,
                                           protocol=AIProtocols.AduibRpc, weight=1,
                                           scheme=config.get('SERVICE_TRANSPORT_SCHEME', TransportSchemes.GRPC))
        await registry_instance.register_service(cls.service_info)
        return cls.service_info
