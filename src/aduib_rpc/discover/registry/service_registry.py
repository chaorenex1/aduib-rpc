import logging
from abc import ABC, abstractmethod
from typing import Union, Any

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.load_balance import LoadBalancerFactory
from aduib_rpc.utils.constant import LoadBalancePolicy

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


class InMemoryServiceRegistry(ServiceRegistry):
    """In-memory implementation of the ServiceRegistry."""

    def __init__(self, policy: LoadBalancePolicy = LoadBalancePolicy.WeightedRoundRobin) -> None:
        self.policy = policy
        self._services: dict[str, list[ServiceInstance]] = {}

    def register_service(self, service_info: ServiceInstance) -> None:
        if service_info.service_name not in self._services:
            self._services[service_info.service_name] = []
        self._services[service_info.service_name].append(service_info)
        logger.info(f"Registered service: {service_info.service_name}")

    def unregister_service(self, service_name: str) -> None:
        if service_name in self._services:
            del self._services[service_name]
        else:
            instances:list[ServiceInstance] = self._services.get(service_name)
            for instance in instances:
                if instance.instance_id == service_name:
                    instances.remove(instance)
                    break
        logger.info(f"Unregistered service: {service_name}")


    def discover_service(self, service_name: str) -> ServiceInstance | None:
        if service_name not in self._services:
            return None
        instances = self._services.get(service_name)
        return  LoadBalancerFactory.get_load_balancer(self.policy).select_instance(instances)
