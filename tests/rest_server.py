import asyncio
import logging

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry.nacos.nacos import NacosServiceRegistry
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes

logging.basicConfig(level=logging.DEBUG)

async def main():
    service = ServiceInstance(service_name='test_rest_app', host='10.0.0.124', port=5001,
                                   protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.HTTP)
    registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
                                         username='nacos', password='nacos11.')
    factory = AduibServiceFactory(service_instance=service)
    await registry.register_service(service)
    await factory.run_server()

if __name__ == '__main__':
    asyncio.run(main())