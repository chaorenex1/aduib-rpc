from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aduib_rpc.client import ClientRequestInterceptor
from aduib_rpc.client.auth import CredentialsProvider, InMemoryCredentialsProvider
from aduib_rpc.client.auth.interceptor import AuthInterceptor
from aduib_rpc.server.rpc_execution.service_func import ServiceFunc


@dataclass(slots=True)
class RpcRuntime:
    """Holds mutable runtime registries.

    Design goals:
    - make state explicit and resettable for tests
    - allow future per-server/per-client runtime instances
    - keep behavior compatible with the existing module-level globals
    """

    service_instances: dict[str, Any] = field(default_factory=dict)
    client_instances: dict[str, Any] = field(default_factory=dict)

    service_funcs: dict[str, ServiceFunc] = field(default_factory=dict)
    client_funcs: dict[str, ServiceFunc] = field(default_factory=dict)

    interceptors: list[ClientRequestInterceptor] = field(default_factory=list)
    credentials_provider: CredentialsProvider | None = None

    def reset(self) -> None:
        self.service_instances.clear()
        self.client_instances.clear()
        self.service_funcs.clear()
        self.client_funcs.clear()
        self.interceptors.clear()
        self.credentials_provider = None

    def enable_auth(self) -> None:
        if not self.credentials_provider:
            self.credentials_provider = InMemoryCredentialsProvider()
        has_auth = any(isinstance(i, AuthInterceptor) for i in self.interceptors)
        if not has_auth:
            self.interceptors.append(AuthInterceptor(self.credentials_provider))


_global_runtime = RpcRuntime()


def get_runtime() -> RpcRuntime:
    """Return the default global RpcRuntime.

    This keeps backward-compatibility for existing imports and decorators.
    """

    return _global_runtime

