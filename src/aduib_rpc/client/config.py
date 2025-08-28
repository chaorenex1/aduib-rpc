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
    httpx_client: httpx.AsyncClient | None = None
    """Http client to use to connect to agent."""

    grpc_channel_factory: Callable[[str], Channel] | None = None
    """Generates a grpc connection channel for a given url."""

    supported_transports: list[TransportSchemes | str] = dataclasses.field(
        default_factory=list
    )