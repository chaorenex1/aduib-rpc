import asyncio
import logging
from typing import Any

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry.nacos.nacos import NacosServiceRegistry
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.server.request_excution import RequestExecutor, RequestContext
from aduib_rpc.server.request_excution.request_executor import request_execution
from aduib_rpc.types import ChatCompletionResponse
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes

logging.basicConfig(level=logging.DEBUG)

@request_execution(method="chat.completions")
class TestRequestExecutor(RequestExecutor):
    def execute(self, context: RequestContext) -> Any:
        print(f"Received prompt: {context.get_input_data()}")
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