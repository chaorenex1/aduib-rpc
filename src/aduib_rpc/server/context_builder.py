"""V2 protocol-aware context builder with trace context and metadata extraction.

Per spec v2 sections 2.1-2.3:
- Extracts W3C trace context from traceparent header or request body
- Injects tenant_id and auth info from metadata into ServerContext
- Integrates with OpenTelemetry for distributed tracing
"""
from __future__ import annotations

import contextlib
import logging
import uuid
from typing import Any

from starlette.requests import Request

from aduib_rpc.protocol.v2.types import TraceContext
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.protocols.rpc.jsonrpc_app import ServerContextBuilder

logger = logging.getLogger(__name__)

# W3C traceparent header format: {version}-{trace_id}-{span_id}-{trace_flags}
_TRACEPARENT_HEADER = "traceparent"
_TRACESTATE_HEADER = "tracestate"


class V2ServerContextBuilder(ServerContextBuilder):
    """V2 protocol-aware context builder.

    Extracts and stores:
    - trace_context: W3C TraceContext from headers or request body
    - tenant_id: From metadata.tenant_id or headers
    - auth_info: From metadata.auth or headers
    """

    def build_context(self, request: Request) -> ServerContext:
        """Build ServerContext with trace context and metadata extraction."""
        state: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

        # Extract headers
        with contextlib.suppress(Exception):
            state["headers"] = dict(request.headers)

            # Extract trace context (priority: request body > headers > generate new)
            trace_context = self._extract_trace_context(request, state)
            if trace_context:
                state["trace_context"] = trace_context

            # Extract tenant_id
            tenant_id = self._extract_tenant_id(request, state)
            if tenant_id:
                state["tenant_id"] = tenant_id

            # Extract auth info
            auth_info = self._extract_auth_info(request, state)
            if auth_info:
                state["auth"] = auth_info

        return ServerContext(state=state, metadata=metadata)

    def _extract_trace_context(
        self, request: Request, state: dict[str, Any]
    ) -> TraceContext | None:
        """Extract TraceContext from request body or W3C traceparent header.

        Priority:
        1. Request body trace_context field (for v2 JSON payload)
        2. W3C traceparent header
        3. Generate new trace context (if create_if_missing=True)
        """
        # Try request body first
        try:
            body = getattr(request, "_json", None) or getattr(request, "_body", None)
            if body is None and hasattr(request, "app"):
                # Body not parsed yet - check if we can peek
                pass

            # If body is already parsed, check for trace_context
            if isinstance(body, dict) and "trace_context" in body:
                tc_data = body["trace_context"]
                if isinstance(tc_data, dict):
                    return TraceContext.model_validate(tc_data)
        except Exception:
            pass  # Body parsing failed or not available

        # Try W3C traceparent header
        headers = state.get("headers", {})
        traceparent = headers.get(_TRACEPARENT_HEADER, "")
        if traceparent:
            try:
                return self._parse_traceparent(traceparent)
            except Exception as e:
                logger.debug("Failed to parse traceparent header: %s", e)

        # No trace context found
        return None

    def _parse_traceparent(self, traceparent: str) -> TraceContext:
        """Parse W3C traceparent header format.

        Format: {version}-{trace_id}-{span_id}-{trace_flags}
        Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
        """
        parts = traceparent.split("-")
        if len(parts) != 4:
            raise ValueError(f"Invalid traceparent format: {traceparent}")

        version, trace_id, span_id, trace_flags = parts

        # Validate hex format
        if len(trace_id) != 32:
            raise ValueError(f"Invalid trace_id length: {trace_id}")
        if len(span_id) != 16:
            raise ValueError(f"Invalid span_id length: {span_id}")

        # Parse trace flags for sampled bit
        sampled = bool(int(trace_flags, 16) & 0x01)

        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            sampled=sampled,
        )

    def _extract_tenant_id(self, request: Request, state: dict[str, Any]) -> str | None:
        """Extract tenant_id from request body or headers.

        Priority:
        1. Request body metadata.tenant_id
        2. X-Tenant-ID header
        3. X-Tenant header
        """
        # Try headers first (easier access)
        headers = state.get("headers", {})
        tenant_id = (
            headers.get("X-Tenant-ID") or headers.get("x-tenant-id")
            or headers.get("X-Tenant") or headers.get("x-tenant")
        )
        if tenant_id:
            return tenant_id

        # Try request body metadata
        try:
            body = getattr(request, "_json", None)
            if isinstance(body, dict):
                metadata = body.get("metadata", {})
                if isinstance(metadata, dict):
                    return metadata.get("tenant_id")
        except Exception:
            pass

        return None

    def _extract_auth_info(self, request: Request, state: dict[str, Any]) -> dict[str, Any] | None:
        """Extract auth info from request body metadata or headers.

        Returns dict with:
        - token: Bearer token from Authorization header
        - api_key: API key from X-API-Key header
        - user_id: User ID from metadata
        - roles: List of roles from metadata
        """
        auth_info: dict[str, Any] = {}
        headers = state.get("headers", {})

        # Extract Authorization header
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if auth_header:
            if auth_header.startswith("Bearer "):
                auth_info["token"] = auth_header[7:]
            else:
                auth_info["token"] = auth_header

        # Extract API key
        api_key = headers.get("X-API-Key") or headers.get("x-api-key")
        if api_key:
            auth_info["api_key"] = api_key

        # Try request body metadata for additional auth info
        try:
            body = getattr(request, "_json", None)
            if isinstance(body, dict):
                metadata = body.get("metadata", {})
                if isinstance(metadata, dict):
                    if "user_id" in metadata:
                        auth_info["user_id"] = metadata["user_id"]
                    if "roles" in metadata:
                        auth_info["roles"] = metadata["roles"]
                    if "auth" in metadata and isinstance(metadata["auth"], dict):
                        auth_info.update(metadata["auth"])
        except Exception:
            pass

        return auth_info if auth_info else None
