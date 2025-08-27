from typing import List, Any

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.load_balance import LoadBalancerFactory
from aduib_rpc.discover.registry import ServiceRegistry
from aduib_rpc.discover.registry.nacos.client import NacosClient
from aduib_rpc.utils.constant import LoadBalancePolicy


class NacosServiceRegistry(ServiceRegistry):

    def __init__(self,
                 server_addresses:str,
                 namespace: str = "public",
                 group_name: str = "DEFAULT_GROUP",
                 username: str = None,
                 password: str = None,
                 policy: LoadBalancePolicy = LoadBalancePolicy.WeightedRoundRobin,
                 ):
        self.server_addresses = server_addresses
        self.namespace = namespace
        self.group_name = group_name
        self.username = username
        self.password = password
        self.policy = policy
        self.client = NacosClient(server_addresses, namespace,group_name, username, password)
        self.client.create_config_service()
        self.client.create_naming_service()

    async def register_service(self, service_info: ServiceInstance) -> None:
        """Register a service instance with the registry."""
        await self.client.register_instance(service_info.service_name, service_info.host, service_info.port, service_info.weight, service_info.metadata)

    async def unregister_service(self, service_info: ServiceInstance) -> None:
        await self.client.remove_instance(service_info.service_name, service_info.host, service_info.port)

    async def discover_service(self, service_info:ServiceInstance) -> ServiceInstance| dict[str,Any] | None:
        services = self.client.list_services(service_info.service_name)
        Service_instances: list[ServiceInstance] = []
        for service in services:
            service_instance = ServiceInstance(
                service_name=service,
                host=service['ip'],
                port=service['port'],
                weight=service.get('weight', 1.0),
                metadata=service.get('metadata', {})
            )
            Service_instances.append(service_instance)
        return await LoadBalancerFactory.get_load_balancer(self.policy).select_instance(Service_instances)