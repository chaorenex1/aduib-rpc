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
