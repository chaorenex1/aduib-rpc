import asyncio
import logging
from typing import Any

import grpc
import uvicorn
from grpc_reflection.v1alpha import reflection
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from aduib_rpc.discover.service import ServiceFactory, add_signal_handlers, get_ip_port
from aduib_rpc.discover.registry import ServiceRegistry
from aduib_rpc.utils.async_utils import AsyncUtils
from aduib_rpc.utils.constant import TransportSchemes
from aduib_rpc.utils.net_utils import NetUtils

is_a2a_installed: bool
try:
    from a2a.grpc import a2a_pb2_grpc, a2a_pb2
    from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH
    from a2a.types import AgentCard
    from a2a.server.tasks import TaskStore
    from a2a.server.agent_execution import AgentExecutor
    from a2a.server.request_handlers import DefaultRequestHandler, GrpcHandler
    from a2a.server.apps import A2ARESTFastAPIApplication, A2AStarletteApplication

    is_a2a_installed = True
except ImportError:
    AgentExecutor = None  # type: ignore # pyright: ignore
    AgentCard = None
    TaskStore = None
    AGENT_CARD_WELL_KNOWN_PATH = '/.well-known/agent-card'
    a2a_pb2_grpc = None
    a2a_pb2 = None
    DefaultRequestHandler = None
    GrpcHandler = None
    A2ARESTFastAPIApplication = None
    A2AStarletteApplication = None
    is_a2a_installed = False

from aduib_rpc.discover.entities import ServiceInstance

logger = logging.getLogger(__name__)


class A2aServiceFactory(ServiceFactory):
    """Class for discovering A2A services on the network."""

    def __init__(self,
                 service: ServiceInstance,
                 agent_card: AgentCard,
                 agent_executor: AgentExecutor,
                 task_store: TaskStore
                 ):
        self.service = service
        self.agent_card = agent_card
        self.agent_executor = agent_executor
        self.task_store = task_store
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
            case _:
                raise ValueError(f"Unsupported transport scheme: {self.service.scheme}")

    def get_server(self) -> Any:
        return self.server

    async def run_grpc_server(self):
        # Create gRPC server
        host, port = get_ip_port(self.service)
        grpc_server = await self.create_grpc_server(self.agent_card, host, port)
        agent_card_port = NetUtils.find_free_port(start_port=port)

        # The gRPC server cannot serve the public agent card at the well-known URL.
        # A separate HTTP server is needed to serve the public agent card, which clients
        # can use as an entry point for discovering the gRPC endpoint.

        # create http server for serving agent card
        http_server = self.create_agent_card_server(self.agent_card, host, agent_card_port)

        loop = asyncio.get_running_loop()
        add_signal_handlers(loop, grpc_server.stop, 5)
        await grpc_server.start()
        self.server = grpc_server

        await asyncio.gather(http_server.serve(), grpc_server.wait_for_termination())

    def create_agent_card_server(self, agent_card: AgentCard, host: str, agent_card_port: int) -> uvicorn.Server:
        """Creates the Starlette app for the agent card server."""

        def get_agent_card_http(request: Request) -> Response:
            return JSONResponse(
                agent_card.model_dump(mode='json', exclude_none=True)
            )

        routes = [
            Route(AGENT_CARD_WELL_KNOWN_PATH, endpoint=get_agent_card_http)
        ]
        app = Starlette(routes=routes)

        # Create uvicorn server for agent card
        config = uvicorn.Config(
            app,
            host=host,
            port=agent_card_port,
            log_config=None,
        )
        logger.info(f'Starting HTTP server on port {agent_card_port}')
        return uvicorn.Server(config)

    async def create_grpc_server(self, agent_card: AgentCard, host: str, port: int) -> grpc.aio.Server:
        """Creates the gRPC server."""
        request_handler = DefaultRequestHandler(
            agent_executor=self.agent_executor, task_store=self.task_store
        )

        server = grpc.aio.server()
        a2a_pb2_grpc.add_A2AServiceServicer_to_server(
            GrpcHandler(agent_card, request_handler),
            server,
        )
        SERVICE_NAMES = (
            a2a_pb2.DESCRIPTOR.services_by_name['A2AService'].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        server.add_insecure_port(f'{host}:{port}')
        logger.info(f'Starting gRPC server on port {port}')
        return server

    async def run_jsonrpc_server(self, **kwargs: Any, ):
        """Run a JSON-RPC server for the given service instance."""
        host, port = get_ip_port(self.service)
        request_handler = DefaultRequestHandler(
            agent_executor=self.agent_executor, task_store=self.task_store
        )

        server = A2AStarletteApplication(
            agent_card=self.agent_card, http_handler=request_handler
        )
        self.server = server

        uvicorn.run(server.build(**kwargs), host=host, port=port)

    async def run_rest_server(self, **kwargs: Any, ):
        """Run a JSON-RPC server for the given service instance."""
        host, port = get_ip_port(self.service)
        request_handler = DefaultRequestHandler(
            agent_executor=self.agent_executor, task_store=self.task_store
        )

        server = A2ARESTFastAPIApplication(
            agent_card=self.agent_card, http_handler=request_handler
        )
        self.server = server

        uvicorn.run(server.build(**kwargs), host=host, port=port)
