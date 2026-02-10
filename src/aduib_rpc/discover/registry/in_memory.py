import logging

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.load_balance import LoadBalancerFactory
from aduib_rpc.discover.registry import ServiceRegistry
from aduib_rpc.discover.registry.registry_factory import registry
from aduib_rpc.utils.constant import LoadBalancePolicy

logger=logging.getLogger(__name__)

@registry(name='in-memory')
class InMemoryServiceRegistry(ServiceRegistry):
    """In-memory implementation of the ServiceRegistry."""

    def __init__(self, policy: LoadBalancePolicy = LoadBalancePolicy.WeightedRoundRobin) -> None:
        self.policy = policy
        self._services: dict[str, list[ServiceInstance]] = {}

    async def register_service(self, service_info: ServiceInstance) -> None:
        if service_info.service_name not in self._services:
            self._services[service_info.service_name] = []
        self._services[service_info.service_name].append(service_info)
        logger.info(f"Registered service: {service_info.service_name}")

    async def unregister_service(self, service_info: ServiceInstance) -> None:
        service_name = service_info.service_name
        if service_name in self._services:
            del self._services[service_name]
        else:
            instances:list[ServiceInstance] = self._services.get(service_name)
            for instance in instances:
                if instance.instance_id == service_name:
                    instances.remove(instance)
                    break
        logger.info(f"Unregistered service: {service_name}")

    async def list_instances(self, service_name: str) -> list[ServiceInstance]:
        if service_name not in self._services:
            return []
        return list(self._services.get(service_name) or [])

    async def discover_service(self, service_name: str) -> ServiceInstance | None:
        instances = await self.list_instances(service_name)
        return LoadBalancerFactory.get_load_balancer(self.policy).select_instance(instances)
