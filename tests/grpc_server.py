import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.server.rpc_execution import RequestExecutor, RequestContext
from aduib_rpc.server.rpc_execution.request_executor import request_execution
from aduib_rpc.server.rpc_execution.service_call import service
from aduib_rpc.types import ChatCompletionResponse

logging.basicConfig(level=logging.DEBUG)

@request_execution(method="chat.completions")
class TestRequestExecutor(RequestExecutor):
    def execute(self, context: RequestContext) -> Any:
        print(f"Received prompt: {context}")
        response = ChatCompletionResponse(id="chatcmpl-123", object="chat.completion", created=1677652288,
                                              model="gpt-3.5-turbo-0301", choices=[
                    {"index": 0, "message": {"role": "assistant", "content": "Hello! How can I assist you today?"},
                     "finish_reason": "stop"}], usage={"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21})
        if context.stream:
            async def stream_response():
                for i in range(1, 4):
                    chunk = response
                    yield chunk
            return stream_response()
        else:
            return response

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