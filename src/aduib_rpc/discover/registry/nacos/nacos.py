from typing import Any

try:
    from v2.nacos.naming.model.instance import Instance
except ImportError:
    # nacos-sdk-python is optional
    Instance = None

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.load_balance import LoadBalancerFactory
from aduib_rpc.discover.registry import ServiceRegistry
from aduib_rpc.discover.registry.nacos.client import InnerNacosClient
from aduib_rpc.discover.registry.registry_factory import registry
from aduib_rpc.utils.constant import LoadBalancePolicy, AIProtocols, TransportSchemes


@registry(name='nacos')
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
        self.client = InnerNacosClient(server_addresses, namespace, username, password,group_name)


    async def register_service(self, service_info: ServiceInstance) -> None:
        """Register a service instance with the registry."""
        await self.client.register_instance(
            service_info.service_name,
            service_info.host,
            service_info.port,
            service_info.weight,
            metadata=service_info.metadata
        )


    async def unregister_service(self, service_info: ServiceInstance) -> None:
        await self.client.remove_instance(service_info.service_name, service_info.host, service_info.port)

    async def list_instances(self, service_name: str) -> list[ServiceInstance]:
        services: list[Instance] = await self.client.list_instances(service_name)
        if not services:
            return []
        if isinstance(services, dict):
            services = [Instance.model_validate(obj=service) for service in services.get('hosts', [])]

        service_instances: list[ServiceInstance] = []
        for service in services:
            md = getattr(service, "metadata", None) or {}
            service_instance = ServiceInstance(
                service_name=md.get("service_name"),
                protocol=AIProtocols.to_original(md.get('protocol')),
                scheme=TransportSchemes.to_original(md.get('scheme')),
                host=service.ip,
                port=service.port,
                weight=int(service.weight),
                metadata=md,
            )
            service_instances.append(service_instance)
        return service_instances

    async def discover_service(self, service_name: str) -> ServiceInstance | dict[str, Any] | None:
        service_instances = await self.list_instances(service_name)
        if not service_instances:
            return None
        instance = LoadBalancerFactory.get_load_balancer(self.policy).select_instance(service_instances)
        return instance