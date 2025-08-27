from pydantic import BaseModel

from aduib_rpc.utils.constant import AIProtocols, TransportSchemes


class ServiceInstance(BaseModel):
    """Represents a service instance in the discovery system."""
    service_instance_id: str
    host: str
    port: int
    metadata: dict[str, str] | None = None
    protocol: AIProtocols
    scheme: TransportSchemes

    @property
    def get_url(self) -> str:
        """Constructs the URL for the service instance."""
        return f"{self.scheme.value}://{self.host}:{self.port}"

    def get_metadata_value(self, key: str) -> str | None:
        """Retrieves a metadata value by key."""
        if self.metadata and key in self.metadata:
            return self.metadata[key]
        return None