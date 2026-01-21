"""Metadata models for Aduib RPC protocol v2."""

from __future__ import annotations

from typing import Any
from enum import StrEnum

from pydantic import BaseModel, field_validator


class AuthScheme(StrEnum):
    BEARER = "bearer"
    API_KEY = "api_key"
    MTLS = "mtls"
    BASIC = "basic"


class ContentType(StrEnum):
    JSON = "application/json"
    MSGPACK = "application/msgpack"
    PROTOBUF = "application/protobuf"
    AVRO = "application/avro"


class Compression(StrEnum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"
    LZ4 = "lz4"


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
    roles: list[str] | None = None


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


__all__ = [
    "AuthScheme",
    "ContentType",
    "Compression",
    "AuthContext",
    "RequestMetadata",
    "Pagination",
    "RateLimitInfo",
    "ResponseMetadata",
]
