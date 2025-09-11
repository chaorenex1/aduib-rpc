import asyncio
import logging
from concurrent import futures
from typing import Any

import grpc
import uvicorn
from grpc_reflection.v1alpha import reflection
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer
from thrift.transport import TSocket, TTransport

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.service import ServiceFactory, add_signal_handlers
from aduib_rpc.grpc import aduib_rpc_pb2_grpc, aduib_rpc_pb2
from aduib_rpc.server.context import ServerInterceptor
from aduib_rpc.server.protocols.rest import AduibRpcRestFastAPIApp
from aduib_rpc.server.protocols.rpc import AduibRpcStarletteApp
from aduib_rpc.server.rpc_execution import RequestExecutor
from aduib_rpc.server.request_handlers import DefaultRequestHandler, GrpcHandler
from aduib_rpc.server.request_handlers.grpc_handler import DefaultServerContentBuilder
from aduib_rpc.server.request_handlers.thrift_handler import ThriftHandler
from aduib_rpc.thrift import AduibRpcService
from aduib_rpc.utils.constant import TransportSchemes

logger = logging.getLogger(__name__)


class AduibServiceFactory(ServiceFactory):
    """Class for discovering Aduib services on the network."""

    def __init__(self,
                 service_instance: ServiceInstance,
                 interceptors: list[ServerInterceptor] | None = None,
                 request_executors: dict[str, RequestExecutor] | None = None,
                 ):
        self.interceptors = interceptors or []
        self.request_executors = request_executors or []
        self.service = service_instance
        self.server = None

    async def run_server(self, **kwargs: Any):
        """Run a server for the given service instance."""
        match self.service.scheme:
            case TransportSchemes.GRPC:
                await self.run_grpc_server()
            case TransportSchemes.JSONRPC:
                await self.run_jsonrpc_server(**kwargs)
            case TransportSchemes.HTTP:
                await self.run_rest_server(**kwargs)
            case TransportSchemes.THRIFT:
                await self.run_thrift_server()
            case _:
                raise ValueError(f"Unsupported transport scheme: {self.service.scheme}")

    def get_server(self) -> Any:
        return self.server

    async def run_thrift_server(self):
        host, port = self.service.host, self.service.port
        handler = ThriftHandler(request_handler=DefaultRequestHandler(self.interceptors, self.request_executors))
        processor = AduibRpcService.Processor(handler)
        transport = TSocket.TServerSocket(host, port)
        tfactory = TTransport.TBufferedTransportFactory()
        pfactory = TBinaryProtocol.TBinaryProtocolFactory()
        server = TServer.TThreadPoolServer(processor, transport, tfactory, pfactory)
        logger.info(f"Starting Thrift server on {host}:{port}")
        server.serve()

    async def run_grpc_server(self):
        # Create gRPC server
        host, port = self.service.host, self.service.port
        """Creates the gRPC server."""
        request_handler = DefaultRequestHandler(self.interceptors,self.request_executors)

        server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=100))
        aduib_rpc_pb2_grpc.add_AduibRpcServiceServicer_to_server(
            GrpcHandler(request_handler=request_handler, context_builder=DefaultServerContentBuilder()),
            server,
        )
        SERVICE_NAMES = (
            aduib_rpc_pb2.DESCRIPTOR.services_by_name['AduibRpcService'].full_name,
            reflection.SERVICE_NAME,
        )
        logger.info(f'Service names for reflection: {SERVICE_NAMES}')
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        server.add_insecure_port(f'{host}:{port}')
        logger.info(f'Starting gRPC server on {host}:{port}')
        await server.start()
        self.server = server
        loop = asyncio.get_running_loop()
        add_signal_handlers(loop, server.stop, 5)
        await server.wait_for_termination()

    async def run_jsonrpc_server(self, **kwargs: Any, ):
        """Run a JSON-RPC server for the given service instance."""
        host, port = self.service.host, self.service.port
        request_handler = DefaultRequestHandler(self.interceptors, self.request_executors)
        server = AduibRpcStarletteApp(request_handler=request_handler)
        self.server = server
        config = uvicorn.Config(app=server.build(**kwargs), host=host, port=port, **kwargs)
        await uvicorn.Server(config).serve()

    async def run_rest_server(self, **kwargs: Any, ):
        """Run a REST server for the given service instance."""
        host, port = self.service.host, self.service.port
        request_handler = DefaultRequestHandler(self.interceptors, self.request_executors)
        server = AduibRpcRestFastAPIApp(request_handler=request_handler)
        self.server = server
        config = uvicorn.Config(app=server.build(**kwargs), host=host, port=port, **kwargs)
        await uvicorn.Server(config).serve()
