from abc import ABC, abstractmethod
from typing import Union, Any

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.load_balance import LoadBalancerFactory
from aduib_rpc.utils.constant import LoadBalancePolicy


class ServiceRegistry(ABC):
    """Abstract base class for a service registry."""

    @abstractmethod
    async def register_service(self,service_info: ServiceInstance) -> None:
        """Registers a service with the registry.

        Args:
            service_info: A dictionary containing information about the service.
        """

    @abstractmethod
    async def unregister_service(self, service_info: Union[str,ServiceInstance]) -> None:
        """Unregisters a service from the registry.

        Args:
            service_info: The name of the service to unregister or a ServiceInstance object.
        """

    @abstractmethod
    async def discover_service(self, service_info: Union[str,ServiceInstance]) -> ServiceInstance |dict[str,Any] | None:
        """Discovers a service by its name.

        Args:
            service_info: The name of the service to discover or a ServiceInstance object.

        Returns:
            A object containing information about the service, or None if not found.
        """


class InMemoryServiceRegistry(ServiceRegistry):
    """In-memory implementation of the ServiceRegistry."""

    def __init__(self, policy: LoadBalancePolicy = LoadBalancePolicy.WeightedRoundRobin) -> None:
        self.policy = policy
        self._services: dict[str, list[ServiceInstance]] = {}

    async def register_service(self, service_info: ServiceInstance) -> None:
        if service_info.service_name not in self._services:
            self._services[service_info.service_name] = []
        self._services[service_info.service_name].append(service_info)

    async def unregister_service(self, service_name: str) -> None:
        if service_name in self._services:
            del self._services[service_name]
        else:
            instances:list[ServiceInstance] = self._services.get(service_name)
            for instance in instances:
                if instance.instance_id == service_name:
                    instances.remove(instance)
                    break


    async def discover_service(self, service_name: str) -> ServiceInstance | None:
       return await LoadBalancerFactory.get_load_balancer(self.policy).select_instance(self._services.get(service_name))
