"""Metadata models for Aduib RPC protocol v2."""

from __future__ import annotations

from typing import Any
from enum import StrEnum

from pydantic import BaseModel, field_validator


class AuthScheme(StrEnum):
    UNSPECIFIED = "unspecified"
    BEARER = "bearer"
    API_KEY = "api_key"
    MTLS = "mtls"
    BASIC = "basic"

    @classmethod
    def from_proto(cls, value: Any) -> "AuthScheme":
        return cls._from_wire(value)

    @classmethod
    def from_thrift(cls, value: Any) -> "AuthScheme":
        return cls._from_wire(value)

    @classmethod
    def _from_wire(cls, value: Any) -> "AuthScheme":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.UNSPECIFIED
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "bearer":
                return cls.BEARER
            if key == "api_key":
                return cls.API_KEY
            if key == "mtls":
                return cls.MTLS
            if key == "basic":
                return cls.BASIC
            if key == "unspecified":
                return cls.UNSPECIFIED
            try:
                raw = int(raw)
            except Exception:
                return cls.UNSPECIFIED
        try:
            num = int(raw)
        except Exception:
            return cls.UNSPECIFIED
        if num == 1:
            return cls.BEARER
        if num == 2:
            return cls.API_KEY
        if num == 3:
            return cls.MTLS
        return cls.UNSPECIFIED

    @classmethod
    def to_proto(cls, value: "AuthScheme | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def to_thrift(cls, value: "AuthScheme | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def _to_wire(cls, value: "AuthScheme | str | int | None") -> int:
        if value is None:
            return 0
        if isinstance(value, cls):
            if value == cls.BEARER:
                return 1
            if value == cls.API_KEY:
                return 2
            if value == cls.MTLS:
                return 3
            return 0
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "bearer":
                return 1
            if key == "api_key":
                return 2
            if key == "mtls":
                return 3
            if key == "basic":
                return 0
            if key == "unspecified":
                return 0
            try:
                raw = int(raw)
            except Exception:
                return 0
        try:
            num = int(raw)
        except Exception:
            return 0
        if 0 <= num <= 3:
            return num
        return 0


class ContentType(StrEnum):
    JSON = "application/json"
    MSGPACK = "application/msgpack"
    PROTOBUF = "application/protobuf"
    AVRO = "application/avro"

    @classmethod
    def from_proto(cls, value: Any) -> "ContentType":
        return cls._from_wire(value)

    @classmethod
    def from_thrift(cls, value: Any) -> "ContentType":
        return cls._from_wire(value)

    @classmethod
    def _from_wire(cls, value: Any) -> "ContentType":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.JSON
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key in {"application/json", "json"}:
                return cls.JSON
            if key in {"application/msgpack", "msgpack"}:
                return cls.MSGPACK
            if key in {"application/protobuf", "protobuf"}:
                return cls.PROTOBUF
            if key in {"application/avro", "avro"}:
                return cls.AVRO
            try:
                raw = int(raw)
            except Exception:
                return cls.JSON
        try:
            num = int(raw)
        except Exception:
            return cls.JSON
        if num == 1:
            return cls.JSON
        if num == 2:
            return cls.MSGPACK
        if num == 3:
            return cls.PROTOBUF
        if num == 4:
            return cls.AVRO
        return cls.JSON

    @classmethod
    def to_proto(cls, value: "ContentType | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def to_thrift(cls, value: "ContentType | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def _to_wire(cls, value: "ContentType | str | int | None") -> int:
        if value is None:
            return 1
        if isinstance(value, cls):
            if value == cls.JSON:
                return 1
            if value == cls.MSGPACK:
                return 2
            if value == cls.PROTOBUF:
                return 3
            if value == cls.AVRO:
                return 4
            return 1
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key in {"application/json", "json"}:
                return 1
            if key in {"application/msgpack", "msgpack"}:
                return 2
            if key in {"application/protobuf", "protobuf"}:
                return 3
            if key in {"application/avro", "avro"}:
                return 4
            try:
                raw = int(raw)
            except Exception:
                return 1
        try:
            num = int(raw)
        except Exception:
            return 1
        if 0 <= num <= 4:
            return num
        return 1


class Compression(StrEnum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"
    LZ4 = "lz4"

    @classmethod
    def from_proto(cls, value: Any) -> "Compression | None":
        return cls._from_wire(value)

    @classmethod
    def from_thrift(cls, value: Any) -> "Compression | None":
        return cls._from_wire(value)

    @classmethod
    def _from_wire(cls, value: Any) -> "Compression | None":
        if isinstance(value, cls):
            return value
        if value is None:
            return None
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "none":
                return cls.NONE
            if key == "gzip":
                return cls.GZIP
            if key == "zstd":
                return cls.ZSTD
            if key == "lz4":
                return cls.LZ4
            try:
                raw = int(raw)
            except Exception:
                return None
        try:
            num = int(raw)
        except Exception:
            return None
        if num == 1:
            return cls.NONE
        if num == 2:
            return cls.GZIP
        if num == 3:
            return cls.ZSTD
        if num == 4:
            return cls.LZ4
        return None

    @classmethod
    def to_proto(cls, value: "Compression | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def to_thrift(cls, value: "Compression | str | int | None") -> int:
        return cls._to_wire(value)

    @classmethod
    def _to_wire(cls, value: "Compression | str | int | None") -> int:
        if value is None:
            return 0
        if isinstance(value, cls):
            if value == cls.NONE:
                return 1
            if value == cls.GZIP:
                return 2
            if value == cls.ZSTD:
                return 3
            if value == cls.LZ4:
                return 4
            return 0
        raw = getattr(value, "value", value)
        if isinstance(raw, str):
            key = raw.lower()
            if key == "none":
                return 1
            if key == "gzip":
                return 2
            if key == "zstd":
                return 3
            if key == "lz4":
                return 4
            try:
                raw = int(raw)
            except Exception:
                return 0
        try:
            num = int(raw)
        except Exception:
            return 0
        if 0 <= num <= 4:
            return num
        return 0


class AuthContext(BaseModel):
    """Authentication context for a request.

    Attributes:
        scheme: Authentication scheme used by the client.
        credentials: Sensitive credential material that must never be logged.
        principal: Authenticated principal identifier, such as a user ID.
        roles: Roles granted to the authenticated principal.
    """

    scheme: AuthScheme
    credentials: str | None = None
    principal: str | None = None
    principal_type: str | None = None
    roles: list[str] | None = None

    @classmethod
    def create(cls, scheme: AuthScheme, credentials: str,principal: str | None = None,
               principal_type: str | None = None,
               roles: list[str] | None = None) -> AuthContext:
        """Helper to create AuthContext."""
        return cls(
            scheme=scheme,
            credentials=credentials,
            principal=principal,
            principal_type=principal_type,
            roles=roles,
        )


class RequestMetadata(BaseModel):
    """Request-scoped metadata for Protocol v2.0.

    Attributes:
        timestamp_ms: Unix timestamp in milliseconds for when the request was created.
        client_id: Client identifier for the caller.
        client_version: Version string for the client.
        auth: Authentication context for the request.
        tenant_id: Tenant identifier for multi-tenant scenarios.
        content_type: Content type of the request payload.
        accept: Content types that the client can accept in the response.
        compression: Compression applied to the request payload.
        headers: Additional request headers.
    """

    timestamp_ms: int
    client_id: str | None = None
    client_version: str | None = None
    auth: AuthContext | None = None
    tenant_id: str | None = None
    content_type: ContentType = ContentType.JSON
    accept: list[ContentType] | None = None
    compression: Compression | None = None
    headers: dict[str, str] | None = None
    long_task: bool = False
    long_task_method: str | None = None
    long_task_timeout: int | None = None


    @classmethod
    def create(cls, tenant_id: str,
               client_id: str,
                *,
                auth: AuthContext | None = None,
               content_type: ContentType = ContentType.JSON,
               accept: list[ContentType] | None = None,
               compression: Compression | None = None,
               headers: dict[str, str] | None = None,
               long_task: bool=False,
               long_task_method: str | None = None,
                long_task_timeout: int | None = None
               ) -> RequestMetadata:
          """Helper to create basic RequestMetadata with current timestamp."""
          import time

          return cls(
                timestamp_ms=int(time.time() * 1000),
                tenant_id=tenant_id,
                client_id=client_id,
                client_version="2.0.0",
                auth=auth,
                content_type=content_type,
                accept=accept,
                compression=compression,
                headers=headers,
                long_task=long_task,
                long_task_method=long_task_method,
               long_task_timeout=long_task_timeout,
          )


class Pagination(BaseModel):
    """Pagination metadata for a paged response.

    Attributes:
        total: Total number of records.
        page: Current page number starting from 1.
        page_size: Number of records per page.
        has_next: Whether more pages are available.
        cursor: Cursor token for cursor-based pagination.
    """

    total: int
    page: int
    page_size: int
    has_next: bool
    cursor: str | None = None

    @field_validator("page")
    @classmethod
    def validate_page(cls, value: Any) -> int:
        if value < 1:
            raise ValueError("page must be greater than or equal to 1")
        return int(value)

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, value: Any) -> int:
        if value < 1:
            raise ValueError("page_size must be greater than or equal to 1")
        return int(value)


class RateLimitInfo(BaseModel):
    """Rate limit information for the response.

    Attributes:
        limit: Total rate limit quota for the time window.
        remaining: Remaining quota for the time window.
        reset_at_ms: Unix timestamp in milliseconds when the limit resets.
    """

    limit: int
    remaining: int
    reset_at_ms: int


class ResponseMetadata(BaseModel):
    """Response-scoped metadata for Protocol v2.0.

    Attributes:
        timestamp_ms: Unix timestamp in milliseconds when the response was generated.
        duration_ms: Total processing duration in milliseconds.
        server_id: Identifier of the responding server instance.
        server_version: Version string for the server.
        pagination: Pagination metadata for paged responses.
        rate_limit: Rate limit information for the response.
        headers: Additional response headers.
    """

    timestamp_ms: int
    duration_ms: int | None = None
    server_id: str | None = None
    server_version: str | None = None
    pagination: Pagination | None = None
    rate_limit: RateLimitInfo | None = None
    headers: dict[str, str] | None = None

