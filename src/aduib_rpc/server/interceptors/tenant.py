"""Tenant isolation interceptor for multi-tenant runtime scoping.

This interceptor reads tenant_id from ServerContext.state and binds it to
the runtime context for the duration of request processing, ensuring
proper multi-tenant isolation.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor
from aduib_rpc.server.rpc_execution.runtime import with_tenant

logger = logging.getLogger(__name__)


class TenantInterceptor(ServerInterceptor):
    """Interceptor that binds tenant_id to the runtime context.

    This interceptor:
    1. Reads tenant_id from ServerContext.state
    2. Binds the tenant to the runtime using with_tenant()
    3. Ensures proper cleanup after request processing

    Usage:
        interceptor = TenantInterceptor()
        handler = DefaultRequestHandler(interceptors=[interceptor])
    """

    def order(self) -> int:
        """Order of the interceptor in the chain.

        Returns:
            An integer representing the order. Lower values run earlier.
        """
        return 1  # Run early to set tenant context

    def __init__(self, *, fallback_tenant: str = "default") -> None:
        """Initialize the tenant interceptor.

        Args:
            fallback_tenant: Default tenant to use if not specified in metadata.
        """
        self._fallback_tenant = fallback_tenant

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        """Extract tenant_id and bind to runtime context."""
        tenant_id = self._extract_tenant_id(ctx.server_context)
        logger.debug(
            "TenantInterceptor: tenant_id=%s, request_id=%s",
            tenant_id,
            ctx.request.id,
        )
        async with TenantScope(tenant_id):
            yield

    def _extract_tenant_id(self, context: ServerContext) -> str:
        if "tenant_id" in context.state:
            return str(context.state["tenant_id"])

        return self._fallback_tenant


class TenantScope:
    """Context manager for binding tenant to runtime during request handling.

    This is used by handlers/interceptors that need to execute code
    within a tenant-scoped runtime.

    Usage:
        async with TenantScope(tenant_id):
            # Code here runs with tenant-specific runtime
            result = await some_operation()
    """

    def __init__(self, tenant_id: str) -> None:
        """Initialize the tenant scope.

        Args:
            tenant_id: The tenant identifier to bind.
        """
        self._tenant_id = tenant_id
        self._scope = None

    async def __aenter__(self) -> "TenantScope":
        """Enter the tenant-scoped runtime context."""
        self._scope = with_tenant(self._tenant_id)
        self._scope.__enter__()
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        """Exit the tenant-scoped runtime context."""
        if self._scope:
            self._scope.__exit__(None, None, None)
