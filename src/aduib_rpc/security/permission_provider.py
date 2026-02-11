from __future__ import annotations

from dataclasses import dataclass

from aduib_rpc.client.auth import CredentialsProvider
from aduib_rpc.protocol.v2 import AuthScheme
from aduib_rpc.security.validators import PermissionValidator, TokenValidator
from aduib_rpc.server import get_runtime
from aduib_rpc.utils.constant import SecuritySchemes


@dataclass(slots=True)
class PermissionProvider:
    """Injects auth/permission handlers into RpcApp and runtime."""

    credentials_provider: CredentialsProvider
    token_validator: TokenValidator
    permission_validator: PermissionValidator
    auth_scheme: AuthScheme = AuthScheme.BEARER
    security_scheme: SecuritySchemes = SecuritySchemes.OAuth2

    def apply(self, app) -> None:
        """Bind provider to app and runtime."""
        app.permission_provider = self
        runtime = get_runtime()
        runtime.set_credentials_provider(self.credentials_provider)
        runtime.auth_scheme = self.auth_scheme
        runtime.security_scheme = self.security_scheme
