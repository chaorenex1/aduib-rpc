import asyncio
import logging

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)
logging.getLogger("v2").setLevel(logging.DEBUG)

async def main():
    registry_config = {
        "server_addresses": "10.0.0.96:8848",
        "namespace": "eeb6433f-d68c-4b3b-a4a7-eeff19110e4d",
        "group_name": "DEFAULT_GROUP",
        "username": "nacos",
        "password": "nacos11.",
        "max_retry": 3
    }
    registry=ServiceRegistryFactory.from_service_registry('nacos', **registry_config)
    service = ServiceInstance(service_name='test_thrift_app', host='10.0.0.169', port=5009,
                                   protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.THRIFT)
    factory = AduibServiceFactory(service_instance=service)
    await registry.register_service(service)
    await factory.run_server()

if __name__ == '__main__':
    asyncio.run(main())