import asyncio

import grpc

from aduib_rpc.grpc import helloworld_pb2_grpc, helloworld_pb2
from aduib_rpc.grpc import aduib_rpc_pb2, aduib_rpc_pb2_grpc


def run():
     with grpc.insecure_channel('10.0.0.124:5001') as channel:
        stub = aduib_rpc_pb2_grpc.AduibRpcServiceStub(channel)
        response = stub.completion(aduib_rpc_pb2.RpcTask())
        print("Greeter client received:", response.message)

if __name__ == "__main__":
    run()
