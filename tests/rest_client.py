import asyncio
import logging
import uuid

import httpx

from aduib_rpc.client import ClientContext
from aduib_rpc.client.auth import InMemoryCredentialsProvider
from aduib_rpc.client.auth.interceptor import AuthInterceptor
from aduib_rpc.client.base_client import ClientConfig, AduibRpcClient
from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry.nacos.nacos_service_registry import NacosServiceRegistry
from aduib_rpc.utils.constant import TransportSchemes, SecuritySchemes, AIProtocols

logging.basicConfig(level=logging.DEBUG)

async def main():
    service = ServiceInstance(service_name='test_rest_app', host='10.0.0.124', port=5001,
                              protocol=AIProtocols.AduibRpc, weight=1, scheme=TransportSchemes.HTTP)
    registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',
                                         namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d', group_name='DEFAULT_GROUP',
                                         username='nacos', password='nacos11.')
    service_name = 'test_rest_app'
    # discover_service = await registry.discover_service(service_name) or service
    discover_service = service
    logging.debug(f'Service: {discover_service}')
    logging.debug(f'Service URL: {discover_service.url}')

    context = ClientContext()
    context.state['session_id'] = str(uuid.uuid4())
    context.state['security_schema'] = SecuritySchemes.APIKey

    credentials_provider = InMemoryCredentialsProvider()
    credentials_provider.set_credentials(SecuritySchemes.APIKey,"my_secret_api_key",context.state['session_id'])

    client_factory = AduibRpcClientFactory(
        config=ClientConfig(streaming=True,
                            httpx_client=httpx.AsyncClient(),
                            supported_transports=[TransportSchemes.GRPC,TransportSchemes.JSONRPC,TransportSchemes.HTTP]))
    aduib_rpc_client:AduibRpcClient = client_factory.create(discover_service.url,
                                                            server_preferred=TransportSchemes.HTTP,
                                                            interceptors=[AuthInterceptor(credentialProvider=credentials_provider)])
    resp = aduib_rpc_client.completion(context=context,method="chat.completions",
                                       data={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}]},
                                       meta={"model": "gpt-3.5-turbo",
                                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"} | discover_service.get_service_info())
    async for r in resp:
        logging.debug(f'Response: {r}')

    # await factory.run_server()


if __name__ == '__main__':
    asyncio.run(main())