from enum import StrEnum, IntEnum

DEFAULT_STREAM_HEADER="x-rpc-streaming"
DEFAULT_STREAM_KEY="stream"
DEFAULT_RPC_PATH="/aduib_rpc"

class SecuritySchemes(StrEnum):
    """Security schemes for the OpenAPI specification
    APIKey
    """
    APIKey="APIKey"
    OAuth2="OAuth2"
    OpenIDConnect="OpenIDConnect"


class TransportSchemes(StrEnum):
    """Transport schemes for the OpenAPI specification
    HTTP
    WebSocket
    """
    HTTP="http"
    GRPC=""
    JSONRPC="http"


class AIProtocols(StrEnum):
    """AI protocol specification for the OpenAPI specification"""
    A2A="A2A"
    AduibRpc="AduibRpc"