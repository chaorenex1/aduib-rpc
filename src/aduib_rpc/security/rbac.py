from __future__ import annotations

"""Simple RBAC model with in-memory permission checks."""

from dataclasses import dataclass, field
from typing import Iterable, Protocol

__all__ = [
    "Permission",
    "Role",
    "Subject",
    "PermissionChecker",
    "InMemoryPermissionChecker",
]


@dataclass(frozen=True, slots=True)
class Permission:
    """Permission tuple for resource/action pairs."""

    resource: str
    action: str


@dataclass(frozen=True, slots=True)
class Role:
    """Role definition with a name and permissions set."""

    name: str
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", frozenset(self.permissions))


@dataclass(frozen=True, slots=True)
class Subject:
    """Subject definition with an identity and assigned role names."""

    id: str
    type: str
    roles: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", frozenset(self.roles))


class PermissionChecker(Protocol):
    """Interface for permission checks."""

    def has_permission(self, subject: Subject, permission: Permission) -> bool:
        """Return True when the subject has the specified permission."""
        ...


class InMemoryPermissionChecker(PermissionChecker):
    """In-memory permission checker that resolves role permissions."""

    def __init__(self, roles: Iterable[Role] | None = None) -> None:
        self._roles: dict[str, Role] = {role.name: role for role in (roles or [])}

    def add_role(self, role: Role) -> None:
        """Register or replace a role definition."""

        self._roles[role.name] = role

    def remove_role(self, name: str) -> None:
        """Remove a role definition by name."""

        self._roles.pop(name, None)

    def has_permission(self, subject: Subject, permission: Permission) -> bool:
        """Check whether a subject has a permission via assigned roles."""

        for role_name in subject.roles:
            role = self._roles.get(role_name)
            if role and permission in role.permissions:
                return True
        return False
