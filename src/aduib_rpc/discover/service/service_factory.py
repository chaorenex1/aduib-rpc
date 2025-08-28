import asyncio
import logging
import platform
import signal
from abc import ABC, abstractmethod
from typing import Any, Callable

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


def get_ip_port(service: ServiceInstance) -> tuple[str, int]:
    ip, port = NetUtils.get_ip_and_free_port()
    if not service.host:
        service.host = ip
    host = service.host
    if not service.port:
        service.port = port
    port = service.port
    return host, port


def add_signal_handlers(loop, shutdown_coro: Callable[..., Any], *args, **kwargs) -> None:
    """Add signal handlers for graceful shutdown."""
    if platform.system() == 'Windows':
        return

    def shutdown(sig: signal.Signals) -> None:
        logger.warning('Received shutdown signal %s', sig)
        shutdown_coro(*args, **kwargs)
        logger.warning('shutdown complete')

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: shutdown(s))


class ServiceFactory(ABC):
    """Class for discovering services on the network."""

    @abstractmethod
    async def run_server(self, **kwargs: Any):
        """Run a server for the given service instance."""

    @abstractmethod
    def get_server(self) -> Any:
        """Get the server instance."""
