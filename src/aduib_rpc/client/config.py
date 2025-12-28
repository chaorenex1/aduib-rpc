import dataclasses
from collections.abc import Callable

try:
    import httpx
    from grpc.aio import Channel
except ImportError:
    httpx = None  # type: ignore
    Channel = None  # type: ignore

from aduib_rpc.utils.constant import TransportSchemes


@dataclasses.dataclass
class ClientConfig:
    """Client configuration class."""

    streaming: bool = True
    """Whether to use streaming mode for message sending."""

    # If provided, caller owns lifecycle and no pooling is used.
    httpx_client: httpx.AsyncClient | None = None
    """Http client to use to connect to agent."""

    grpc_channel_factory: Callable[[str], Channel] | None = None
    """Generates a grpc connection channel for a given url."""

    supported_transports: list[TransportSchemes | str] = dataclasses.field(default_factory=list)

    pooling_enabled: bool = True
    """Whether to reuse underlying httpx/grpc connections when possible."""

    http_timeout: float | None = 60.0
    """Default request timeout for http-based transports (seconds)."""

    grpc_timeout: float | None = 60.0
    """Default request timeout for gRPC unary calls (seconds)."""

    retry_enabled: bool = False
    """Global retry switch (default off). Can be overridden via request.meta."""

    retry_max_attempts: int = 1
    retry_backoff_ms: int = 200
    retry_max_backoff_ms: int = 2000
    retry_jitter: float = 0.1
