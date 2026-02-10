"""Protocol version negotiation middleware.

This middleware now enforces v2-only traffic and rejects unsupported versions.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from aduib_rpc.protocol.v2.errors import ERROR_CODE_NAMES, ErrorCode
from aduib_rpc.protocol.v2.types import (
    AduibRpcRequest as V2Request,
    AduibRpcResponse as V2Response,
    RpcError,
)
from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor

logger = logging.getLogger(__name__)


class VersionNegotiationInterceptor(ServerInterceptor):
    """Interceptor that negotiates protocol version for v2-only traffic.

    This interceptor:
    1. Detects the protocol version from incoming requests
    2. Rejects unsupported versions
    3. Adds version information to the context
    """

    def order(self) -> int:
        """Order of the interceptor in the chain.

        Returns:
            An integer representing the order. Lower values run earlier.
        """
        return 2  # Run early to enforce versioning

    def __init__(
        self,
        server_versions: list[str] | None = None,
        default_version: str = "2.0",
    ):
        """Initialize the version negotiation interceptor.

        Args:
            server_versions: Protocol versions supported by this server.
            default_version: Default version to use if negotiation fails.
        """
        self.server_versions = server_versions
        self.default_version = default_version

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        """Intercept and validate the request version."""
        try:
            request_version = self._detect_version(ctx.request)

            if ctx.server_context:
                if not hasattr(ctx.server_context, "state"):
                    ctx.server_context.state = {}
                ctx.server_context.state["protocol_version"] = request_version
                ctx.server_context.state["negotiated_version"] = self.default_version

            if request_version != "2.0":
                code = int(ErrorCode.UNSUPPORTED_VERSION)
                ctx.abort(
                    RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message=f"Unsupported protocol version: {request_version}",
                    )
                )
            yield
        except Exception:
            logger.exception("Version negotiation failed")
            yield

    def _detect_version(self, request: Any) -> str:
        """Detect the protocol version from a request.

        Args:
            request: The request object.

        Returns:
            The detected version ("2.0", "1.0", or "unknown").
        """
        if isinstance(request, V2Request):
            return "2.0"

        if isinstance(request, dict):
            return request.get("aduib_rpc", request.get("jsonrpc", "unknown"))

        if hasattr(request, "aduib_rpc"):
            return str(getattr(request, "aduib_rpc", "unknown"))

        return "unknown"


def normalize_request(request: Any) -> V2Request:
    """Normalize any request format to v2.

    Args:
        request: Request in v2 format or dict.

    Returns:
        A normalized v2 request.
    """
    if isinstance(request, V2Request):
        return request

    if isinstance(request, dict):
        version = request.get("aduib_rpc", "unknown")
        if version == "2.0":
            return V2Request(**request)
        raise ValueError(f"Unsupported protocol version: {version}")

    raise TypeError(f"Cannot normalize {type(request)} to V2Request")


def normalize_response(
    response: V2Response,
    client_version: str = "2.0",
) -> V2Response:
    """Return the v2 response without conversion.

    Args:
        response: The v2 response.
        client_version: The client's protocol version.

    Returns:
        The v2 response.
    """
    return response


def negotiate_client_version(
    client_versions: list[str] | None,
    server_versions: list[str] | None = None,
) -> str:
    """Negotiate the protocol version between client and server.

    Args:
        client_versions: Versions supported by the client.
        server_versions: Versions supported by the server.

    Returns:
        The negotiated version.
    """
    if server_versions is None:
        server_versions = ["2.0"]

    if client_versions is None:
        client_versions = ["2.0"]

    for version in client_versions:
        if version in server_versions:
            return version

    return "2.0"

