import asyncio
import logging

import grpc
from pydantic import BaseModel

from aduib_rpc.client.auth import InMemoryCredentialsProvider
from aduib_rpc.client.auth.interceptor import AuthInterceptor
from aduib_rpc.client.base_client import ClientConfig, AduibRpcClient
from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.discover.registry.nacos.nacos import NacosServiceRegistry
from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.server.request_excution.service_call import client, FuncCallContext
from aduib_rpc.utils.constant import TransportSchemes

logging.basicConfig(level=logging.DEBUG)

async def main():
    registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
                                         username='nacos', password='nacos11.')
    service_name = 'test_grpc_app'
    discover_service = await registry.discover_service(service_name)
    logging.debug(f'Service: {discover_service}')
    logging.debug(f'Service URL: {discover_service.url}')
    def create_channel(url: str) -> grpc.aio.Channel:
        logging.debug(f'Channel URL: {url}')
        return grpc.aio.insecure_channel(url)

    client_factory = AduibRpcClientFactory(
        config=ClientConfig(streaming=True,grpc_channel_factory=create_channel, supported_transports=[TransportSchemes.GRPC]))
    aduib_rpc_client:AduibRpcClient = client_factory.create(discover_service.url, server_preferred=TransportSchemes.GRPC,interceptors=[AuthInterceptor(credentialProvider=InMemoryCredentialsProvider())])
    resp = aduib_rpc_client.completion(method="chat.completions",
                                       data={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}]},
                                       meta={"model": "gpt-3.5-turbo",
                                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"} | discover_service.get_service_info())
    async for r in resp:
        logging.debug(f'Response: {r}')


class test_add(BaseModel):
    x: int = 1
    y: int = 2

@client("CaculService")
class CaculService:
    def add(self, x, y):
        """同步加法"""
        ...

    def add2(self, data:test_add):
        """同步加法"""
        ...

    async def async_mul(self, x, y):
        """异步乘法"""
        ...

    def fail(self, x):
        """会失败的函数"""
        ...

async def client_call():
    registry_config = {
        "server_addresses": "10.0.0.96:8848",
        "namespace": "eeb6433f-d68c-4b3b-a4a7-eeff19110e4d",
        "group_name": "DEFAULT_GROUP",
        "username": "nacos",
        "password": "nacos11.",
        "max_retry": 3,
        "DISCOVERY_SERVICE_ENABLED": True,
        "DISCOVERY_SERVICE_TYPE": "nacos"
    }
    ServiceRegistryFactory.start_service_discovery(registry_config)
    FuncCallContext.enable_auth()
    caculService = CaculService()
    result = caculService.add(1, 2)
    logging.debug(f'1 + 2 = {result}')
    result = caculService.add2(test_add(x=3, y=4))
    logging.debug(f'3 + 4 = {result}')
    result = await caculService.async_mul(3, 5)
    logging.debug(f'3 * 5 = {result}')
    # client_caller = ClientCaller.from_client_caller("caculService")
    # res1 = await client_caller.call("add", 1, 2)
    # res3 = await client_caller.call("add2", test_add())
    # res2 = await client_caller.call("async_mul", 3, 4)
    # res4 = await client_caller.call("fail", 123)

    # print("add:", res1)
    # print("add2:", res3)
    # print("async_mul:", res2)
    # print("fail:", res4)


if __name__ == '__main__':
    asyncio.run(client_call())