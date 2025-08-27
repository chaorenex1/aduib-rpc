from pydantic import BaseModel

from aduib_rpc.utils.constant import AIProtocols, TransportSchemes


class ServiceInstance(BaseModel):
    """Represents a service instance in the discovery system."""
    service_name: str
    host: str
    port: int
    weight: int
    metadata: dict[str, str] | None = None
    protocol: AIProtocols
    scheme: TransportSchemes

    @property
    def url(self) -> str:
        """Constructs the URL for the service instance."""
        return f"{self.scheme.value}://{self.host}:{self.port}"

    @property
    def instance_id(self) -> str:
        """Returns the service instance ID."""
        return f"{self.service_name}_{self.host}_{self.port}"

    def get_metadata_value(self, key: str) -> str | None:
        """Retrieves a metadata value by key."""
        if self.metadata and key in self.metadata:
            return self.metadata[key]
        return None