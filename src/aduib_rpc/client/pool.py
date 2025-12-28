from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

try:
    import grpc
    from grpc.aio import Channel
except Exception:  # pragma: no cover
    grpc = None  # type: ignore
    Channel = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PoolKey:
    """Normalized key for pooling network clients/channels."""

    scheme: str
    url: str

    @staticmethod
    def for_url(url: str, scheme: str) -> "PoolKey":
        return PoolKey(scheme=str(scheme), url=str(url))


class HttpxClientPool:
    """A simple per-event-loop pool of httpx.AsyncClient instances."""

    def __init__(self) -> None:
        self._clients: dict[tuple[int, PoolKey], httpx.AsyncClient] = {}

    def get(self, key: PoolKey, *, timeout: httpx.Timeout | None = None) -> httpx.AsyncClient:
        loop_id = id(asyncio.get_running_loop())
        k = (loop_id, key)
        client = self._clients.get(k)
        if client is not None:
            return client
        client = httpx.AsyncClient(timeout=timeout)
        self._clients[k] = client
        return client

    async def aclose_all(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        for c in clients:
            try:
                await c.aclose()
            except Exception:
                logger.exception("Failed to close httpx client")


class GrpcChannelPool:
    """A simple per-event-loop pool of grpc.aio.Channel instances."""

    def __init__(self) -> None:
        self._channels: dict[tuple[int, PoolKey], Channel] = {}

    def get(self, key: PoolKey, *, factory) -> Channel:
        loop_id = id(asyncio.get_running_loop())
        k = (loop_id, key)
        ch = self._channels.get(k)
        if ch is not None:
            return ch
        ch = factory(key.url)
        self._channels[k] = ch
        return ch

    async def aclose_all(self) -> None:
        chans = list(self._channels.values())
        self._channels.clear()
        for ch in chans:
            try:
                await ch.close()  # type: ignore[func-returns-value]
            except Exception:
                logger.exception("Failed to close grpc channel")


# Global default pools (opt-in via ClientConfig.pooling_enabled)
_default_httpx_pool = HttpxClientPool()
_default_grpc_pool = GrpcChannelPool()


def default_httpx_pool() -> HttpxClientPool:
    return _default_httpx_pool


def default_grpc_pool() -> GrpcChannelPool:
    return _default_grpc_pool

