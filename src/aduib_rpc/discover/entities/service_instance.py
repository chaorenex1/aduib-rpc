from pydantic import BaseModel

from aduib_rpc.utils.constant import AIProtocols, TransportSchemes


class ServiceInstance(BaseModel):
    """Represents a service instance in the discovery system."""
    service_name: str
    host: str
    port: int
    weight: int=1
    metadata: dict[str, str] | None = {}
    protocol: AIProtocols = AIProtocols.AduibRpc
    scheme: TransportSchemes = TransportSchemes.GRPC

    @property
    def url(self) -> str:
        """Constructs the URL for the service instance."""
        return f"{TransportSchemes.get_real_scheme(self.scheme)}://{self.host}:{self.port}" if self.scheme!=TransportSchemes.GRPC else f"{self.host}:{self.port}"

    @property
    def instance_id(self) -> str:
        """Returns the service instance ID."""
        return f"{self.service_name}:{self.host}:{self.port}"

    def get_metadata_value(self, key: str) -> str | None:
        """Retrieves a metadata value by key."""
        if self.metadata and key in self.metadata:
            return self.metadata[key]
        return None
    def get_service_info(self) -> dict[str, str | int | dict[str, str]]:
        """Returns a dictionary representation of the service instance."""
        return self.metadata|{
            "service_name": self.service_name,
            "host": self.host,
            "port": str(self.port),
            "weight": str(self.weight),
            "protocol": self.protocol.value,
            "scheme": self.scheme.value,
        }