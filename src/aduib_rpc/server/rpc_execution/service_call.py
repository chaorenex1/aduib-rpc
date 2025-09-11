import asyncio
import functools
import inspect
import logging
from typing import Any, Callable

import anyio

from aduib_rpc.client import ClientRequestInterceptor
from aduib_rpc.client.auth import CredentialsProvider, InMemoryCredentialsProvider
from aduib_rpc.client.auth.interceptor import AuthInterceptor
from aduib_rpc.server.rpc_execution.service_func import ServiceFunc
from aduib_rpc.utils.async_utils import AsyncUtils

logger = logging.getLogger(__name__)

service_instances: dict[str, Any] = {}

client_instances: dict[str, Any] = {}

service_funcs: dict[str, ServiceFunc] = {}
client_funcs: dict[str, ServiceFunc] = {}
interceptors: list[ClientRequestInterceptor] = []
credentials_provider: CredentialsProvider | None = None


class FuncCallContext:
    @classmethod
    def add_interceptor(cls, interceptor: ClientRequestInterceptor) -> None:
        interceptors.append(interceptor)

    @classmethod
    def get_interceptors(cls) -> list[ClientRequestInterceptor]:
        return interceptors

    @classmethod
    def set_credentials_provider(cls, provider: CredentialsProvider) -> None:
        global credentials_provider
        credentials_provider = provider

    @classmethod
    def enable_auth(cls):
        global credentials_provider
        if not credentials_provider:
            credentials_provider = InMemoryCredentialsProvider()
        no_auth = any(isinstance(interceptor, AuthInterceptor) for interceptor in interceptors)
        if not no_auth:
            interceptors.append(AuthInterceptor(credentials_provider))

    @classmethod
    def get_service_func_names(cls) -> list[str]:
        global service_funcs
        return list(service_funcs.keys())

    @classmethod
    def get_client_func_names(cls) -> list[str]:
        global client_funcs
        return list(client_funcs.keys())


import importlib
import pkgutil

def load_service_plugins(package_name: str = __name__):
    """
    自动加载指定 package 下所有子模块，触发 @service 和 @client 装饰器的执行。
    """
    package = importlib.import_module(package_name)
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        full_module_name = f"{package_name}.{module_name}"
        importlib.import_module(full_module_name)


def fallback_function(fallback: Callable[..., Any], *args, **kwargs) -> Any:
    try:
        # fallback to async execution
        if asyncio.iscoroutinefunction(fallback):
            return AsyncUtils.run_async(fallback(*args, **kwargs))
        else:
            return fallback(*args, **kwargs)
    except Exception as e:
        raise e


def service_function(  # noqa: PLR0915
        func: Callable | None = None,
        *,
        func_name: str | None = None,
        fallback: Callable[..., Any] = None
) -> Callable:
    """Decorator to register a service function."""
    if func is None:
        return functools.partial(
            service_function,
            func_name=func_name,
            fallback=fallback,
        )

    actual_func_name = func_name or f'{func.__module__}.{func.__name__}'

    is_async_func = inspect.iscoroutinefunction(func)

    logger.debug(
        'Start wrap func for %s, is_async_func %s',
        actual_func_name,
        is_async_func,
    )

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        """Async Wrapper for the decorator."""
        logger.debug('Start async wrapper for service %s', actual_func_name)
        try:
            # Async wrapper, await for the function call to complete.
            result = await func(*args, **kwargs)
        # asyncio.CancelledError extends from BaseException
        except asyncio.CancelledError as ce:
            logger.debug('CancelledError in service %s', actual_func_name)
            if fallback:
                logger.info('Calling fallback function for %s', actual_func_name)
                result = fallback_function(fallback, *args, **kwargs)
            else:
                raise ce
        except Exception as e:
            logger.warning('Exception in service %s: %s', actual_func_name, e, exc_info=True)
            if fallback:
                logger.info('Calling fallback function for %s', actual_func_name)
                result = fallback_function(fallback, *args, **kwargs)
            else:
                raise e
        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        """Sync Wrapper for the decorator."""
        logger.debug('Start sync wrapper service for %s', actual_func_name)
        try:
            # sync wrapper, the function call to complete.
            result = func(*args, **kwargs)
        except Exception as e:
            logger.warning('Exception in service %s: %s', actual_func_name, e, exc_info=True)
            if fallback:
                logger.info('Calling fallback function for %s', actual_func_name)
                result = fallback_function(fallback, *args, **kwargs)
            else:
                raise e
        return result

    return async_wrapper if is_async_func else sync_wrapper


def client_function(  # noqa: PLR0915
        func: Callable | None = None,
        *,
        func_name: str | None = None,
        service_name: str | None = None,
        stream: bool = True,
        fallback: Callable[..., Any] = None
) -> Callable:
    """Decorator to register a service function."""
    if func is None:
        return functools.partial(
            client_function,
            func_name=func_name,
            service_name=service_name,
            stream=stream,
            fallback=fallback,
        )

    actual_func_name = func_name or f'{func.__module__}.{func.__name__}'

    is_async_func = inspect.iscoroutinefunction(func)

    logger.debug(
        'Start call for %s, is_async_func %s',
        actual_func_name,
        is_async_func,
    )

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        """Async Wrapper for the decorator."""
        logger.debug('Start async wrapper client for %s', actual_func_name)
        try:
            # Async wrapper, await for the function call to complete.
            # result = await func(*args, **kwargs)
            result = None
            from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
            from aduib_rpc.client.client_factory import AduibRpcClientFactory
            registries = ServiceRegistryFactory.list_registries()
            if not registries:
                raise RuntimeError("No service registry available")
            # service_name =actual_func_name.split('.')[0]
            for registry in registries:
                service = registry.discover_service(service_name)
                if service:
                    client = AduibRpcClientFactory.create_client(service.url, stream, service.scheme,interceptors=FuncCallContext.get_interceptors())
                    dict_data = args_to_dict(func, *args, **kwargs)
                    dict_data.pop('self')
                    resp = client.completion(service_name + '.' + actual_func_name, dict_data,
                                             service.get_service_info())
                    logger.debug('called remote service %s', actual_func_name)
                    async for r in resp:
                        result = r.result
                break
        # asyncio.CancelledError extends from BaseException
        except asyncio.CancelledError as ce:
            logger.debug('CancelledError in service %s', actual_func_name)
            if fallback:
                logger.info('Calling fallback function for %s', actual_func_name)
                result = fallback_function(fallback, *args, **kwargs)
            else:
                raise ce
        except Exception as e:
            logger.warning('Exception in service %s: %s', actual_func_name, e, exc_info=True)
            if fallback:
                logger.info('Calling fallback function for %s', actual_func_name)
                result = fallback_function(fallback, *args, **kwargs)
            else:
                raise e
        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        """Sync Wrapper for the decorator."""
        logger.debug('Start sync wrapper client for %s', actual_func_name)
        try:
            # sync wrapper, the function call to complete.
            # result = func(*args, **kwargs)
            result = None
            from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
            from aduib_rpc.client.client_factory import AduibRpcClientFactory
            def run_in_new_loop():
                # 在新线程中创建独立的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    async def async_call():
                        registries = ServiceRegistryFactory.list_registries()
                        if not registries:
                            raise RuntimeError("No service registry available")

                        for registry in registries:
                            service = registry.discover_service(service_name)
                            if service:
                                client = AduibRpcClientFactory.create_client(service.url, stream, service.scheme,interceptors=FuncCallContext.get_interceptors())
                                dict_data = args_to_dict(func, *args, **kwargs)
                                dict_data.pop('self', None)  # 使用 pop 的默认值参数
                                resp = client.completion(service_name + '.' + actual_func_name, dict_data,
                                                         service.get_service_info())
                                logger.debug('called remote service %s', actual_func_name)

                                async for r in resp:
                                    return r.result
                            break
                        return None

                    return loop.run_until_complete(async_call())
                finally:
                    loop.close()

            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_new_loop)
                result = future.result()
        except Exception as e:
            logger.warning('Exception in service %s: %s', actual_func_name, e, exc_info=True)
            if fallback:
                logger.info('Calling fallback function for %s', actual_func_name)
                result = fallback_function(fallback, *args, **kwargs)
            else:
                raise e
        return result

    return async_wrapper if is_async_func else sync_wrapper


def service(service_name: str):
    """Decorator to register a service executor class."""

    def decorator(cls: Any):
        for method_name, function in inspect.getmembers(cls, inspect.isfunction):
            if method_name.startswith('__') and method_name.endswith('__'):
                continue
            service_fuc_name = f'{service_name or cls.__name__}.{method_name}'
            setattr(
                cls,
                method_name,
                service_function(func_name=service_fuc_name, fallback=None)(function),
            )
            wrapper_func = getattr(cls, method_name)
            service_func: ServiceFunc = ServiceFunc.from_function(function, service_fuc_name, function.__doc__)
            service_func.wrap_fn = wrapper_func
            service_funcs[service_fuc_name] = service_func
        service_instances[service_name] = cls
        return cls

    return decorator


def client(service_name: str, stream: bool = True, fallback: Callable[..., Any] = None):
    """Decorator to call a service executor class."""

    def decorator(cls: Any):
        for method_name, function in inspect.getmembers(cls, inspect.isfunction):
            if method_name.startswith('__') and method_name.endswith('__'):
                continue
            client_fuc_name = f'{cls.__name__}.{method_name}'
            setattr(
                cls,
                method_name,
                client_function(func_name=client_fuc_name, service_name=service_name, stream=stream, fallback=fallback)(
                    function),
            )
            wrapper_func = getattr(cls, method_name)
            client_func: ServiceFunc = ServiceFunc.from_function(function, client_fuc_name, function.__doc__)
            client_func.wrap_fn = wrapper_func
            client_funcs[client_fuc_name] = client_func
        if fallback:
            setattr(cls, 'fallback', staticmethod(fallback))
        client_instances[cls.__name__] = cls
        return cls

    return decorator


def args_to_dict(func, *args, **kwargs):
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()  # 填充默认值
    return dict(bound.arguments)


# ------------------------------
# Service 调用器
# ------------------------------
class ServiceCaller:
    def __init__(self, service_type: Any, service_name: str):
        self.service_type = service_type
        self.service_name = service_name

    @classmethod
    def from_service_caller(cls, service_name: str):
        service_type = service_instances.get(service_name)
        return cls(service_type, service_name)

    async def call(self, func_name: str, *args, **kwargs):
        service_fuc_name = f'{self.service_name}.{func_name}'
        logger.debug("Calling service function: %s", service_fuc_name)
        service_func = service_funcs.get(service_fuc_name)
        if not service_func:
            raise ValueError(f"Service function '{func_name}' is not registered.")
        service_instance = self.service_type()
        func = getattr(service_instance, func_name)
        arguments = args_to_dict(func, *args, **kwargs)
        arguments['self'] = service_instance
        return await service_func.run(arguments)


class ClientCaller:
    def __init__(self, service_type: Any, service_name: str):
        self.service_type = service_type
        self.service_name = service_name

    @classmethod
    def from_client_caller(cls, service_name: str):
        service_type = client_instances.get(service_name)
        return cls(service_type, service_name)

    async def call(self, func_name: str, *args, **kwargs):
        service_fuc_name = f'{self.service_name}.{func_name}'
        service_func = client_funcs.get(service_fuc_name)
        if not service_func:
            raise ValueError(f"Client function '{func_name}' is not registered.")
        service_instance = self.service_type()
        func = getattr(service_instance, func_name)
        arguments = args_to_dict(func, *args, **kwargs)
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
