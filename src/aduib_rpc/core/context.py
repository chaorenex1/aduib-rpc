"""Runtime configuration and context management.

This module defines an async-safe runtime context using ``contextvars`` and a
scoped runtime container that supports inheritance and overrides. The default
runtime mirrors the historical global behavior while enabling per-request
scoping through context managers and decorators.
"""

from __future__ import annotations

import contextvars
import functools
import inspect
from dataclasses import dataclass, replace
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from aduib_rpc.client.auth import CredentialsProvider
    from aduib_rpc.discover.entities import ServiceInstance

__all__ = [
    "RuntimeConfig",
    "ScopedRuntime",
    "create_runtime",
    "get_current_runtime",
    "get_runtime",
    "with_runtime",
    "with_tenant",
]


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Immutable runtime configuration.

    Args:
        tenant_id: Tenant identifier for multi-tenant routing.
        environment: Runtime environment name.
        max_connections: Maximum concurrent outbound connections.
        request_timeout_ms: Default request timeout in milliseconds.
        enable_telemetry: Whether telemetry is enabled for this runtime.
    """

    tenant_id: str = "default"
    environment: str = "production"
    max_connections: int = 100
    request_timeout_ms: int = 30000
    enable_telemetry: bool = True


class ScopedRuntime:
    """Scoped runtime registries with optional inheritance.

    Args:
        config: Optional runtime configuration for the scope.
        service_funcs: Service function registry.
        client_funcs: Client function registry.
        interceptors: Interceptor registry for outbound calls.
        parent: Optional parent runtime scope.
        service_instances: Service instance registry (legacy compatibility).
        client_instances: Client instance registry (legacy compatibility).
        service_info: Service identity metadata (legacy compatibility).
        credentials_provider: Credentials provider (legacy compatibility).
    """

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        service_funcs: dict[str, Any] | None = None,
        client_funcs: dict[str, Any] | None = None,
        interceptors: list[Any] | None = None,
        parent: ScopedRuntime | None = None,
        service_instances: dict[str, Any] | None = None,
        client_instances: dict[str, Any] | None = None,
        service_info: ServiceInstance | None = None,
        credentials_provider: CredentialsProvider | None = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.service_funcs = service_funcs or {}
        self.client_funcs = client_funcs or {}
        self.interceptors = interceptors or []
        self._parent = parent
        self.service_instances = service_instances or {}
        self.client_instances = client_instances or {}
        self.service_info = service_info
        self.credentials_provider = credentials_provider

    def child(self, **overrides: Any) -> ScopedRuntime:
        """Create a child scope inheriting config and registries.

        Args:
            **overrides: ``RuntimeConfig`` fields to override for the child.

        Returns:
            A new ``ScopedRuntime`` instance.
        """
        new_config = replace(self.config, **overrides)
        return ScopedRuntime(
            config=new_config,
            service_funcs=dict(self.service_funcs),
            client_funcs=dict(self.client_funcs),
            interceptors=list(self.interceptors),
            parent=self,
            service_instances=dict(self.service_instances),
            client_instances=dict(self.client_instances),
            service_info=self.service_info,
            credentials_provider=self.credentials_provider,
        )

    def register_service(self, name: str, func: Any) -> None:
        """Register a service function in the current scope.

        Args:
            name: Service function name.
            func: Callable or handler to register.
        """
        self.service_funcs[name] = func

    def register_client(self, name: str, func: Any) -> None:
        """Register a client function in the current scope.

        Args:
            name: Client function name.
            func: Callable or handler to register.
        """
        self.client_funcs[name] = func

    def get_service(self, name: str) -> Any | None:
        """Get a service function by name with parent fallback.

        Args:
            name: Service function name.

        Returns:
            The registered callable, or ``None`` if not found.
        """
        if name in self.service_funcs:
            return self.service_funcs[name]
        if self._parent is None:
            return None
        return self._parent.get_service(name)

    def get_client(self, name: str) -> Any | None:
        """Get a client function by name with parent fallback.

        Args:
            name: Client function name.

        Returns:
            The registered callable, or ``None`` if not found.
        """
        if name in self.client_funcs:
            return self.client_funcs[name]
        if self._parent is None:
            return None
        return self._parent.get_client(name)

    def reset(self) -> None:
        """Reset runtime registries for test isolation."""
        self.service_instances.clear()
        self.client_instances.clear()
        self.service_funcs.clear()
        self.client_funcs.clear()
        self.interceptors.clear()
        self.credentials_provider = None
        self.service_info = None

    def enable_auth(self) -> None:
        """Enable auth interception for outbound calls."""
        from aduib_rpc.client.auth import InMemoryCredentialsProvider
        from aduib_rpc.client.auth.interceptor import AuthInterceptor

        if not self.credentials_provider:
            self.credentials_provider = InMemoryCredentialsProvider()
        has_auth = any(isinstance(i, AuthInterceptor) for i in self.interceptors)
        if not has_auth:
            self.interceptors.append(AuthInterceptor(self.credentials_provider))


def create_runtime(config: RuntimeConfig | None = None) -> ScopedRuntime:
    """Create a new scoped runtime.

    Args:
        config: Optional runtime configuration.

    Returns:
        A new ``ScopedRuntime`` instance.
    """
    return ScopedRuntime(config or RuntimeConfig())


_default_runtime = create_runtime(RuntimeConfig())
_runtime_ctx: contextvars.ContextVar[ScopedRuntime] = contextvars.ContextVar(
    "aduib_rpc_runtime_ctx",
    default=_default_runtime,
)


class _RuntimeScope:
    """Context manager/decorator for binding runtime to the current context."""

    def __init__(self, runtime_factory: Callable[[], ScopedRuntime]) -> None:
        self._runtime_factory = runtime_factory
        self._token: contextvars.Token[ScopedRuntime] | None = None

    def __enter__(self) -> ScopedRuntime:
        runtime = self._runtime_factory()
        self._token = _runtime_ctx.set(runtime)
        return runtime

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._token is not None:
            _runtime_ctx.reset(self._token)
        self._token = None
        return False

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                with _RuntimeScope(self._runtime_factory):
                    return await func(*args, **kwargs)

            return wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with _RuntimeScope(self._runtime_factory):
                return func(*args, **kwargs)

        return wrapper


def get_current_runtime() -> ScopedRuntime:
    """Return the runtime bound to the current context.

    Returns:
        The current ``ScopedRuntime`` instance.
    """
    return _runtime_ctx.get()


def get_runtime() -> ScopedRuntime:
    """Backward-compatible alias for ``get_current_runtime``."""
    return get_current_runtime()


def with_runtime(runtime: ScopedRuntime) -> _RuntimeScope:
    """Bind a runtime to the current context.

    Args:
        runtime: Runtime instance to bind.

    Returns:
        A context manager/decorator that sets the runtime.
    """
    return _RuntimeScope(lambda: runtime)


def with_tenant(tenant_id: str) -> _RuntimeScope:
    """Create a tenant-scoped runtime context.

    Args:
        tenant_id: Tenant identifier to override in the runtime config.

    Returns:
        A context manager/decorator that binds a tenant-specific runtime.
    """

    def _factory() -> ScopedRuntime:
        parent = get_current_runtime()
        return parent.child(tenant_id=tenant_id)

    return _RuntimeScope(_factory)
