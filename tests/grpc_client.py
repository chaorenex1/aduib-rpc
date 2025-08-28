import asyncio
import logging

import grpc

from aduib_rpc.client.auth import InMemoryCredentialsProvider
from aduib_rpc.client.auth.interceptor import AuthInterceptor
from aduib_rpc.client.base_client import ClientConfig, AduibRpcClient
from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.discover.registry.nacos.nacos_service_registry import NacosServiceRegistry
from aduib_rpc.utils.constant import TransportSchemes

logging.basicConfig(level=logging.DEBUG)

async def main():
    registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
                                         username='nacos', password='nacos11.')
    service_name = 'test_jsonrpc_app'
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

    # await factory.run_server()


if __name__ == '__main__':
    asyncio.run(main())