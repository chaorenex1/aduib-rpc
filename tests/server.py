import asyncio
from concurrent import futures
from typing import Any

import grpc

from aduib_rpc.grpc import aduib_rpc_pb2_grpc
from aduib_rpc.grpc import helloworld_pb2_grpc, helloworld_pb2
from aduib_rpc.server.request_excution import RequestExecutor, RequestContext
from aduib_rpc.server.request_handlers import GrpcHandler, DefaultRequestHandler
from aduib_rpc.server.request_handlers.grpc_handler import DefaultServerContentBuilder
from aduib_rpc.types import ChatCompletionResponse


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

class Greeter(helloworld_pb2_grpc.GreeterServicer):
    def SayHello(self, request, context):
        return helloworld_pb2.HelloReply(message=f"Hello, {request.name}!")

async def serve():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    aduib_rpc_pb2_grpc.add_AduibRpcServiceServicer_to_server(GrpcHandler(context_builder=DefaultServerContentBuilder(),request_handler=DefaultRequestHandler(
        request_executors={
        "gpt-3.5-turbo":TestRequestExecutor()
    })), server)
    # SERVICE_NAMES = (
    #     helloworld_pb2.DESCRIPTOR.services_by_name['Greeter'].full_name,
    #     reflection.SERVICE_NAME,
    # )
    # print(f'Service names for reflection: {SERVICE_NAMES}')
    # reflection.enable_server_reflection(SERVICE_NAMES, server)
    server.add_insecure_port('10.0.0.124:5001')  # 监听 5000
    await server.start()
    print("gRPC server running on 0.0.0.0:5001...")
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())
