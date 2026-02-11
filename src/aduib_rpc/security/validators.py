from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from aduib_rpc.exceptions import InvalidTokenError
from aduib_rpc.security.rbac import Permission, Principal, RbacPolicy

if TYPE_CHECKING:
    from aduib_rpc.protocol.v2.types import AduibRpcRequest
    from aduib_rpc.server.context import ServerContext


class TokenValidator(ABC):
    """Interface for token validation."""

    @abstractmethod
    async def validate(
        self,
        token: str,
        *,
        method: str,
        request: "AduibRpcRequest",
        context: "ServerContext",
    ) -> Principal:
        """Validate token and return Principal."""


class PermissionValidator(ABC):
    """Interface for permission checks."""

    @abstractmethod
    async def check(
        self,
        principal: Principal,
        *,
        permission: Permission,
        method: str,
        request: "AduibRpcRequest",
        context: "ServerContext",
    ) -> bool:
        """Return True if allowed, False otherwise."""


class MetadataTokenValidator(TokenValidator):
    """Extracts principal info from RequestMetadata.auth."""

    async def validate(
        self,
        token: str,
        *,
        method: str,
        request: "AduibRpcRequest",
        context: "ServerContext",
    ) -> Principal:
        auth = request.metadata.auth if request.metadata else None
        if auth and auth.principal:
            roles = auth.roles or []
            role_set = set(roles) if isinstance(roles, (list, set, tuple)) else set()
            principal_type = auth.principal_type or "user"
            return Principal(
                id=str(auth.principal),
                type=str(principal_type),
                roles=frozenset(role_set),
            )
        raise InvalidTokenError()


class RbacPermissionValidator(PermissionValidator):
    """Permission validator backed by RbacPolicy."""

    def __init__(self, policy: RbacPolicy) -> None:
        self._policy = policy

    async def check(
        self,
        principal: Principal,
        *,
        permission: Permission,
        method: str,
        request: "AduibRpcRequest",
        context: "ServerContext",
    ) -> bool:
        if not self._policy.can_invoke_method(principal, method):
            return False
        return self._policy.has_permission(principal, permission)
