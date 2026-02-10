import asyncio
import logging
import platform
import signal
from abc import ABC, abstractmethod
from typing import Any, Callable

from aduib_rpc.utils.net_utils import NetUtils

from aduib_rpc.discover.entities import ServiceInstance

logger = logging.getLogger(__name__)


def get_ip_port(service: ServiceInstance) -> tuple[str, int]:
    ip, port = NetUtils.get_ip_and_free_port()
    if ip:
        service.host = ip
    host = service.host
    if port:
        service.port = port
    port = service.port
    return host, port


def add_signal_handlers(loop, shutdown_coro: Callable[..., Any], *args, **kwargs) -> None:
    """Add signal handlers for graceful shutdown."""
    if platform.system() == 'Windows':
        return

    def shutdown(sig: signal.Signals) -> None:
        logger.warning('Received shutdown signal %s', sig)
        result = shutdown_coro(*args, **kwargs)
        if asyncio.iscoroutine(result):
            asyncio.ensure_future(result, loop=loop)
        logger.warning('Shutdown scheduled')

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
