"""Metadata models for Aduib RPC protocol v2."""

from __future__ import annotations

from typing import Any
from enum import StrEnum

from pydantic import BaseModel


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
        headers: Additional request headers.
    """

    timestamp_ms: int
    client_id: str | None = None
    client_version: str | None = None
    auth: AuthContext | None = None
    tenant_id: str | None = None
    headers: dict[str, str] | None = None
    long_task: bool = False
    long_task_method: str | None = None
    long_task_timeout: int | None = None


    @classmethod
    def create(cls, tenant_id: str,
               client_id: str,
                *,
                auth: AuthContext | None = None,
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
                headers=headers,
                long_task=long_task,
                long_task_method=long_task_method,
               long_task_timeout=long_task_timeout,
          )


class ResponseMetadata(BaseModel):
    """Response-scoped metadata for Protocol v2.0.

    Attributes:
        timestamp_ms: Unix timestamp in milliseconds when the response was generated.
        duration_ms: Total processing duration in milliseconds.
        server_id: Identifier of the responding server instance.
        server_version: Version string for the server.
    """

    timestamp_ms: int
    duration_ms: int | None = None
    server_id: str | None = None
    server_version: str | None = None

    @classmethod
    def create(cls,
               duration_ms: int | None = None,
               server_id: str | None = None,
               server_version: str | None = None) -> ResponseMetadata:
          """Helper to create basic ResponseMetadata with current timestamp."""
          import time

          return cls(
                timestamp_ms=int(time.time() * 1000),
                duration_ms=duration_ms,
                server_id=server_id,
                server_version=server_version,
          )
