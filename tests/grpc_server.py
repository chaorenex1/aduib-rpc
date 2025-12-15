import asyncio
import logging

from pydantic import BaseModel

from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.server.rpc_execution.service_call import service

logging.basicConfig(level=logging.DEBUG)

class test_add(BaseModel):
    x: int = 1
    y: int = 2

@service(service_name='CaculService')
class CaculService:
    def add(self, x, y):
        """同步加法"""
        return x + y

    def add2(self, data:test_add):
        """同步加法"""
        return data.x + data.y

    async def async_mul(self, x, y):
        """异步乘法"""
        await asyncio.sleep(0.1)
        return x * y

    def fail(self, x):
        """会失败的函数"""
        raise RuntimeError("Oops!")

async def main():
    registry_config = {
        "server_addresses": "10.0.0.96:8848",
        "namespace": "eeb6433f-d68c-4b3b-a4a7-eeff19110e4d",
        "group_name": "DEFAULT_GROUP",
        "username": "nacos",
        "password": "nacos11.",
        "max_retry": 3,
        "DISCOVERY_SERVICE_ENABLED": True,
        "DISCOVERY_SERVICE_TYPE": "nacos",
        "APP_NAME": "CaculServiceApp"
    }
    service = await ServiceRegistryFactory.start_service_registry(registry_config)
    # ip,port = NetUtils.get_ip_and_free_port()
    # service = ServiceInstance(service_name='test_grpc', host=ip, port=port,
    #                                protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.GRPC)
    # registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
    #                                      namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
    #                                      username='nacos', password='nacos11.')
    factory = AduibServiceFactory(service_instance=service)
    # await registry.register_service(service)
    await factory.run_server()

if __name__ == '__main__':
    asyncio.run(main())