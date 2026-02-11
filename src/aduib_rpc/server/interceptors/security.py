"""Security interceptor for server-side request processing.

This module provides security-related interceptors including:
- RBAC (Role-Based Access Control) authorization
- Audit logging for security events
- Principal extraction from requests
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import inspect
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from aduib_rpc.protocol.v2 import RpcError
from aduib_rpc.exceptions import InvalidTokenError, TokenExpiredError, UnauthenticatedError
from aduib_rpc.telemetry.audit import AuditLogger
from aduib_rpc.security.rbac import (
    Permission,
    Principal,
    RbacPolicy,
)
from aduib_rpc.security.validators import (
    TokenValidator,
    PermissionValidator,
    MetadataTokenValidator,
    RbacPermissionValidator,
)
from aduib_rpc.protocol.v2.errors import ERROR_CODE_NAMES, ErrorCode
from aduib_rpc.server.context import InterceptContext, ServerContext, ServerInterceptor
from aduib_rpc.server.rpc_execution import MethodName, get_runtime
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
    anonymous_methods: set[str] = field(
        default_factory=lambda: {
            "health",
            "metrics",
            "ping",
        }
    )


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
        token_validator: TokenValidator | None = None,
        permission_validator: PermissionValidator | None = None,
    ):
        """Initialize the security interceptor.

        Args:
            config: Security configuration.
            rbac_policy: RBAC policy for authorization.
            audit_logger: Audit logger for security events.
            token_validator: Token validator implementation.
            permission_validator: Permission validator implementation.
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
                permissions=frozenset([Permission(resource="*", action="*")]),
                allowed_methods=frozenset(["*"]),
            )
            self._rbac_policy = RbacPolicy(
                roles=[admin_role],
                default_role=self.config.default_role,
            )

        # Set superadmin role
        if self.config.superadmin_role:
            self._rbac_policy.set_superadmin_role(self.config.superadmin_role)

        self._token_validator = token_validator or MetadataTokenValidator()
        self._permission_validator = permission_validator or RbacPermissionValidator(self._rbac_policy)

        # Initialize audit logger
        self._audit_logger = audit_logger or AuditLogger()

    @asynccontextmanager
    async def intercept(self, ctx: InterceptContext) -> AsyncIterator[None]:
        """Intercept the request and apply security checks."""
        method = ctx.request.method or ""

        if self._is_anonymous_method(method):
            yield
            return

        permission = self._get_permission_for_method(method)
        token = self._extract_token(ctx.request, ctx.server_context)

        if token is None:
            if self.config.require_auth or self.config.rbac_enabled:
                self._abort_with_error(
                    ctx,
                    ErrorCode.UNAUTHENTICATED,
                    "Unauthenticated",
                )
                yield
                return
            principal = self._extract_principal(ctx.request, ctx.server_context)
        else:
            try:
                principal = await self._validate_token(token, ctx, method)
            except TokenExpiredError:
                self._abort_with_error(
                    ctx,
                    ErrorCode.TOKEN_EXPIRED,
                    "Token expired",
                )
                yield
                return
            except InvalidTokenError:
                self._abort_with_error(
                    ctx,
                    ErrorCode.INVALID_TOKEN,
                    "Invalid token",
                )
                yield
                return
            except UnauthenticatedError:
                self._abort_with_error(
                    ctx,
                    ErrorCode.UNAUTHENTICATED,
                    "Unauthenticated",
                )
                yield
                return
            except Exception:
                self._abort_with_error(
                    ctx,
                    ErrorCode.INVALID_TOKEN,
                    "Invalid token",
                )
                yield
                return

        if principal is None:
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
            if permission is None:
                self._deny_permission(ctx, principal, method, permission, reason="permission_not_defined")
                yield
                return
            allowed = await self._check_permission(principal, permission, ctx, method)
            if not allowed:
                self._deny_permission(ctx, principal, method, permission, reason="insufficient_permissions")
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

    def _extract_principal(self, request: AduibRpcRequest, context: ServerContext) -> Principal:
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
            principal_roles = auth.roles or []

            return Principal(
                id=principal_id,
                type=principal_type,
                roles=frozenset(principal_roles) if isinstance(principal_roles, (list, set, tuple)) else frozenset(),
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

    def _extract_token(self, request: AduibRpcRequest, context: ServerContext) -> str | None:
        auth = request.metadata.auth if request.metadata else None
        if auth and auth.credentials:
            return str(auth.credentials)
        state_auth = context.state.get("auth") if hasattr(context, "state") else None
        if isinstance(state_auth, dict):
            token = state_auth.get("token") or state_auth.get("api_key")
            if token:
                return str(token)
        return None

    def _get_permission_for_method(self, method: str) -> Permission | None:
        try:
            parsed = MethodName.parse_compat(method)
        except Exception:
            return None
        runtime = get_runtime()
        service_func = runtime.service_funcs.get(parsed.handler)
        if service_func is None:
            legacy_key = f"{parsed.service}.{parsed.handler}"
            service_func = runtime.service_funcs.get(legacy_key)
        if service_func is None:
            return None
        metadata = getattr(service_func, "metadata", {}) or {}
        return self._normalize_permission_data(metadata.get("permission"))

    def _normalize_permission_data(self, value: Any) -> Permission | None:
        if value is None:
            return None
        if isinstance(value, Permission):
            return value
        if isinstance(value, dict):
            resource = value.get("resource")
            action = value.get("action")
            if resource is None or action is None:
                return None
            return Permission(resource=str(resource), action=str(action))
        if isinstance(value, tuple | list) and len(value) == 2:
            return Permission(resource=str(value[0]), action=str(value[1]))
        return None

    async def _validate_token(self, token: str, ctx: InterceptContext, method: str) -> Principal:
        validator = self._token_validator
        result = validator.validate(
            token,
            method=method,
            request=ctx.request,
            context=ctx.server_context,
        )
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _check_permission(
        self,
        principal: Principal,
        permission: Permission,
        ctx: InterceptContext,
        method: str,
    ) -> bool:
        validator = self._permission_validator
        result = validator.check(
            principal,
            permission=permission,
            method=method,
            request=ctx.request,
            context=ctx.server_context,
        )
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    def _abort_with_error(
        self,
        ctx: InterceptContext,
        code: ErrorCode,
        message: str,
    ) -> None:
        code_int = int(code)
        ctx.abort(
            RpcError(
                code=code_int,
                name=ERROR_CODE_NAMES.get(code_int, "UNKNOWN"),
                message=message,
            )
        )

    def _deny_permission(
        self,
        ctx: InterceptContext,
        principal: Principal,
        method: str,
        permission: Permission | None,
        *,
        reason: str,
    ) -> None:
        if self.config.audit_enabled:
            self._log_security_event(
                ctx,
                principal=principal,
                event_type="access_denied",
                details={
                    "request_id": ctx.request.id,
                    "method": method,
                    "roles": list(principal.roles),
                    "reason": reason,
                },
            )

        code = int(ErrorCode.PERMISSION_DENIED)
        details = []
        if permission is not None:
            details.append(
                {
                    "type": "aduib.rpc/permission_denied",
                    "field": "permission",
                    "reason": reason,
                    "metadata": {
                        "principal_id": principal.id,
                        "resource": permission.resource,
                        "action": permission.action,
                    },
                }
            )
        ctx.abort(
            RpcError(
                code=code,
                name=ERROR_CODE_NAMES.get(code, "UNKNOWN"),
                message=f"Access denied to method: {method}",
                details=details or None,
            )
        )

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
