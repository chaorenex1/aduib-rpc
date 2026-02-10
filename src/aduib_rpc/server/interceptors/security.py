"""Security interceptor for server-side request processing.

This module provides security-related interceptors including:
- RBAC (Role-Based Access Control) authorization
- Audit logging for security events
- Principal extraction from requests
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from aduib_rpc.protocol.v2 import RpcError
from aduib_rpc.telemetry.audit import AuditLogger
from aduib_rpc.security.rbac import (
    InMemoryPermissionChecker,
    Permission,
    PermissionDeniedError,
    PermissionChecker,
    Principal,
    RbacPolicy,
)
from aduib_rpc.protocol.v2.errors import ERROR_CODE_NAMES, ErrorCode
from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor
from aduib_rpc.types import AduibRpcRequest


@dataclass
class SecurityConfig:
    """Configuration for security interceptor.

    Attributes:
        rbac_enabled: Whether RBAC authorization is enabled.
        audit_enabled: Whether audit logging is enabled.
        default_role: Default role for unauthenticated users.
        superadmin_role: Role name that bypasses all checks.
        require_auth: Whether authentication is required.
        anonymous_methods: Methods that don't require authentication.
    """

    rbac_enabled: bool = True
    audit_enabled: bool = True
    default_role: str = "anonymous"
    superadmin_role: str | None = "admin"
    require_auth: bool = False
    anonymous_methods: set[str] = field(default_factory=lambda: {
        "health",
        "metrics",
        "ping",
    })


class SecurityInterceptor(ServerInterceptor):
    """Server interceptor that applies security policies to incoming requests.

    This interceptor:
    1. Extracts the principal (user/service) from the request
    2. Checks RBAC authorization if enabled
    3. Logs audit events for security-relevant actions
    4. Returns errors for unauthorized/forbidden requests

    Usage:
        from aduib_rpc.server.interceptors import SecurityInterceptor, SecurityConfig
        from aduib_rpc.security.rbac import RbacPolicy, Role, Permission

        config = SecurityConfig(rbac_enabled=True, audit_enabled=True)
        policy = RbacPolicy(roles=[...])
        interceptor = SecurityInterceptor(config, rbac_policy=policy)

        # Use with request handler
        handler = DefaultRequestHandler(interceptors=[interceptor])
    """

    def order(self) -> int:
        """Order of the interceptor in the chain."""
        return 0

    def __init__(
        self,
        config: SecurityConfig | None = None,
        rbac_policy: RbacPolicy | None = None,
        audit_logger: AuditLogger | None = None,
        permission_checker: PermissionChecker | None = None,
    ):
        """Initialize the security interceptor.

        Args:
            config: Security configuration.
            rbac_policy: RBAC policy for authorization.
            audit_logger: Audit logger for security events.
            permission_checker: Permission checker (uses rbac_policy's if None).
        """
        self.config = config or SecurityConfig()
        # Initialize RBAC
        if rbac_policy:
            self._rbac_policy = rbac_policy
        else:
            # Create default policy with basic roles
            from aduib_rpc.security.rbac import Role

            admin_role = Role(
                name="admin",
                permissions=frozenset([
                    Permission(resource="*", action="*")
                ]),
                allowed_methods=frozenset(["*"]),
            )
            self._rbac_policy = RbacPolicy(
                roles=[admin_role],
                default_role=self.config.default_role,
            )

        # Set superadmin role
        if self.config.superadmin_role:
            self._rbac_policy.set_superadmin_role(self.config.superadmin_role)

        # Initialize permission checker
        self._permission_checker = permission_checker or InMemoryPermissionChecker(
            list(self._rbac_policy._roles.values())
        )

        # Initialize audit logger
        self._audit_logger = audit_logger or AuditLogger()

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        """Intercept the request and apply security checks."""
        method = ctx.request.method or ""

        if self._is_anonymous_method(method):
            yield
            return

        principal = self._extract_principal(ctx.request, ctx.server_context)
        ctx.server_context.state["principal"] = principal
        if hasattr(ctx.server_context, "metadata"):
            ctx.server_context.metadata["principal_id"] = principal.id
            ctx.server_context.metadata["principal_type"] = principal.type

        if self.config.audit_enabled:
            self._log_security_event(
                ctx,
                principal=principal,
                event_type="access_attempt",
                details={
                    "request_id": ctx.request.id,
                    "method": method,
                    "roles": list(principal.roles),
                },
            )

        if self.config.rbac_enabled:
            if not self._is_authorized(principal, method, ctx.request):
                if self.config.audit_enabled:
                    self._log_security_event(
                        ctx,
                        principal=principal,
                        event_type="access_denied",
                        details={
                            "request_id": ctx.request.id,
                            "method": method,
                            "roles": list(principal.roles),
                            "reason": "insufficient_permissions",
                        },
                    )

                code = int(ErrorCode.PERMISSION_DENIED)
                ctx.abort(
                    RpcError(
                        code=code,
                        name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                        message=f"Access denied to method: {method}",
                        details=[
                            {
                                "type": "aduib.rpc/permission_denied",
                                "field": "method",
                                "reason": "insufficient_permissions",
                                "metadata": {
                                    "principal_id": principal.id,
                                    "required_roles": list(self._get_required_roles(method)),
                                },
                            }
                        ],
                    )
                )
                yield
                return

        if self.config.audit_enabled:
            self._log_security_event(
                ctx,
                principal=principal,
                event_type="access_granted",
                details={
                    "request_id": ctx.request.id,
                    "method": method,
                    "roles": list(principal.roles),
                },
            )
        yield

    def _log_security_event(
        self,
        ctx: InterceptContext,
        *,
        principal: Principal,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        tenant_id = None
        if ctx.request.metadata is not None:
            tenant_id = ctx.request.metadata.tenant_id
        trace_id = ctx.request.trace_context.trace_id if ctx.request.trace_context else None
        request_id = str(ctx.request.id) if ctx.request.id is not None else None
        self._audit_logger.log_security_event(
            event_type=event_type,
            tenant_id=str(tenant_id) if tenant_id is not None else None,
            request_id=request_id,
            trace_id=trace_id,
            principal=principal.id,
            details=details,
        )

    def _is_anonymous_method(self, method: str) -> bool:
        """Check if a method allows anonymous access."""
        method_lower = method.lower()
        for pattern in self.config.anonymous_methods:
            pattern_lower = pattern.lower()
            if method_lower.endswith(pattern_lower) or f".{pattern_lower}" in method_lower:
                return True
        try:
            from aduib_rpc.server.rpc_execution.method_registry import MethodName

            parsed = MethodName.parse_compat(method)
            service = parsed.service.lower()
            handler = parsed.handler.lower()
            for pattern in self.config.anonymous_methods:
                pattern_lower = pattern.lower()
                if service.startswith(pattern_lower) or handler.startswith(pattern_lower):
                    return True
        except Exception:
            pass
        return False

    def _extract_principal(
        self, request: AduibRpcRequest, context: ServerContext
    ) -> Principal:
        """Extract principal from request and context.

        Args:
            request: The RPC request.
            context: The server context.

        Returns:
            The extracted principal.
        """
        # Try to get from context (might be set by auth middleware)
        if "principal" in context.state:
            principal = context.state["principal"]
            if principal is not None:
                return principal

        # Try to get from metadata
        auth = request.metadata.auth
        if auth:
            principal_id = auth.principal
            principal_type = auth.principal_type or "user"
            principal_roles = auth.roles or set()

            return Principal(
                id=principal_id,
                type=principal_type,
                roles=frozenset(principal_roles) if isinstance(principal_roles, set) else frozenset(),
            )
        if hasattr(context, "metadata"):
            principal_id = context.metadata.get("principal_id")
            principal_type = context.metadata.get("principal_type", "user")
            principal_roles = context.metadata.get("roles", set())

            if principal_id:
                return Principal(
                    id=principal_id,
                    type=principal_type,
                    roles=frozenset(principal_roles) if isinstance(principal_roles, set) else frozenset(),
                )

        # Return anonymous principal
        return Principal(
            id="anonymous",
            type="anonymous",
            roles=frozenset([self.config.default_role]) if self.config.default_role else frozenset(),
        )

    def _is_authorized(
        self, principal: Principal, method: str, request: AduibRpcRequest
    ) -> bool:
        """Check if principal is authorized to call the method.

        Args:
            principal: The principal to check.
            method: The method being called.
            request: The RPC request.

        Returns:
            True if authorized, False otherwise.
        """
        # Check method-level authorization
        if not self._permission_checker.can_invoke_method(principal, method):
            return False

        # If request has specific resource/action, check resource-level permissions
        if request.data and isinstance(request.data, dict):
            resource = request.data.get("resource")
            action = request.data.get("action", "call")

            if resource:
                permission = Permission(resource=resource, action=action)
                if not self._permission_checker.has_permission(principal, permission):
                    return False

        return True

    def _get_required_roles(self, method: str) -> set[str]:
        """Get roles that are required for a method."""
        # This is a simplified version - in practice, you might want to
        # configure this per-method
        return {"authenticated"}

    def refresh_from_config(self) -> None:
        """Sync RBAC policy defaults with the current config."""
        if hasattr(self._rbac_policy, "set_default_role"):
            self._rbac_policy.set_default_role(self.config.default_role)
        if self.config.superadmin_role:
            self._rbac_policy.set_superadmin_role(self.config.superadmin_role)


def create_security_interceptor(
    rbac_enabled: bool = True,
    audit_enabled: bool = True,
    default_role: str = "anonymous",
    superadmin_role: str | None = "admin",
) -> SecurityInterceptor:
    """Factory function to create a security interceptor with common configuration.

    Args:
        rbac_enabled: Whether RBAC is enabled.
        audit_enabled: Whether audit logging is enabled.
        default_role: Default role for anonymous users.
        superadmin_role: Role that bypasses all checks.

    Returns:
        Configured SecurityInterceptor instance.
    """
    config = SecurityConfig(
        rbac_enabled=rbac_enabled,
        audit_enabled=audit_enabled,
        default_role=default_role,
        superadmin_role=superadmin_role,
    )
    return SecurityInterceptor(config=config)

