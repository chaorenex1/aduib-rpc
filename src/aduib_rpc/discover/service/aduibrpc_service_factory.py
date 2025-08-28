import asyncio
import logging
from typing import Any

import grpc
import uvicorn
from grpc_reflection.v1alpha import reflection

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry import ServiceRegistry
from aduib_rpc.discover.service import ServiceFactory, add_signal_handlers, get_ip_port
from aduib_rpc.grpc import aduib_rpc_pb2_grpc, aduib_rpc_pb2
from aduib_rpc.server.protocols.rest import AduibRpcRestFastAPIApp
from aduib_rpc.server.protocols.rpc import AduibRpcStarletteApp
from aduib_rpc.server.request_handlers import DefaultRequestHandler, GrpcHandler
from aduib_rpc.server.request_handlers.grpc_handler import DefaultServerContentBuilder
from aduib_rpc.utils.constant import TransportSchemes

logger = logging.getLogger(__name__)


class AduibServiceFactory(ServiceFactory):
    """Class for discovering Aduib services on the network."""

    def __init__(self,
                 service_instance: ServiceInstance,
                 ):
        self.service = service_instance
        self.server = None

    async def run_server(self, **kwargs: Any):
        """Run a server for the given service instance."""
        match self.service.scheme:
            case TransportSchemes.GRPC:
                self.server=await self.run_grpc_server()
            case TransportSchemes.JSONRPC:
                self.server=await self.run_jsonrpc_server(**kwargs)
            case TransportSchemes.HTTP:
                self.server=await self.run_rest_server(**kwargs)
            case _:
                raise ValueError(f"Unsupported transport scheme: {self.service.scheme}")

    def get_server(self) -> Any:
        return self.server

    async def run_grpc_server(self):
        # Create gRPC server
        host, port = get_ip_port(self.service)
        grpc_server = grpc.aio.server()
        """Creates the gRPC server."""
        request_handler = DefaultRequestHandler()

        server = grpc.aio.server()
        aduib_rpc_pb2_grpc.add_AduibRpcServiceServicer_to_server(
            GrpcHandler(request_handler=request_handler, context_builder=DefaultServerContentBuilder()),
            server,
        )
        SERVICE_NAMES = (
            aduib_rpc_pb2.DESCRIPTOR.services_by_name['AduibRpcService'].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        server.add_insecure_port(f'{host}:{port}')
        logging.info(f'Starting gRPC server on port {port}')
        await grpc_server.start()
        loop = asyncio.get_running_loop()
        add_signal_handlers(loop, grpc_server.stop, 5)
        await grpc_server.wait_for_termination()

    async def run_jsonrpc_server(self, **kwargs: Any, ):
        """Run a JSON-RPC server for the given service instance."""
        host, port = get_ip_port(self.service)
        request_handler = DefaultRequestHandler()
        server = AduibRpcStarletteApp(request_handler=request_handler)
        uvicorn.run(server.build(**kwargs), host=host, port=port)

    async def run_rest_server(self, **kwargs: Any, ):
        """Run a REST server for the given service instance."""
        host, port = get_ip_port(self.service)
        request_handler = DefaultRequestHandler()
        server = AduibRpcRestFastAPIApp(request_handler=request_handler)
        uvicorn.run(server.build(**kwargs), host=host, port=port)
