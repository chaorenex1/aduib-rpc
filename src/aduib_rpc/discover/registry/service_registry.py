from abc import ABC, abstractmethod

from aduib_rpc.discover.entities import ServiceInstance


class ServiceRegistry(ABC):
    """Abstract base class for a service registry."""

    @abstractmethod
    async def register_service(self,service_info: ServiceInstance) -> None:
        """Registers a service with the registry.

        Args:
            service_info: A dictionary containing information about the service.
        """

    @abstractmethod
    async def unregister_service(self, service_id: str) -> None:
        """Unregisters a service from the registry.

        Args:
            service_id: The name of the service to unregister.
        """

    @abstractmethod
    async def discover_service(self, service_id: str) -> ServiceInstance | None:
        """Discovers a service by its name.

        Args:
            service_id: The name of the service to discover.

        Returns:
            A object containing information about the service, or None if not found.
        """
