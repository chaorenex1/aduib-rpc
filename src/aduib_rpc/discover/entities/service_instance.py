"""Service discovery entities for Aduib RPC Protocol v2.0.

This module provides the v2 protocol entities for service discovery and
registration, matching the specification in docs/protocol_v2_specification.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import uuid
from pydantic import BaseModel, field_validator, Field

from aduib_rpc.protocol.v2.metadata import ContentType, Compression
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes


class HealthStatus(StrEnum):
    """Health status of a service instance."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class MethodDescriptor(BaseModel):
    """Description of an RPC method provided by a service.

    Attributes:
        name: Method name.
        input_type: Input message type.
        output_type: Output message type.
        streaming_input: Whether input is streamed.
        streaming_output: Whether output is streamed.
        idempotent: Whether the method is idempotent.
        deprecated: Whether the method is deprecated.
    """

    name: str
    full_name: str | None = None
    description: str | None = None
    client_stream: bool = False
    server_stream: bool = False
    bidirectional_stream: bool = False
    deprecated: bool = False
    version: str | None = None


class ServiceCapabilities(BaseModel):
    """Capabilities declared by a service instance.

    Attributes:
        protocol_versions: Supported protocol versions.
        content_types: Supported content types.
        compressions: Supported compression algorithms.
        methods: List of available methods.
    """

    protocol_versions: list[str] = ["2.0"]
    content_types: list[ContentType] = [ContentType.JSON,ContentType.MSGPACK]
    compressions: list[Compression] = [Compression.ZSTD,Compression.GZIP]
    methods: list[MethodDescriptor] | None = None
    streaming: bool = False
    bidirectional: bool = False


class ServiceInstance(BaseModel):
    """A service instance in the discovery system (v2 protocol).

    This matches the v2 protocol specification for service discovery.

    Attributes:
        instance_id: Globally unique instance identifier.
        service_name: Service name.
        version: Semantic version of the service.
        host: Host address.
        port: Port number.
        scheme: Transport scheme.
        health: Health status.
        last_health_check_ms: Last health check timestamp (ms).
        weight: Load balancing weight.
        zone: Availability zone.
        region: Geographic region.
        capabilities: Service capabilities.
        metadata: Instance metadata.
        tags: Instance tags.
        registered_at_ms: Registration timestamp (ms).
        ttl_seconds: Time-to-live for registration.
    """

    instance_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service_name: str
    version: str = "2.0.0"
    host: str
    port: int
    scheme: TransportSchemes = TransportSchemes.HTTPS
    protocol: AIProtocols = AIProtocols.AduibRpc
    health: HealthStatus = HealthStatus.UNKNOWN
    last_health_check_ms: int | None = None
    weight: int = 100
    zone: str | None = None
    region: str | None = None
    capabilities: ServiceCapabilities | None = None
    metadata: dict[str, str] | None = None
    tags: list[str] | None = None
    registered_at_ms: int | None = None
    ttl_seconds: int = 30

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, value: int) -> int:
        if value < 0:
            raise ValueError("weight must be non-negative")
        return value

    @property
    def url(self) -> str:
        """Constructs the URL for the service instance."""
        scheme = self.scheme.value
        if scheme == "grpc":
            return f"{self.host}:{self.port}"
        return f"{scheme}://{self.host}:{self.port}"

    @property
    def is_healthy(self) -> bool:
        """Check if the instance is healthy."""
        return self.health == HealthStatus.HEALTHY

    @property
    def is_expired(self, ttl_multiplier: float = 1.5) -> bool:
        """Check if the registration has expired.

        Args:
            ttl_multiplier: Multiplier for TTL to determine expiration.

        Returns:
            True if the registration has expired.
        """
        if self.registered_at_ms is None:
            return False
        now_ms = int(datetime.now().timestamp() * 1000)
        expiry_ms = self.registered_at_ms + (self.ttl_seconds * 1000 * ttl_multiplier)
        return now_ms > expiry_ms

    @classmethod
    def create(
        cls,
        service_name: str,
        host: str,
        port: int,
        version: str = "1.0.0",
        instance_id: str | None = None,
        scheme: TransportSchemes = TransportSchemes.HTTPS,
        protocol: AIProtocols = AIProtocols.AduibRpc,
        **kwargs,
    ) -> "ServiceInstance":
        """Create a new service instance.

        Args:
            service_name: Service name.
            host: Host address.
            port: Port number.
            version: Service version.
            instance_id: Instance ID (generated if not provided).
            scheme: Transport scheme.
            protocol: Communication protocol.
            **kwargs: Additional attributes.

        Returns:
            A new ServiceInstance.
        """
        import uuid

        service_instance = cls(instance_id=instance_id or str(uuid.uuid4()), service_name=service_name, version=version, host=host,
                port=port, scheme=scheme, protocol=protocol, registered_at_ms=int(datetime.now().timestamp() * 1000),
                **kwargs, )
        service_instance.metadata=service_instance.to_dict()
        return service_instance


    def to_dict(self) -> dict[str, str]:
        """Convert the ServiceInstance class fields to a dictionary.

        Returns:
            A dictionary representation of the ServiceInstance fields.
        """
        result: dict[str, str] = {}
        for field_name, field_value in self.model_dump().items():
            if field_value is not None:
                result[field_name] = str(field_value)
        # Remove capabilities from metadata to avoid complexity
        result.pop("capabilities", None)
        return result

