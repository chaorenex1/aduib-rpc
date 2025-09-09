import logging
from abc import ABC, abstractmethod
from typing import Any

from aduib_rpc.discover.entities import ServiceInstance

logger=logging.getLogger(__name__)


class ServiceRegistry(ABC):
    """Abstract base class for a service registry."""

    @abstractmethod
    def register_service(self,service_info: ServiceInstance) -> None:
        """Registers a service with the registry.

        Args:
            service_info: A dictionary containing information about the service.
        """

    @abstractmethod
    def unregister_service(self, service_name: str) -> None:
        """Unregisters a service from the registry.

        Args:
            service_info: The name of the service to unregister
        """

    @abstractmethod
    def discover_service(self, service_name: str) -> ServiceInstance |dict[str,Any] | None:
        """Discovers a service by its name.

        Args:
            service_info: The name of the service to discover

        Returns:
            A object containing information about the service, or None if not found.
        """
