import asyncio
import functools
import inspect
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Callable, Mapping, TypeVar

from aduib_rpc.client import ClientRequestInterceptor
from aduib_rpc.client.auth import CredentialsProvider
from aduib_rpc.client.midwares import ClientContext
from aduib_rpc.protocol.v2 import TraceContext, QosConfig, RequestMetadata, AuthContext, AuthScheme
from aduib_rpc.protocol.v2 import get_current_trace_context, set_current_trace_context
from aduib_rpc.server.rpc_execution import MethodName, RpcRuntime, get_runtime
from aduib_rpc.server.rpc_execution.service_func import ServiceFunc
from aduib_rpc.server.tasks import TaskMethod, TaskSubmitRequest, TaskSubscribeRequest
from aduib_rpc.server.tasks.types import TaskEventType, TaskStatus
from aduib_rpc.types import AduibRpcRequest
from aduib_rpc.utils.anyio_compat import run as run_anyio
from aduib_rpc.utils.constant import SecuritySchemes

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class ServiceInstancePool:
    """Singleton service instance pool for reusing service instances."""

    def __init__(self):
        self._instances: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, service_type: type) -> Any:
        """Get existing instance or create a new one."""
        key = f"{service_type.__module__}.{service_type.__name__}"

        if key in self._instances:
            return self._instances[key]

        async with self._lock:
            # Double-check after acquiring lock
            if key in self._instances:
                return self._instances[key]

            instance = service_type()
            self._instances[key] = instance
            return instance

    def clear(self) -> None:
        """Clear all cached instances (for testing)."""
        self._instances.clear()


# Module-level singleton
_service_pool = ServiceInstancePool()


def get_service_pool() -> ServiceInstancePool:
    """Get the global service instance pool."""
    return _service_pool


def default_runtime() -> RpcRuntime:
    """Return the current default runtime.

    Use this instead of relying on module-level globals.
    """

    return get_runtime()


def _get_effective_runtime(runtime: RpcRuntime | None) -> RpcRuntime:
    return runtime or default_runtime()


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
        cls._rt().set_credentials_provider(provider)

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
        get_service_pool().clear()


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
        return run_anyio(fallback, *args, **kwargs)
    return fallback(*args, **kwargs)


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


def _is_async_iterable(value: Any) -> bool:
    return inspect.isasyncgen(value) or hasattr(value, "__aiter__")


def _extract_stream_source(data: dict[str, Any]) -> Any | None:
    if len(data.items()) > 1:
        raise ValueError("When using client streaming or bidirectional streaming, only one stream source is allowed.")
    for key, value in list(data.items()):
        if _is_async_iterable(value):
            data.pop(key)
            return value
    return None


async def _iter_stream_items(source: Any) -> AsyncIterator[Any]:
    if source is None:
        return
    if _is_async_iterable(source):
        async for item in source:
            yield item
        return
    if isinstance(source, (list, tuple, set)):
        for item in source:
            yield item
        return
    yield source


def _raise_for_rpc_error(value: Any, *, message: str | None = None) -> None:
    if value is None:
        return

    from aduib_rpc.protocol.v2 import AduibRpcResponse, ErrorCode, RpcError, exception_from_code

    err = None
    if isinstance(value, RpcError):
        err = value
    elif isinstance(value, AduibRpcResponse):
        err = value.error
    else:
        err = getattr(value, "error", None)

    if err is None:
        return

    code = getattr(err, "code", None)
    if code is None:
        code = int(ErrorCode.INTERNAL_ERROR)
    msg = getattr(err, "message", None) or message or "RPC error"
    if isinstance(err, Mapping):
        data = dict(err)
        code = data.get("code", code)
        msg = data.get("message", msg)
        name = data.get("name")
    else:
        data = err.model_dump() if hasattr(err, "model_dump") else {"code": code, "message": msg}
        name = getattr(err, "name", None)
    if name is not None and isinstance(data, dict):
        data.setdefault("name", name)
    raise exception_from_code(int(code), message=msg, data=data)


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

            # Async generator objects are not awaitable; they must be consumed with `async for`.
            # If a handler intentionally returns a stream, we pass it through unchanged.
            if inspect.isasyncgen(res):
                return res

            if inspect.isawaitable(res):
                return await res
            return res
        except asyncio.CancelledError:
            logger.debug("CancelledError in %s %s", kind, handler_name, extra=extra_base)
            if fallback:
                logger.info(
                    "Calling fallback function for %s", handler_name, extra={**extra_base, "rpc.fallback_used": True}
                )
                return fallback_function(fallback, *args, **kwargs)
            raise
        except Exception as e:
            logger.warning("Exception in %s %s: %s", kind, handler_name, e, exc_info=True, extra=extra_base)
            if fallback:
                logger.info(
                    "Calling fallback function for %s", handler_name, extra={**extra_base, "rpc.fallback_used": True}
                )
                return fallback_function(fallback, *args, **kwargs)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "%s call finished",
                kind.capitalize(),
                extra={**extra_base, "rpc.handler": handler_name, "rpc.duration_ms": duration_ms},
            )

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        # Keep sync wrapper truly sync for service functions.
        start = time.perf_counter()
        try:
            res = func(*args, **kwargs)
            # A sync wrapper cannot consume an async generator; fail fast with a clear error.
            if inspect.isasyncgen(res):
                raise TypeError(
                    f"{kind} handler '{handler_name}' returned an async generator, but was called via a sync wrapper. "
                    "Make the function async and consume it with 'async for', or return a concrete value instead."
                )
            return res
        except Exception as e:
            logger.warning("Exception in %s %s: %s", kind, handler_name, e, exc_info=True, extra=extra_base)
            if fallback:
                logger.info(
                    "Calling fallback function for %s", handler_name, extra={**extra_base, "rpc.fallback_used": True}
                )
                return fallback_function(fallback, *args, **kwargs)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "%s call finished",
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
    # Treat async-generator functions as async as well.
    is_async_func = inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)

    logger.debug(
        "Start wrap func for %s, is_async_func %s",
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


# Attribute name for storing stream metadata on functions
_METADATA_ATTR = "_rpc_metadata"


def _normalize_permission(
    value: "Permission | tuple[str, str] | dict[str, str] | None",
) -> dict[str, str] | None:
    if value is None:
        return None
    try:
        from aduib_rpc.security.rbac import Permission
    except Exception:
        Permission = None  # type: ignore[assignment]
    if Permission is not None and isinstance(value, Permission):
        return {"resource": str(value.resource), "action": str(value.action)}
    if isinstance(value, dict):
        resource = value.get("resource")
        action = value.get("action")
        if resource is None or action is None:
            raise ValueError("permission dict must include 'resource' and 'action'")
        return {"resource": str(resource), "action": str(action)}
    if isinstance(value, tuple | list) and len(value) == 2:
        return {"resource": str(value[0]), "action": str(value[1])}
    raise ValueError("permission must be Permission, (resource, action), dict, or None")


def _normalize_auth_scheme(value: Any) -> AuthScheme:
    if isinstance(value, AuthScheme):
        return value
    if value is None:
        return AuthScheme.UNSPECIFIED
    raw = str(value).strip().lower()
    for item in AuthScheme:
        if str(item.value).lower() == raw:
            return item
    return AuthScheme.UNSPECIFIED


def _build_auth_context(token: Any, scheme: Any | None) -> AuthContext | None:
    if token is None:
        return None
    if isinstance(token, AuthContext):
        return token
    auth_scheme = _normalize_auth_scheme(scheme) if scheme is not None else AuthScheme.BEARER
    return AuthContext.create(scheme=auth_scheme, credentials=str(token))


async def _get_credentials(
    provider: CredentialsProvider,
    *,
    scheme: Any,
    method: str,
    payload: dict[str, Any],
) -> Any:
    context = ClientContext()
    context.state["security_schema"] = scheme
    context.state["method"] = method
    context.state["payload"] = payload
    result = provider.get_credentials(scheme, context)
    if inspect.isawaitable(result):
        result = await result
    return result


def function(
    *,
    idempotent_key: str | None = None,
    timeout: int | None = None,
    client_stream: bool = False,
    server_stream: bool = False,
    bidirectional_stream: bool = False,
    long_running: bool = False,
    permission: "Permission | tuple[str, str] | dict[str, str] | None" = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to mark a service method with streaming capabilities.

    Usage:
        @function(server=True)
        async def stream_data(self, request: Request) -> AsyncIterator[Response]:
            ...

        @function(client=True)
        async def upload_data(self, stream: AsyncIterator[Chunk]) -> Result:
            ...

        @function(bidirectional=True)
        async def chat(self, stream: AsyncIterator[Message]) -> AsyncIterator[Message]:
            ...

    Args:
        client: Enable client-side streaming (client sends stream of messages).
        server: Enable server-side streaming (server sends stream of messages).
        bidirectional: Enable bidirectional streaming (both client and server stream).
            If True, implicitly sets client=True and server=True.

    Returns:
        A decorator that attaches stream metadata to the function.
    """
    # Bidirectional implies both client and server streaming
    if bidirectional_stream:
        client_stream = True
        server_stream = True

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        normalized_permission = _normalize_permission(permission)
        setattr(
            func,
            _METADATA_ATTR,
            {
                "client_stream": client_stream,
                "server_stream": server_stream,
                "bidirectional_stream": bidirectional_stream,
                "idempotent_key": idempotent_key,
                "timeout": timeout,
                "long_running": long_running,
                "permission": normalized_permission,
            },
        )
        return func

    return decorator


def get_func_metadata(func: Callable[..., Any]) -> dict[str, bool]:
    """Get stream metadata from a function decorated with @streaming.

    Args:
        func: The function to get stream metadata from.

    Returns:
        A dict with keys: client_stream, server_stream, bidirectional_stream.
        All values default to False if the function is not decorated.
    """
    return getattr(
        func,
        _METADATA_ATTR,
        {
            "client_stream": False,
            "server_stream": False,
            "bidirectional_stream": False,
            "idempotent_key": None,
            "timeout": None,
            "long_running": False,
            "permission": None,
        },
    )


def client_function(  # noqa: PLR0915
    func: Callable | None = None,
    *,
    handler_name: str | None = None,
    service_name: str | None = None,
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
            handler_name=handler_name,
            service_name=service_name,
            fallback=fallback,
            runtime=runtime,
        )
    from aduib_rpc.app import get_global_app, RpcApp

    app: RpcApp = get_global_app()
    effective_runtime = _get_effective_runtime(runtime)

    client_func: ServiceFunc = effective_runtime.client_funcs.get(handler_name)

    if client_func is None:
        raise ValueError(f"Client function '{handler_name}' is not registered in the runtime.")

    is_async_func = client_func.is_async

    logger.debug(
        "Start call for %s (service=%s), is_async_func %s",
        handler_name,
        service_name,
        is_async_func,
    )

    @functools.wraps(func)
    async def _client_call(*args, **kwargs) -> Any:
        from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
        from aduib_rpc.client.service_resolver import RegistryServiceResolver

        if not service_name:
            raise ValueError("service_name is required for @client")

        registries = ServiceRegistryFactory.list_registries()
        if not registries:
            raise RuntimeError("No service registry available")

        dict_data = args_to_dict(func, *args, **kwargs)
        dict_data.pop("self", None)

        if client_func.deprecated:
            logger.warning(
                "Calling deprecated client function '%s': %s",
                handler_name,
                client_func.deprecation_message or "No deprecation message provided.",
            )
        method_name = client_func.full_name
        if client_func.replaced_by:
            logger.info("Client function '%s' has been replaced by '%s'.", handler_name, client_func.replaced_by)

            method_name = MethodName.format_v2(service_name, client_func.replaced_by) or method_name

        logger.debug("called remote service %s", service_name, extra={"rpc.method": method_name})
        error_context = f"RPC call failed: {method_name}"

        metadata = client_func.metadata or {}
        lb_policy = metadata.get("lb_policy", 0)
        lb_key = metadata.get("lb_key", "")

        resolver_policy = None
        if lb_policy is not None:
            try:
                from aduib_rpc.utils.constant import LoadBalancePolicy

                resolver_policy = LoadBalancePolicy(int(lb_policy))
            except Exception:
                logger.warning("Invalid lb_policy=%r; falling back to default", lb_policy)

        resolver = RegistryServiceResolver(registries, policy=resolver_policy or app.resolver_policy)
        resolved = await resolver.resolve(service_name, lb_key=lb_key)
        if not resolved:
            raise RuntimeError(f"Service '{service_name}' not found")

        client = app.create_client(resolved)

        client_stream = client_func.client_stream
        server_stream = client_func.server_stream
        bidirectional_stream = client_func.bidirectional_stream
        if bidirectional_stream and not resolved.instance.capabilities.bidirectional:
            raise RuntimeError(f"Service '{service_name}' does not support bidirectional streaming")

        if client_stream and not resolved.instance.capabilities.streaming:
            raise RuntimeError(f"Service '{service_name}' does not support client streaming")

        if server_stream and not resolved.instance.capabilities.streaming:
            raise RuntimeError(f"Service '{service_name}' does not support server streaming")

        trace_context = get_current_trace_context()
        if trace_context is None:
            trace_context = TraceContext.create(baggage=resolved.meta())
            set_current_trace_context(trace_context)

        qos_config = QosConfig(
            timeout_ms=client_func.timeout,
            idempotency_key=dict_data.get("idempotency_key", None) if client_func.idempotent_key else None,
            retry=app.config.resilience.retry,
        )
        auth_ctx = None
        provider = getattr(effective_runtime, "credentials_provider", None)
        if provider is not None:
            try:
                scheme = getattr(effective_runtime, "security_scheme", None) or SecuritySchemes.OAuth2
                token = await _get_credentials(
                    provider,
                    scheme=scheme,
                    method=method_name,
                    payload=dict_data,
                )
                auth_ctx = _build_auth_context(token, getattr(effective_runtime, "auth_scheme", None))
            except Exception:
                logger.exception("credentials_provider failed for method %s", method_name)
        request_meta = RequestMetadata.create(
            effective_runtime.tenant_id,
            client_id=app.get_client_id(),
            auth=auth_ctx,
        )

        if client_func.long_running:
            request_meta.long_task = True
            if client_stream or bidirectional_stream:
                raise RuntimeError("long_running cannot be combined with client/bidirectional streaming.")
            request_meta.long_task_method = TaskMethod.SUBMIT_TASK
            request = AduibRpcRequest.create(
                id=str(uuid.uuid4()),
                name=service_name,
                method=method_name,
                data=dict_data,
                meta=resolved.meta(),
                trace_context=trace_context,
                qos=qos_config,
                metadata=request_meta,
            )

            submit_resp = await client.task_submit(
                TaskSubmitRequest(target_method=request_meta.long_task_method, params=request.model_dump())
            )
            task_id = submit_resp.task_id
            if not task_id:
                raise RuntimeError("long_running task submit did not return task_id")

            logger.info("Task '%s' returned status '%s'.", handler_name, submit_resp.status)
            if submit_resp.status != TaskStatus.FAILED:
                request_meta.long_task_method = TaskMethod.SUBMIT_TASK

                async def _results():
                    async for resp in client.task_subscribe(TaskSubscribeRequest(task_id=task_id)):
                        yield resp
                        if resp.event == TaskEventType.COMPLETED:
                            logger.info("Task '%s' completed status '%s'.", handler_name, submit_resp.status)
                            return

                return _results()
            else:
                logger.warning("Task '%s' failed status '%s'.", handler_name, submit_resp.status)
                return None

        stream_source = None
        if client_stream or bidirectional_stream:
            stream_source = _extract_stream_source(dict_data)

            async def _iter_requests():
                async for item in _iter_stream_items(stream_source):
                    yield AduibRpcRequest.create(
                        id=str(uuid.uuid4()),
                        name=service_name,
                        method=method_name,
                        data=item,
                        meta=resolved.meta(),
                        trace_context=trace_context,
                        qos=qos_config,
                        metadata=request_meta,
                    )

            if bidirectional_stream:
                resp_stream = client.call_bidirectional(_iter_requests())

                async def _results():
                    async for r in resp_stream:
                        _raise_for_rpc_error(r, message=error_context)
                        yield r.result

                return _results()

            if client_stream:
                resp = await client.call_client_stream(_iter_requests())
                _raise_for_rpc_error(resp, message=error_context)
                return resp.result
            return None
        elif server_stream:
            resp = client.call_server_stream(
                AduibRpcRequest.create(
                    id=str(uuid.uuid4()),
                    name=service_name,
                    method=method_name,
                    data=dict_data,
                    meta=resolved.meta(),
                    trace_context=trace_context,
                    qos=qos_config,
                    metadata=request_meta,
                )
            )

            async def _results():
                async for r in resp:
                    _raise_for_rpc_error(r, message=error_context)
                    yield r.result

            return _results()
        else:
            resp = await client.call(
                AduibRpcRequest.create(
                    id=str(uuid.uuid4()),
                    name=service_name,
                    method=method_name,
                    data=dict_data,
                    meta=resolved.meta(),
                    trace_context=trace_context,
                    qos=qos_config,
                    metadata=request_meta,
                )
            )

            if inspect.isawaitable(resp) and not hasattr(resp, "__aiter__"):
                resp = await resp
            if _is_async_iterable(resp):
                result = None
                async for r in resp:
                    _raise_for_rpc_error(r, message=error_context)
                    result = r.result
                return result
            if hasattr(resp, "result"):
                _raise_for_rpc_error(resp, message=error_context)
                return resp.result
            _raise_for_rpc_error(resp, message=error_context)
            return resp

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


def service(
    name: str | None = None,
    *,
    version: str = "1.0.0",
    deprecated: bool = False,
    deprecation_message: str = "",
    replaced_by: str | None = None,
    metadata: dict[str, Any] | None = None,
    runtime: RpcRuntime | None = None,
):
    """Decorator to register a service executor class.

    Usage:
        @service("MyService")  # with name
        @service(name="MyService")  # keyword argument
        @service()  # use class name
    """

    effective_runtime = _get_effective_runtime(runtime)

    def decorator(cls: Any):
        service_name = name if name else cls.__name__
        for method_name, function in inspect.getmembers(cls, inspect.isfunction):
            handler_name = f"{service_name}.{method_name}"
            if effective_runtime.get_service(handler_name):
                logger.warning("Service function '%s' is already registered; skipping.", handler_name)
                continue
            full_handler_name = MethodName.format_v2(effective_runtime.service_info.service_name, handler_name)

            setattr(
                cls,
                method_name,
                service_function(func_name=handler_name, fallback=None, runtime=effective_runtime)(function),
            )
            wrapper_func = getattr(cls, method_name)
            func_metadata = get_func_metadata(function)
            merged_metadata = {**(metadata or {}), **func_metadata}
            service_func: ServiceFunc = ServiceFunc.from_function(
                function,
                wrapper_func,
                handler_name,
                full_handler_name,
                function.__doc__,
                version=version,
                deprecated=deprecated,
                deprecation_message=deprecation_message,
                replaced_by=replaced_by,
                idempotent_key=func_metadata["idempotent_key"],
                timeout=func_metadata["timeout"],
                long_running=func_metadata["long_running"],
                metadata=merged_metadata,
                client_stream=func_metadata["client_stream"],
                server_stream=func_metadata["server_stream"],
                bidirectional_stream=func_metadata["bidirectional_stream"],
            )
            effective_runtime.register_service(handler_name, service_func)

        effective_runtime.register_service_instance(service_name, cls)
        # Also register under runtime service_info name when it differs, so
        # ServiceCaller can resolve by the advertised service name.
        service_info = getattr(effective_runtime, "service_info", None)
        runtime_service_name = getattr(service_info, "service_name", None) if service_info is not None else None
        if runtime_service_name and runtime_service_name != service_name:
            if runtime_service_name not in effective_runtime.service_instances:
                effective_runtime.service_instances[runtime_service_name] = cls
        return cls

    return decorator


def client(
    service_name: str,
    fallback: Callable[..., Any] = None,
    *,
    version: str = "1.0.0",
    deprecated: bool = False,
    deprecation_message: str = "",
    metadata: dict[str, Any] | None = None,
    runtime: RpcRuntime | None = None,
):
    """Decorator to register a client class whose methods call remote services."""

    effective_runtime = _get_effective_runtime(runtime)

    def decorator(cls: Any):
        for method_name, function in inspect.getmembers(cls, inspect.isfunction):
            if method_name.startswith("__") and method_name.endswith("__"):
                continue

            handler_name = f"{cls.__name__}.{method_name}" if cls.__name__ else method_name
            if effective_runtime.get_client(handler_name):
                logger.warning("Client function '%s' is already registered; skipping.", handler_name)
                continue
            full_handler_name = MethodName.format_v2(service_name, handler_name)

            setattr(
                cls,
                method_name,
                client_function(
                    handler_name=handler_name,
                    service_name=service_name,
                    fallback=fallback,
                    runtime=effective_runtime,
                )(function),
            )
            wrapper_func = getattr(cls, method_name)
            func_metadata = get_func_metadata(function)
            merged_metadata = {**(metadata or {}), **func_metadata}
            client_func: ServiceFunc = ServiceFunc.from_function(
                function,
                wrapper_func,
                handler_name,
                full_handler_name,
                function.__doc__,
                version=version,
                deprecated=deprecated,
                deprecation_message=deprecation_message,
                replaced_by=None,
                idempotent_key=func_metadata["idempotent_key"],
                timeout=func_metadata["timeout"],
                long_running=func_metadata["long_running"],
                metadata=merged_metadata,
                client_stream=func_metadata["client_stream"],
                server_stream=func_metadata["server_stream"],
                bidirectional_stream=func_metadata["bidirectional_stream"],
            )
            client_func.wrap_fn = wrapper_func
            effective_runtime.register_client(handler_name, client_func)

        if fallback:
            setattr(cls, "fallback", staticmethod(fallback))
        effective_runtime.register_client_instance(cls.__name__, cls)
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
        return cls(service_type, service_name, runtime=effective_runtime)

    async def call(self, func_name: str, *args, **kwargs):
        # func_name may be "method" or "Class.method" depending on the caller.
        logger.debug("Calling service function: %s", func_name)

        service_func = self._runtime.service_funcs.get(func_name)
        if not service_func:
            raise ValueError(f"Service function '{func_name}' is not registered.")
        if self.service_type is None:
            raise ValueError(f"Service '{self.service_name}' is not registered.")

        # Use pooled service instances to avoid per-call instantiation overhead.
        service_instance = await _service_pool.get_or_create(self.service_type)

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
        method = getattr(service_instance, handler.split(".")[-1])
        arguments = args_to_dict(method, *args, **kwargs)
        arguments["self"] = service_instance
        return await service_func.run(arguments)
