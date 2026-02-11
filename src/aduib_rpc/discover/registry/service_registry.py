import logging
from abc import ABC, abstractmethod
from typing import Any

from aduib_rpc.discover.entities import ServiceInstance

logger = logging.getLogger(__name__)


class ServiceRegistry(ABC):
    """Abstract base class for a service registry."""

    @abstractmethod
    async def register_service(self, service_info: ServiceInstance) -> None:
        """Registers a service with the registry.

        Args:
            service_info: Service instance to register.
        """

    @abstractmethod
    async def unregister_service(self, service_info: ServiceInstance) -> None:
        """Unregisters a service from the registry.

        Args:
            service_info: The name of the service to unregister.
        """

    @abstractmethod
    async def list_instances(self, service_name: str) -> list[ServiceInstance]:
        """List all instances for a service.

        Boundary note:
            Registries should focus on *discovery* (listing instances).
            Load balancing should be handled by a resolver layer.

        Returns:
            A list of ServiceInstance. Empty list if not found.
        """

    async def discover_service(self, service_name: str) -> ServiceInstance | dict[str, Any] | None:
        """Backward-compatible convenience API.

        Prefer `list_instances()` in new code.
        """
        instances = await self.list_instances(service_name)
        return instances[0] if instances else None
