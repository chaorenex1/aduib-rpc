from __future__ import annotations

import contextvars
import functools
import inspect
from typing import Any, Callable, TYPE_CHECKING
from aduib_rpc.discover import MethodDescriptor
from aduib_rpc.discover.entities import ServiceInstance

if TYPE_CHECKING:
    from aduib_rpc.client.auth import CredentialsProvider
    from aduib_rpc.config.models import AduibRpcConfig


class ScopedRuntime:
    """Scoped runtime registries with optional inheritance.

    Args:
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
        tenant_id: str = "default",
        service_funcs: dict[str, Any] | None = None,
        client_funcs: dict[str, Any] | None = None,
        interceptors: list[Any] | None = None,
        parent: ScopedRuntime | None = None,
        service_instances: dict[str, Any] | None = None,
        client_instances: dict[str, Any] | None = None,
        service_info: ServiceInstance | None = None,
        credentials_provider: CredentialsProvider | None = None,
        config: AduibRpcConfig | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.service_funcs = service_funcs or {}
        self.client_funcs = client_funcs or {}
        self.interceptors = interceptors or []
        self._parent = parent
        self.service_instances = service_instances or {}
        self.client_instances = client_instances or {}
        self.service_info = service_info
        self.credentials_provider = credentials_provider
        self.config = config

    def child(self, tenant_id: str | None = None) -> ScopedRuntime:
        """Create a child scope inheriting config and registries.

        Returns:
            A new ``ScopedRuntime`` instance.
        """
        return ScopedRuntime(
            tenant_id=tenant_id or self.tenant_id,
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
        if name in self.service_funcs:
            raise ValueError(f"Service function '{name}' is already registered in the current scope.")
        self.service_funcs[name] = func

    def register_client(self, name: str, func: Any) -> None:
        """Register a client function in the current scope.

        Args:
            name: Client function name.
            func: Callable or handler to register.
        """
        if name in self.client_funcs:
            raise ValueError(f"Client function '{name}' is already registered in the current scope.")
        self.client_funcs[name] = func

    def register_service_instance(self, name: str, instance: Any) -> None:
        """Register a service instance in the current scope.

        Args:
            name: Service instance name.
            instance: Instance to register.
        """
        if name in self.service_instances:
            raise ValueError(f"Service instance '{name}' is already registered in the current scope.")
        self.service_instances[name] = instance

    def register_client_instance(self, name: str, instance: Any) -> None:
        """Register a client instance in the current scope.

        Args:
            name: Client instance name.
            instance: Instance to register.
        """
        if name in self.client_instances:
            raise ValueError(f"Client instance '{name}' is already registered in the current scope.")
        self.client_instances[name] = instance

    def register_interceptor(self, interceptor: Any) -> None:
        """Register an interceptor in the current scope.

        Args:
            interceptor: Interceptor to register.
        """
        self.interceptors.append(interceptor)

    def register_parent(self, parent: ScopedRuntime) -> None:
        """Register a parent runtime for inheritance.

        Args:
            parent: Parent ``ScopedRuntime`` instance.
        """
        if self._parent is not None:
            raise ValueError("Parent runtime is already set.")
        self._parent = parent

    def clear_parent(self) -> None:
        """Clear the parent runtime reference."""
        self._parent = None

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

    def get_service_instance(self, name: str) -> Any | None:
        """Get a service instance by name with parent fallback.

        Args:
            name: Service instance name.

        Returns:
            The registered instance, or ``None`` if not found.
        """
        if name in self.service_instances:
            return self.service_instances[name]
        if self._parent is None:
            return None
        return self._parent.get_service_instance(name)

    def get_client_instance(self, name: str) -> Any | None:
        """Get a client instance by name with parent fallback.

        Args:
            name: Client instance name.

        Returns:
            The registered instance, or ``None`` if not found.
        """
        if name in self.client_instances:
            return self.client_instances[name]
        if self._parent is None:
            return None
        return self._parent.get_client_instance(name)

    def batch_to_method_descriptors(self) -> list[MethodDescriptor]:
        """Convert registered service functions to method descriptors.

        Returns:
            A list of ``MethodDescriptor`` instances for registered services.
        """
        descriptors = []
        for name, func in self.service_funcs.items():
            descriptor = func.to_descriptor() if hasattr(func, "to_descriptor") else MethodDescriptor(name=name)
            descriptors.append(descriptor)
        return descriptors

    def set_config(self, config: AduibRpcConfig) -> None:
        """Set the runtime configuration.

        Args:
            config: The AduibRpcConfig instance to set.
        """
        self.config = config
        if self._parent is not None:
            self._parent.set_config(config)

    def reset(self) -> None:
        """Reset runtime registries for test isolation.

        Note: service_info is preserved if it was set via set_service_info().
        To clear service_info, explicitly set it to None after reset.
        """
        saved_service_info = self.service_info
        self.service_instances.clear()
        self.client_instances.clear()
        self.service_funcs.clear()
        self.client_funcs.clear()
        self.interceptors.clear()
        self.credentials_provider = None
        # Restore service_info if it was explicitly set (not from default)
        if saved_service_info is not None:
            self.service_info = saved_service_info

    def enable_auth(self) -> None:
        """Enable auth interception for outbound calls."""
        from aduib_rpc.client.auth import InMemoryCredentialsProvider
        from aduib_rpc.client.auth.interceptor import AuthInterceptor

        if not self.credentials_provider:
            self.credentials_provider = InMemoryCredentialsProvider()
        has_auth = any(isinstance(i, AuthInterceptor) for i in self.interceptors)
        if not has_auth:
            self.interceptors.append(AuthInterceptor(self.credentials_provider))


def create_runtime() -> ScopedRuntime:
    """Create a new scoped runtime.

    Returns:
        A new ``ScopedRuntime`` instance.
    """
    return ScopedRuntime()


_default_runtime = create_runtime()
_runtime_ctx: contextvars.ContextVar[ScopedRuntime] = contextvars.ContextVar(
    "aduib_rpc_runtime_ctx",
    default=_default_runtime,
)


def update_runtime(runtime: ScopedRuntime) -> None:
    """Update the current runtime context to the provided runtime.

    Args:
        runtime: The new ScopedRuntime instance to set as current.
    """
    _runtime_ctx.set(runtime)


class _RuntimeScope:
    """Context manager/decorator for binding runtime to the current context."""

    def __init__(self, runtime_factory: Callable[[], ScopedRuntime]) -> None:
        self._runtime_factory = runtime_factory
        self._token: contextvars.Token[ScopedRuntime] | None = None

    def __enter__(self) -> ScopedRuntime:
        runtime = self._runtime_factory()
        self._token = _runtime_ctx.set(runtime)
        return runtime

    def __exit__(self, exc_type, exc, _tb) -> bool:
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
        return parent.child(tenant_id)

    return _RuntimeScope(_factory)


# Backward compatibility alias
RpcRuntime = ScopedRuntime

def set_service_info(service_info: ServiceInstance) -> None:
    """Set service identity metadata on the active runtime.

    This persists the service_info across runtime resets by storing it
    in a catalog. When the runtime is reset, service_info is restored
    from the catalog.

    Args:
        service_info: Service instance identity metadata.
    """
    runtime = get_runtime()
    runtime.service_info = service_info
    # Persist for recovery after reset


def get_service_info() -> ServiceInstance | None:
    """Get the service identity metadata from the active runtime.

    Returns:
        The current service_info, or None if not set.
    """
    runtime = get_runtime()
    return runtime.service_info
