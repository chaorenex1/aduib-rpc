"""RBAC (Role-Based Access Control) module for fine-grained authorization.

This module provides a complete RBAC implementation with:
- Resource and action-based permissions
- Role definitions with allowed/denied methods
- Principal (Subject) with roles and metadata
- Wildcard resource matching
- Permission checking with audit support
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

@dataclass(frozen=True, slots=True)
class Permission:
    """Permission tuple for resource/action pairs.

    Supports wildcards in both resource and action:
    - "user:*" matches all user actions
    - "*:read" matches read on all resources
    - "*:*" matches everything

    Attributes:
        resource: Resource identifier (supports wildcards)
        action: Action identifier (supports wildcards)
    """

    resource: str
    action: str

    def matches(self, permission: Permission) -> bool:
        """Check if this permission matches another (wildcard aware)."""
        resource_match = fnmatch.fnmatch(permission.resource, self.resource)
        action_match = fnmatch.fnmatch(permission.action, self.action)
        return resource_match and action_match


@dataclass(frozen=True, slots=True)
class Role:
    """Role definition with permissions and method restrictions.

    Attributes:
        name: Unique role identifier
        permissions: Set of permissions granted by this role
        allowed_methods: RPC method patterns explicitly allowed
        denied_methods: RPC method patterns explicitly denied (overrides allowed)
        metadata: Additional role attributes
    """

    name: str
    permissions: frozenset[Permission] = field(default_factory=frozenset)
    allowed_methods: frozenset[str] = field(default_factory=frozenset)
    denied_methods: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", frozenset(self.permissions))
        object.__setattr__(self, "allowed_methods", frozenset(self.allowed_methods))
        object.__setattr__(self, "denied_methods", frozenset(self.denied_methods))

    def has_permission(self, permission: Permission) -> bool:
        """Check if this role grants the given permission."""
        return any(p.matches(permission) for p in self.permissions)

    def is_method_allowed(self, method: str) -> bool:
        """Check if a method is allowed for this role.

        Denied methods take precedence over allowed methods.
        If no explicit rules, method is allowed.
        """
        # Check denied patterns first
        for pattern in self.denied_methods:
            if fnmatch.fnmatch(method, pattern):
                return False
        # If allowed patterns are defined, check them
        if self.allowed_methods:
            return any(fnmatch.fnmatch(method, pattern) for pattern in self.allowed_methods)
        return True


@dataclass(frozen=True, slots=True)
class Principal:
    """Principal (Subject) representing a user or service.

    Attributes:
        id: Unique principal identifier
        type: Principal type (e.g., "user", "service", "api_key")
        roles: Set of role names assigned to this principal
        metadata: Additional principal attributes (e.g., org_id, email)
    """

    id: str
    type: str
    roles: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", frozenset(self.roles))

    def has_role(self, role_name: str) -> bool:
        """Check if principal has a specific role."""
        return role_name in self.roles

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """Get metadata attribute with default."""
        return self.metadata.get(key, default)


class PermissionChecker:
    """Interface for permission checks."""

    def has_permission(
        self,
        principal: Principal,
        permission: Permission | tuple[str, str],
    ) -> bool:
        """Check if principal has the given permission.

        Args:
            principal: The principal to check
            permission: Permission or (resource, action) tuple

        Returns:
            True if permission is granted
        """
        raise NotImplementedError

    def can_invoke_method(
        self,
        principal: Principal,
        method: str,
    ) -> bool:
        """Check if principal can invoke a specific RPC method.

        Args:
            principal: The principal to check
            method: RPC method path (e.g., "rpc.v2/users/UserService")

        Returns:
            True if method invocation is allowed
        """
        raise NotImplementedError


class InMemoryPermissionChecker(PermissionChecker):
    """In-memory permission checker with role resolution.

    Thread-safe for read operations; add_role/remove_role should be
    called during initialization only.
    """

    def __init__(self, roles: Iterable[Role] | None = None) -> None:
        """Initialize with a set of available roles.

        Args:
            roles: Initial set of roles (default: empty)
        """
        self._roles: dict[str, Role] = {role.name: role for role in (roles or [])}
        self._superadmin_role: str | None = None

    def add_role(self, role: Role) -> None:
        """Register or replace a role definition."""
        self._roles[role.name] = role

    def remove_role(self, name: str) -> None:
        """Remove a role definition by name."""
        self._roles.pop(name, None)

    def set_superadmin_role(self, role_name: str) -> None:
        """Set the superadmin role that bypasses all permission checks."""
        self._superadmin_role = role_name

    def has_permission(
        self,
        principal: Principal,
        permission: Permission | tuple[str, str],
    ) -> bool:
        """Check if principal has the given permission.

        A superadmin bypasses all checks. Otherwise, permissions from
        all assigned roles are unioned.
        """
        if isinstance(permission, tuple):
            permission = Permission(resource=permission[0], action=permission[1])

        # Superadmin bypass
        if self._superadmin_role and principal.has_role(self._superadmin_role):
            return True

        # Check all roles
        for role_name in principal.roles:
            role = self._roles.get(role_name)
            if role and role.has_permission(permission):
                return True
        return False

    def can_invoke_method(self, principal: Principal, method: str) -> bool:
        """Check if principal can invoke a specific RPC method.

        Superadmin bypass applies. Denied methods in any role block
        access regardless of other roles.
        """
        # Superadmin bypass
        if self._superadmin_role and principal.has_role(self._superadmin_role):
            return True

        # Check denied methods first (any role denial blocks)
        for role_name in principal.roles:
            role = self._roles.get(role_name)
            if role:
                # Check denied patterns
                for pattern in role.denied_methods:
                    if fnmatch.fnmatch(method, pattern):
                        return False

        # Check allowed methods
        has_allowed_rules = False
        for role_name in principal.roles:
            role = self._roles.get(role_name)
            if role and role.allowed_methods:
                has_allowed_rules = True
                for pattern in role.allowed_methods:
                    if fnmatch.fnmatch(method, pattern):
                        return True

        # If no allowed rules defined, permit (default allow)
        return not has_allowed_rules

    def get_role(self, name: str) -> Role | None:
        """Get a role definition by name."""
        return self._roles.get(name)

    def list_roles(self) -> list[str]:
        """List all available role names."""
        return list(self._roles.keys())


class RbacPolicy(InMemoryPermissionChecker):
    """RBAC policy with enforcement and audit hooks.

    Extends InMemoryPermissionChecker with:
    - Custom enforcement logic
    - Audit callbacks
    - Default role assignment
    """

    def __init__(
        self,
        roles: Iterable[Role] | None = None,
        default_role: str | None = None,
        audit_callback: Callable[[str, Principal, Permission, bool], None] | None = None,
    ) -> None:
        """Initialize RBAC policy.

        Args:
            roles: Initial set of roles
            default_role: Default role for principals without roles
            audit_callback: Called on each permission check
        """
        super().__init__(roles)
        self._default_role = default_role
        self._audit_callback = audit_callback

    def set_default_role(self, role_name: str) -> None:
        """Set the default role for unassigned principals."""
        self._default_role = role_name

    def set_audit_callback(
        self,
        callback: Callable[[str, Principal, Permission, bool], None],
    ) -> None:
        """Set the audit callback.

        The callback receives: (event_type, principal, permission, result)
        """
        self._audit_callback = callback

    def _audit(
        self,
        event_type: str,
        principal: Principal,
        permission: Permission,
        result: bool,
    ) -> None:
        """Emit audit event if callback is configured."""
        if self._audit_callback:
            try:
                self._audit_callback(event_type, principal, permission, result)
            except Exception:
                # Audit failures should not block authorization
                pass

    def has_permission(
        self,
        principal: Principal,
        permission: Permission | tuple[str, str],
    ) -> bool:
        """Check permission with audit logging."""
        if isinstance(permission, tuple):
            permission = Permission(resource=permission[0], action=permission[1])

        result = super().has_permission(principal, permission)
        self._audit("permission_check", principal, permission, result)
        return result

    def require_permission(
        self,
        principal: Principal,
        permission: Permission | tuple[str, str],
    ) -> None:
        """Raise PermissionDeniedError if permission is not granted."""
        if isinstance(permission, tuple):
            permission = Permission(resource=permission[0], action=permission[1])

        if not self.has_permission(principal, permission):
            self._audit("permission_denied", principal, permission, False)
            raise PermissionDeniedError(
                principal_id=principal.id,
                resource=permission.resource,
                action=permission.action,
            )

    def create_principal(
        self,
        principal_id: str,
        principal_type: str = "user",
        roles: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Principal:
        """Create a Principal with default role if applicable.

        Args:
            principal_id: Unique principal identifier
            principal_type: Type of principal
            roles: Assigned role names
            metadata: Additional attributes

        Returns:
            A Principal instance
        """
        role_set = set(roles or [])
        if self._default_role and not role_set:
            role_set.add(self._default_role)

        return Principal(
            id=principal_id,
            type=principal_type,
            roles=frozenset(role_set),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class PermissionDeniedError(Exception):
    """Raised when a permission check fails."""

    principal_id: str
    resource: str
    action: str

    def __str__(self) -> str:
        return f"Principal '{self.principal_id}' denied '{self.action}' on '{self.resource}'"

    @property
    def message(self) -> str:
        return str(self)
