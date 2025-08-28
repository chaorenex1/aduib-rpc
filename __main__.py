import asyncio
import logging

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry.nacos.nacos_service_registry import NacosServiceRegistry
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes

logging.basicConfig(level=logging.DEBUG)

async def main():
    service = ServiceInstance(service_name='test_jsonrpc_app', host='localhost', port=5000,
                                   protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.GRPC)
    registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
                                         username='nacos', password='nacos11.')
    factory = AduibServiceFactory(service_instance=service)
    await registry.discover_service(service.service_name)
    await factory.run_server()

if __name__ == '__main__':
    asyncio.run(main())