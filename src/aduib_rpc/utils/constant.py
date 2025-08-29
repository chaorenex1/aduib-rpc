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

    @classmethod
    def to_original(cls,value: str):
        match value:
            case "APIKey":
                return SecuritySchemes.APIKey
            case "OAuth2":
                return SecuritySchemes.OAuth2
            case "OpenIDConnect":
                return SecuritySchemes.OpenIDConnect
            case _:
                raise ValueError(f"Unsupported security scheme: {value}")

class LoadBalancePolicy(IntEnum):
    """Load balancer policies for the gRPC client
    RoundRobin
    PickFirst
    """
    Random=0
    WeightedRoundRobin=1
    CONSISTENT_HASHING=2


class TransportSchemes(StrEnum):
    """Transport schemes for the OpenAPI specification
    HTTP
    WebSocket
    """
    HTTP="http"
    GRPC="grpc"
    JSONRPC="jsonrpc"

    @classmethod
    def to_original(cls,value: str):
        match value:
            case "http":
                return TransportSchemes.HTTP
            case "grpc":
                return TransportSchemes.GRPC
            case "jsonrpc":
                return TransportSchemes.JSONRPC
            case _:
                raise ValueError(f"Unsupported transport scheme: {value}")
    @classmethod
    def get_real_scheme(cls,scheme: 'TransportSchemes'):
        match scheme:
            case TransportSchemes.HTTP:
                return "http"
            case TransportSchemes.GRPC:
                return ""
            case TransportSchemes.JSONRPC:
                return "http"
            case _:
                raise ValueError(f"Unsupported transport scheme: {scheme}")


class AIProtocols(StrEnum):
    """AI protocol specification for the OpenAPI specification"""
    A2A="A2A"
    AduibRpc="AduibRpc"

    @classmethod
    def to_original(cls,value: str):
        match value:
            case "A2A":
                return AIProtocols.A2A
            case "AduibRpc":
                return AIProtocols.AduibRpc
            case _:
                raise ValueError(f"Unsupported AI protocol: {value}")