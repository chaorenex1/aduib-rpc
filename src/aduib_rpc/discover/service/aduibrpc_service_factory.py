import asyncio
import inspect
import logging
import ssl
from concurrent import futures
from pathlib import Path
from typing import Any

import grpc
import uvicorn
from grpc_reflection.v1alpha import reflection
from thrift.TMultiplexedProcessor import TMultiplexedProcessor
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer
from thrift.transport import TSocket, TTransport

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.service import ServiceFactory, add_signal_handlers
from aduib_rpc.grpc import aduib_rpc_v2_pb2_grpc, aduib_rpc_v2_pb2
from aduib_rpc.server.context import ServerInterceptor
from aduib_rpc.server.protocols.rest import AduibRpcRestFastAPIApp
from aduib_rpc.server.protocols.rpc import AduibRpcStarletteApp
from aduib_rpc.server.rpc_execution import RequestExecutor
from aduib_rpc.server.request_handlers import DefaultRequestHandler
from aduib_rpc.server.request_handlers.grpc_v2_handler import (
    GrpcV2Handler,
    GrpcV2HealthHandler,
    GrpcV2TaskHandler,
)
from aduib_rpc.server.request_handlers.thrift_v2_handler import (
    ThriftV2Handler,
    ThriftV2HealthHandler,
    ThriftV2TaskHandler,
)
from aduib_rpc.security.mtls import ServerTlsConfig
from aduib_rpc.server.tasks.task_manager import TaskManager
from aduib_rpc.thrift_v2 import AduibRpcService, HealthService, TaskService
from aduib_rpc.utils.constant import TransportSchemes

logger = logging.getLogger(__name__)


class AduibServiceFactory(ServiceFactory):
    """Class for discovering Aduib services on the network."""

    def __init__(self,
                 service_instance: ServiceInstance,
                 interceptors: list[ServerInterceptor] | None = None,
                 request_executors: dict[str, RequestExecutor] | None = None,
                 server_tls: ServerTlsConfig | None = None,
                 task_manager: TaskManager | None = None,
                 ):
        self.interceptors = interceptors or []
        self.request_executors = request_executors or []
        self.service = service_instance
        self.server = None
        self.server_tls = server_tls
        self.task_manager = task_manager
        self._task_manager_started = False

    async def run_server(self, **kwargs: Any):
        """Run a server for the given service instance."""
        await self._ensure_task_manager_started()
        server_tls = kwargs.pop("server_tls", None) or self.server_tls
        match self.service.scheme:
            case TransportSchemes.GRPC:
                await self.run_grpc_server(server_tls=server_tls)
            case TransportSchemes.JSONRPC:
                await self.run_jsonrpc_server(server_tls=server_tls, **kwargs)
            case TransportSchemes.HTTP:
                await self.run_rest_server(server_tls=server_tls, **kwargs)
            case TransportSchemes.THRIFT:
                await self.run_thrift_server()
            case _:
                raise ValueError(f"Unsupported transport scheme: {self.service.scheme}")

    def get_server(self) -> Any:
        return self.server

    async def run_thrift_server(self):
        host, port = self.service.host, self.service.port
        request_handler = DefaultRequestHandler(
            self.interceptors,
            self.request_executors,
            task_manager=self.task_manager,
        )
        rpc_handler = ThriftV2Handler(
            request_handler=request_handler
        )
        task_handler = ThriftV2TaskHandler(request_handler=request_handler)
        health_handler = ThriftV2HealthHandler(request_handler=request_handler)

        multiplex = TMultiplexedProcessor()
        multiplex.registerDefault(AduibRpcService.Processor(rpc_handler))
        multiplex.registerProcessor("AduibRpcService", AduibRpcService.Processor(rpc_handler))
        multiplex.registerProcessor("TaskService", TaskService.Processor(task_handler))
        multiplex.registerProcessor("HealthService", HealthService.Processor(health_handler))
        transport = TSocket.TServerSocket(host, port)
        tfactory = TTransport.TBufferedTransportFactory()
        pfactory = TBinaryProtocol.TBinaryProtocolFactory()
        server = TServer.TThreadPoolServer(multiplex, transport, tfactory, pfactory)
        self.server = server
        logger.info(f"Starting Thrift v2 server on {host}:{port}")
        try:
            server.serve()
        finally:
            await self._stop_task_manager()

    async def run_grpc_server(self, *, server_tls: ServerTlsConfig | None = None):
        # Create gRPC server
        host, port = self.service.host, self.service.port
        request_handler = DefaultRequestHandler(
            self.interceptors,
            self.request_executors,
            task_manager=self.task_manager,
        )

        server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=100))

        # Pure v2 gRPC service
        aduib_rpc_v2_pb2_grpc.add_AduibRpcServiceServicer_to_server(
            GrpcV2Handler(request_handler=request_handler),
            server,
        )
        aduib_rpc_v2_pb2_grpc.add_TaskServiceServicer_to_server(
            GrpcV2TaskHandler(request_handler=request_handler),
            server,
        )
        aduib_rpc_v2_pb2_grpc.add_HealthServiceServicer_to_server(
            GrpcV2HealthHandler(request_handler=request_handler),
            server,
        )

        SERVICE_NAMES = (
            aduib_rpc_v2_pb2.DESCRIPTOR.services_by_name['AduibRpcService'].full_name,
            aduib_rpc_v2_pb2.DESCRIPTOR.services_by_name['TaskService'].full_name,
            aduib_rpc_v2_pb2.DESCRIPTOR.services_by_name['HealthService'].full_name,
            reflection.SERVICE_NAME,
        )
        logger.info(f'Service names for reflection: {SERVICE_NAMES}')
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        if server_tls:
            creds = self._build_grpc_credentials(server_tls)
            server.add_secure_port(f"{host}:{port}", creds)
            logger.info("Starting gRPC server with TLS on %s:%s", host, port)
        else:
            server.add_insecure_port(f'{host}:{port}')
            logger.info(f'Starting gRPC server on {host}:{port}')
        await server.start()
        self.server = server
        loop = asyncio.get_running_loop()
        add_signal_handlers(loop, server.stop, 5)
        stopped = False
        try:
            await server.wait_for_termination()
        except asyncio.CancelledError:
            # Ensure the server is stopped before propagating cancellation.
            try:
                await server.stop(5)
                stopped = True
            finally:
                raise
        finally:
            if not stopped:
                try:
                    await server.stop(5)
                except Exception:
                    logger.exception("Failed to stop gRPC server cleanly")
            await self._stop_task_manager()

    async def run_jsonrpc_server(self, *, server_tls: ServerTlsConfig | None = None, **kwargs: Any, ):
        """Run a JSON-RPC server for the given service instance."""
        host, port = self.service.host, self.service.port
        request_handler = DefaultRequestHandler(
            self.interceptors,
            self.request_executors,
            task_manager=self.task_manager,
        )
        app = AduibRpcStarletteApp(request_handler=request_handler)
        uvicorn_kwargs = dict(kwargs)
        uvicorn_kwargs.update(self._build_uvicorn_ssl_kwargs(server_tls))
        config = uvicorn.Config(app=app.build(**kwargs), host=host, port=port, **uvicorn_kwargs)
        server = uvicorn.Server(config)
        self.server = server
        try:
            await server.serve()
        finally:
            await self._stop_task_manager()

    async def run_rest_server(self, *, server_tls: ServerTlsConfig | None = None, **kwargs: Any, ):
        """Run a REST server for the given service instance."""
        host, port = self.service.host, self.service.port
        request_handler = DefaultRequestHandler(
            self.interceptors,
            self.request_executors,
            task_manager=self.task_manager,
        )
        app = AduibRpcRestFastAPIApp(request_handler=request_handler)
        uvicorn_kwargs = dict(kwargs)
        uvicorn_kwargs.update(self._build_uvicorn_ssl_kwargs(server_tls))
        config = uvicorn.Config(app=app.build(**kwargs), host=host, port=port, **uvicorn_kwargs)
        server = uvicorn.Server(config)
        self.server = server
        try:
            await server.serve()
        finally:
            await self._stop_task_manager()

    def _build_grpc_credentials(self, server_tls: ServerTlsConfig) -> grpc.ServerCredentials:
        cert_chain = Path(server_tls.server_cert_path).read_bytes()
        private_key = Path(server_tls.server_key_path).read_bytes()
        root_certificates = None
        require_client_auth = False

        if server_tls.client_cert_verification != ssl.CERT_NONE:
            if not server_tls.ca_cert_path:
                raise ValueError("ca_cert_path is required when client cert verification is enabled")
            root_certificates = Path(server_tls.ca_cert_path).read_bytes()
            require_client_auth = server_tls.client_cert_verification == ssl.CERT_REQUIRED

        return grpc.ssl_server_credentials(
            [(private_key, cert_chain)],
            root_certificates=root_certificates,
            require_client_auth=require_client_auth,
        )

    def _build_uvicorn_ssl_kwargs(self, server_tls: ServerTlsConfig | None) -> dict[str, Any]:
        if not server_tls:
            return {}

        ssl_kwargs: dict[str, Any] = {
            "ssl_certfile": str(server_tls.server_cert_path),
            "ssl_keyfile": str(server_tls.server_key_path),
        }

        if server_tls.server_key_password:
            ssl_kwargs["ssl_keyfile_password"] = server_tls.server_key_password
        if server_tls.ca_cert_path:
            ssl_kwargs["ssl_ca_certs"] = str(server_tls.ca_cert_path)
        if server_tls.client_cert_verification is not None:
            ssl_kwargs["ssl_cert_reqs"] = int(server_tls.client_cert_verification)
        if server_tls.ciphers:
            ssl_kwargs["ssl_ciphers"] = server_tls.ciphers

        return ssl_kwargs

    async def _ensure_task_manager_started(self) -> None:
        if self.task_manager is None or self._task_manager_started:
            return
        self._task_manager_started = True

        start = getattr(self.task_manager, "start", None)
        if callable(start):
            maybe_awaitable = start()
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable

    async def _stop_task_manager(self) -> None:
        if self.task_manager is None or not self._task_manager_started:
            return

        try:
            stop = getattr(self.task_manager, "stop", None)
            if callable(stop):
                try:
                    maybe_awaitable = stop(grace_period=5.0)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                    return
                except Exception:
                    # Best-effort cleanup: if stop() fails, fall back to shutdown().
                    logger.exception("Failed to stop task manager via stop(grace_period=5.0)")

            shutdown = getattr(self.task_manager, "shutdown", None)
            if callable(shutdown):
                try:
                    maybe_awaitable = shutdown()
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                except Exception:
                    logger.exception("Failed to stop task manager via shutdown()")
        except Exception:
            logger.exception("Unexpected error while stopping task manager")
        finally:
            self._task_manager_started = False
