"""Local gRPC server for integration tests.

This intentionally avoids service discovery / nacos and just starts a gRPC server
bound to a host:port.

Usage (manual):
  python -m tests.grpc_server_local --host 127.0.0.1 --port 50051
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from concurrent import futures

import grpc

from aduib_rpc.grpc import aduib_rpc_pb2_grpc
from aduib_rpc.server.request_handlers import DefaultRequestHandler, GrpcHandler
from aduib_rpc.server.request_handlers.grpc_handler import DefaultServerContentBuilder
from aduib_rpc.server.rpc_execution.service_call import service

logging.basicConfig(level=logging.INFO)


@service("CaculService")
class CaculService:
    def add(self, x: int, y: int) -> int:
        return x + y


@service("LongTaskSvc")
class LongTaskSvc:
    async def slow_add(self, a: int, b: int, delay_ms: int = 30) -> int:
        await asyncio.sleep(delay_ms / 1000)
        return a + b

    async def slow_fail(self, delay_ms: int = 10) -> int:
        await asyncio.sleep(delay_ms / 1000)
        raise RuntimeError("boom")


async def serve(host: str, port: int) -> None:
    handler = DefaultRequestHandler()

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    aduib_rpc_pb2_grpc.add_AduibRpcServiceServicer_to_server(
        GrpcHandler(context_builder=DefaultServerContentBuilder(), request_handler=handler),
        server,
    )

    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    logging.getLogger(__name__).info("gRPC test server listening on %s:%s", host, port)
    await server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50051)
    args = parser.parse_args()

    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
