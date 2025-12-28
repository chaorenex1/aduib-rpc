import asyncio
import functools
import inspect
import logging
import time
import warnings
from collections.abc import Iterator, MutableMapping, MutableSequence
from typing import Any, Callable, Mapping, TypeVar

from aduib_rpc.rpc.methods import MethodName
from aduib_rpc.server.rpc_execution.runtime import RpcRuntime, get_runtime
from aduib_rpc.utils.anyio_compat import run as run_anyio

from aduib_rpc.client import ClientRequestInterceptor
from aduib_rpc.client.auth import CredentialsProvider
from aduib_rpc.server.rpc_execution.service_func import ServiceFunc
from aduib_rpc.utils.async_utils import AsyncUtils

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Persistent catalogs
# ---------------------------------------------------------------------------
#
# Some tests (and real apps) may call FuncCallContext.reset() which clears the
# default runtime registries. Services defined via decorators may have already
# been imported, and their decorators won't re-run automatically. To avoid
# cross-test ordering issues, we keep a persistent catalog of decorated services
# and service funcs, and re-hydrate the default runtime on demand.
_SERVICE_CATALOG: dict[str, Any] = {}
_SERVICE_FUNC_CATALOG: dict[str, ServiceFunc] = {}


def default_runtime() -> RpcRuntime:
    """Return the current default runtime.

    Use this instead of relying on module-level globals.
    """

    return get_runtime()


def _get_effective_runtime(runtime: RpcRuntime | None) -> RpcRuntime:
    return runtime or default_runtime()


class _DeprecatedRuntimeView:
    """A dynamic view over the current default runtime.

    This exists to keep backward compatibility with older code that imports
    `service_funcs`, `service_instances`, etc.

    These views always reflect the *current* default runtime (get_runtime()),
    rather than capturing one at import-time.
    """

    __slots__ = ("_name",)

    def __init__(self, name: str):
        self._name = name

    def _target(self):
        return getattr(default_runtime(), self._name)


class _RuntimeMappingView(_DeprecatedRuntimeView, MutableMapping[str, Any]):
    def __getitem__(self, key: str) -> Any:
        warnings.warn(
            f"Importing '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._target()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        warnings.warn(
            f"Mutating '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._target()[key] = value

    def __delitem__(self, key: str) -> None:
        warnings.warn(
            f"Mutating '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        del self._target()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._target())

    def __len__(self) -> int:
        return len(self._target())


class _RuntimeListView(_DeprecatedRuntimeView, MutableSequence[_T]):
    def __getitem__(self, i: int) -> _T:
        warnings.warn(
            f"Importing '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._target()[i]

    def __setitem__(self, i: int, item: _T) -> None:
        warnings.warn(
            f"Mutating '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._target()[i] = item

    def __delitem__(self, i: int) -> None:
        warnings.warn(
            f"Mutating '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        del self._target()[i]

    def __len__(self) -> int:
        return len(self._target())

    def insert(self, index: int, value: _T) -> None:
        warnings.warn(
            f"Mutating '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._target().insert(index, value)


class _RuntimeAttrView(_DeprecatedRuntimeView):
    def get(self) -> Any:
        warnings.warn(
            f"Accessing '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._target()

    def set(self, value: Any) -> None:
        warnings.warn(
            f"Mutating '{self._name}' from service_call is deprecated; use explicit runtime access.",
            DeprecationWarning,
            stacklevel=2,
        )
        setattr(default_runtime(), self._name, value)


# ---------------------------------------------------------------------------
# Backward-compatible module-level views (deprecated)
# ---------------------------------------------------------------------------
service_instances: MutableMapping[str, Any] = _RuntimeMappingView("service_instances")
client_instances: MutableMapping[str, Any] = _RuntimeMappingView("client_instances")
service_funcs: MutableMapping[str, ServiceFunc] = _RuntimeMappingView("service_funcs")  # type: ignore[assignment]
client_funcs: MutableMapping[str, ServiceFunc] = _RuntimeMappingView("client_funcs")  # type: ignore[assignment]
interceptors: MutableSequence[ClientRequestInterceptor] = _RuntimeListView("interceptors")
credentials_provider: _RuntimeAttrView = _RuntimeAttrView("credentials_provider")


class FuncCallContext:
    """Compatibility facade around the current default runtime."""

    @staticmethod
    def _rt() -> RpcRuntime:
        return default_runtime()

    @classmethod
    def add_interceptor(cls, interceptor: ClientRequestInterceptor) -> None:
        cls._rt().interceptors.append(interceptor)

    @classmethod
    def get_interceptors(cls) -> list[ClientRequestInterceptor]:
        return cls._rt().interceptors

    @classmethod
    def set_credentials_provider(cls, provider: CredentialsProvider) -> None:
        cls._rt().credentials_provider = provider

    @classmethod
    def enable_auth(cls):
        cls._rt().enable_auth()

    @classmethod
    def get_service_func_names(cls) -> list[str]:
        return list(cls._rt().service_funcs.keys())

    @classmethod
    def get_client_func_names(cls) -> list[str]:
        return list(cls._rt().client_funcs.keys())

    @classmethod
    def reset(cls) -> None:
        """Reset default runtime state (primarily for tests)."""
        cls._rt().reset()


import importlib
import pkgutil


def load_service_plugins(package_name: str = __name__) -> None:
    """Auto-load all submodules under a package to trigger decorators.

    This is best-effort:
    - If the package doesn't exist or isn't a package (no __path__), it returns.
    - If a submodule fails to import, it logs and continues.
    """

    try:
        package = importlib.import_module(package_name)
    except Exception:
        logger.exception("Failed to import package %s", package_name)
        return

    package_path = getattr(package, "__path__", None)
    if not package_path:
        return

    for _, module_name, _ in pkgutil.iter_modules(package_path):
        full_module_name = f"{package_name}.{module_name}"
        try:
            importlib.import_module(full_module_name)
        except Exception:
            logger.exception("Failed to import plugin module %s", full_module_name)


def fallback_function(fallback: Callable[..., Any], *args, **kwargs) -> Any:
    # No need to catch/raise, just preserve original traceback.
    # fallback may be sync or async.
    if asyncio.iscoroutinefunction(fallback):
        return AsyncUtils.run_async(fallback(*args, **kwargs))
    return fallback(*args, **kwargs)


def _compose_remote_method(service_name: str, func_qualname: str) -> str:
    """Compose stable RPC method name sent to server."""
    return MethodName.format_v2(service_name, func_qualname)


def _default_handler_name(func: Callable[..., Any]) -> str:
    """Derive a stable handler name for RPC.

    Prefer __qualname__ so methods include their class name, avoiding collisions.
    """

    qn = getattr(func, "__qualname__", None)
    if qn:
        return qn
    return getattr(func, "__name__", str(func))


def _call_maybe_async(fn: Callable[..., Any], *args, **kwargs) -> Any:
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        return result
    return result


def _make_wrappers(
        *,
        kind: str,
        func: Callable[..., Any],
        handler_name: str,
        fallback: Callable[..., Any] | None,
        extra_base: Mapping[str, Any] | None = None,
) -> tuple[Callable[..., Any], Callable[..., Any]]:
    """Create async and sync wrappers with shared logging/timing/fallback behavior."""

    extra_base = dict(extra_base or {})

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
            res = _call_maybe_async(func, *args, **kwargs)
            if inspect.isawaitable(res):
                return await res
            return res
        except asyncio.CancelledError:
            logger.debug('CancelledError in %s %s', kind, handler_name, extra=extra_base)
            if fallback:
                logger.info('Calling fallback function for %s', handler_name,
                            extra={**extra_base, "rpc.fallback_used": True})
                return fallback_function(fallback, *args, **kwargs)
            raise
        except Exception as e:
            logger.warning('Exception in %s %s: %s', kind, handler_name, e, exc_info=True, extra=extra_base)
            if fallback:
                logger.info('Calling fallback function for %s', handler_name,
                            extra={**extra_base, "rpc.fallback_used": True})
                return fallback_function(fallback, *args, **kwargs)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                '%s call finished',
                kind.capitalize(),
                extra={**extra_base, "rpc.handler": handler_name, "rpc.duration_ms": duration_ms},
            )

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        # Keep sync wrapper truly sync for service functions.
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning('Exception in %s %s: %s', kind, handler_name, e, exc_info=True, extra=extra_base)
            if fallback:
                logger.info('Calling fallback function for %s', handler_name,
                            extra={**extra_base, "rpc.fallback_used": True})
                return fallback_function(fallback, *args, **kwargs)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                '%s call finished',
                kind.capitalize(),
                extra={**extra_base, "rpc.handler": handler_name, "rpc.duration_ms": duration_ms},
            )

    return async_wrapper, sync_wrapper


def service_function(  # noqa: PLR0915
        func: Callable | None = None,
        *,
        func_name: str | None = None,
        fallback: Callable[..., Any] = None,
        runtime: RpcRuntime | None = None,
) -> Callable:
    """Decorator to register a service function.

    runtime:
        Optional runtime registry holder. If not passed, the default global runtime
        is used for backward compatibility.

    Note: This decorator only wraps the function. Actual registration into runtime
    happens in the @service / @client class decorators.
    """
    if func is None:
        return functools.partial(
            service_function,
            func_name=func_name,
            fallback=fallback,
            runtime=runtime,
        )

    actual_func_name = func_name or _default_handler_name(func)
    is_async_func = inspect.iscoroutinefunction(func)

    logger.debug(
        'Start wrap func for %s, is_async_func %s',
        actual_func_name,
        is_async_func,
    )

    async_wrapper, sync_wrapper = _make_wrappers(
        kind="service",
        func=func,
        handler_name=actual_func_name,
        fallback=fallback,
    )

    return async_wrapper if is_async_func else sync_wrapper


def client_function(  # noqa: PLR0915
        func: Callable | None = None,
        *,
        func_name: str | None = None,
        service_name: str | None = None,
        stream: bool = True,
        fallback: Callable[..., Any] = None,
        runtime: RpcRuntime | None = None,
) -> Callable:
    """Decorator to call a remote service function.

    runtime:
        Optional runtime registry holder. If not passed, the default global runtime
        is used for backward compatibility.

    runtime is used to source interceptors/credentials in the future; currently it
    mainly allows keeping per-test isolation when methods are generated via @client.
    """
    if func is None:
        return functools.partial(
            client_function,
            func_name=func_name,
            service_name=service_name,
            stream=stream,
            fallback=fallback,
            runtime=runtime,
        )

    handler_name = func_name or _default_handler_name(func)
    is_async_func = inspect.iscoroutinefunction(func)

    logger.debug(
        'Start call for %s (service=%s), is_async_func %s',
        handler_name,
        service_name,
        is_async_func,
    )

    effective_runtime = _get_effective_runtime(runtime)

    @functools.wraps(func)
    async def _client_call(*args, **kwargs) -> Any:
        from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
        from aduib_rpc.client.client_factory import AduibRpcClientFactory
        from aduib_rpc.client.service_resolver import RegistryServiceResolver

        if not service_name:
            raise ValueError("service_name is required for @client")

        registries = ServiceRegistryFactory.list_registries()
        if not registries:
            raise RuntimeError("No service registry available")

        dict_data = args_to_dict(func, *args, **kwargs)
        dict_data.pop('self', None)

        remote_method = _compose_remote_method(service_name, handler_name)

        # Optional per-call load balancing controls via meta.
        # - lb_policy: int enum value from LoadBalancePolicy
        # - lb_key: string key for consistent hashing
        lb_policy = None
        lb_key = None
        if isinstance(dict_data.get('meta'), dict):
            lb_policy = dict_data['meta'].get('lb_policy')
            lb_key = dict_data['meta'].get('lb_key')

        resolver_policy = None
        if lb_policy is not None:
            try:
                from aduib_rpc.utils.constant import LoadBalancePolicy
                resolver_policy = LoadBalancePolicy(int(lb_policy))
            except Exception:
                logger.warning("Invalid lb_policy=%r; falling back to default", lb_policy)

        resolver = RegistryServiceResolver(registries, policy=resolver_policy or None, key=lb_key)
        resolved = resolver.resolve(service_name)
        if not resolved:
            raise RuntimeError(f"Service '{service_name}' not found")

        client = AduibRpcClientFactory.create_client(
            resolved.url,
            stream,
            resolved.scheme,
            interceptors=effective_runtime.interceptors,
        )

        resp = await client.completion(
            remote_method,
            dict_data,
            resolved.meta(),
        )
        logger.debug('called remote service %s', remote_method, extra={"rpc.method": remote_method})

        result = None
        async for r in resp:
            result = r.result

        return result

    async_wrapper, _sync_wrapper = _make_wrappers(
        kind="client",
        func=_client_call,
        handler_name=handler_name,
        fallback=fallback,
        extra_base={"rpc.service": service_name or ""},
    )

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        async def async_call() -> Any:
            return await async_wrapper(*args, **kwargs)

        return run_anyio(async_call)

    return async_wrapper if is_async_func else sync_wrapper


def service(service_name: str, *, runtime: RpcRuntime | None = None):
    """Decorator to register a service executor class."""

    effective_runtime = _get_effective_runtime(runtime)

    def decorator(cls: Any):
        for method_name, function in inspect.getmembers(cls, inspect.isfunction):
            if method_name.startswith('__') and method_name.endswith('__'):
                continue

            handler_name = f"{cls.__name__}.{method_name}" if cls.__name__ else method_name
            full_name = f"{service_name}.{handler_name}"

            setattr(
                cls,
                method_name,
                service_function(func_name=full_name, fallback=None, runtime=effective_runtime)(function),
            )
            wrapper_func = getattr(cls, method_name)
            service_func: ServiceFunc = ServiceFunc.from_function(function, full_name, function.__doc__)
            service_func.wrap_fn = wrapper_func
            effective_runtime.service_funcs[full_name] = service_func

            # Keep a persistent copy so we can rehydrate runtime after reset().
            _SERVICE_FUNC_CATALOG[full_name] = service_func

        effective_runtime.service_instances[service_name] = cls

        # Keep a persistent copy so we can rehydrate runtime after reset().
        _SERVICE_CATALOG[service_name] = cls
        return cls

    return decorator


def client(service_name: str, stream: bool = True, fallback: Callable[..., Any] = None, *, runtime: RpcRuntime | None = None):
    """Decorator to register a client class whose methods call remote services."""

    effective_runtime = _get_effective_runtime(runtime)

    def decorator(cls: Any):
        for method_name, function in inspect.getmembers(cls, inspect.isfunction):
            if method_name.startswith('__') and method_name.endswith('__'):
                continue

            handler_name = f"{cls.__name__}.{method_name}" if cls.__name__ else method_name

            setattr(
                cls,
                method_name,
                client_function(
                    func_name=handler_name,
                    service_name=service_name,
                    stream=stream,
                    fallback=fallback,
                    runtime=effective_runtime,
                )(function),
            )
            wrapper_func = getattr(cls, method_name)
            client_func: ServiceFunc = ServiceFunc.from_function(function, handler_name, function.__doc__)
            client_func.wrap_fn = wrapper_func
            effective_runtime.client_funcs[handler_name] = client_func

        if fallback:
            setattr(cls, 'fallback', staticmethod(fallback))
        effective_runtime.client_instances[cls.__name__] = cls
        return cls

    return decorator


def args_to_dict(func, *args, **kwargs):
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()
    return dict(bound.arguments)


class ServiceCaller:
    def __init__(self, service_type: Any, service_name: str, runtime: RpcRuntime | None = None):
        self.service_type = service_type
        self.service_name = service_name
        self._runtime = _get_effective_runtime(runtime)

    @classmethod
    def from_service_caller(cls, service_name: str, runtime: RpcRuntime | None = None):
        effective_runtime = _get_effective_runtime(runtime)
        service_type = effective_runtime.service_instances.get(service_name)
        if service_type is None:
            service_type = _SERVICE_CATALOG.get(service_name)
            if service_type is not None:
                effective_runtime.service_instances[service_name] = service_type

                prefix = f"{service_name}."
                for full_name, service_func in _SERVICE_FUNC_CATALOG.items():
                    if full_name.startswith(prefix):
                        effective_runtime.service_funcs.setdefault(full_name, service_func)
        return cls(service_type, service_name, runtime=effective_runtime)

    async def call(self, func_name: str, *args, **kwargs):
        # func_name may be "method" or "Class.method" depending on the caller.
        handler = func_name
        if "." not in handler and self.service_type is not None:
            handler = f"{self.service_type.__name__}.{func_name}"

        service_func_name = f"{self.service_name}.{handler}"
        logger.debug("Calling service function: %s", service_func_name)

        service_func = self._runtime.service_funcs.get(service_func_name)
        if not service_func:
            raise ValueError(f"Service function '{service_func_name}' is not registered.")
        if self.service_type is None:
            raise ValueError(f"Service '{self.service_name}' is not registered.")

        service_instance = self.service_type()

        # IMPORTANT:
        # Methods on the service class are wrapped by @service, so their signatures
        # become (*args, **kwargs). Binding against the wrapped method collapses
        # keyword args into a single "kwargs" entry, breaking arg validation.
        # Bind against the original function signature instead.
        original_fn = service_func.fn
        arguments = args_to_dict(original_fn, service_instance, *args, **kwargs)
        return await service_func.run(arguments)


class ClientCaller:
    def __init__(self, service_type: Any, service_name: str, runtime: RpcRuntime | None = None):
        self.service_type = service_type
        self.service_name = service_name
        self._runtime = _get_effective_runtime(runtime)

    @classmethod
    def from_client_caller(cls, service_name: str, runtime: RpcRuntime | None = None):
        effective_runtime = _get_effective_runtime(runtime)
        service_type = effective_runtime.client_instances.get(service_name)
        return cls(service_type, service_name, runtime=effective_runtime)

    async def call(self, func_name: str, *args, **kwargs):
        handler = func_name
        service_func = self._runtime.client_funcs.get(handler)
        if not service_func:
            raise ValueError(f"Client function '{func_name}' is not registered.")
        if self.service_type is None:
            raise ValueError(f"Client '{self.service_name}' is not registered.")
        service_instance = self.service_type()
        method = getattr(service_instance, handler.split('.')[-1])
        arguments = args_to_dict(method, *args, **kwargs)
        arguments['self'] = service_instance
        return await service_func.run(arguments)

# ------------------------------
# 示例使用
# ------------------------------

# class test_add(BaseModel):
#     x: int = 1
#     y: int = 2
#
# @service("MyService")
# class MyService:
#     def add(self, x, y):
#         """同步加法"""
#         return x + y
#
#     def add2(self, data:test_add):
#         """同步加法"""
#         return data.x + data.y
#
#     async def async_mul(self, x, y):
#         """异步乘法"""
#         await asyncio.sleep(0.1)
#         return x * y
#
#     def fail(self, x):
#         """会失败的函数"""
#         raise RuntimeError("Oops!")
#
#
# class MyServiceFallback(Callable[..., Any]):
#     def __call__(self, *args, **kwargs) -> Any:
#         return "Fallback result"
#
# @client("MyService2", fallback=MyServiceFallback())
# class MyService2:
#     def add(self, x, y):
#         """同步加法"""
#         return x + y
#
#     def add2(self, data:test_add):
#         """同步加法"""
#         return data.x + data.y
#
#     async def async_mul(self, x, y):
#         """异步乘法"""
#         await asyncio.sleep(0.1)
#         return x * y
#
#     def fail(self, x):
#         """会失败的函数"""
#         raise RuntimeError("Oops!")
# ------------------------------
# 调用示例
# ------------------------------
# async def main():
#     # caller = ServiceCaller.from_service_caller("MyService")
#     #
#     # res1 = await caller.call("add", 1, 2)
#     # res3 = await caller.call("add2", test_add())
#     # res2 = await caller.call("async_mul", 3, 4)
#     # # res3 = await caller.call("fail", 123)
#     #
#     # print("add:", res1)
#     # print("add2:", res3)
#     # print("async_mul:", res2)
#     # print("fail:", res3)
#
#     myservice = MyService2()
#     print("MyService2 add:", myservice.add(5, 6))
#     print("MyService2 async_mul:", await myservice.async_mul(7, 8))
#     print("MyService2 fail:", myservice.fail(123))  # 调用会触发 fallback
#
#
# asyncio.run(main())
