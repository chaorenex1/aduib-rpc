from .service_registry import ServiceRegistry
from .in_memory import InMemoryServiceRegistry

try:
    from .nacos.nacos import NacosServiceRegistry
    _all = ["ServiceRegistry", "InMemoryServiceRegistry", "NacosServiceRegistry"]
except ImportError:
    # nacos-sdk-python is optional
    NacosServiceRegistry = None  # type: ignore
    _all = ["ServiceRegistry", "InMemoryServiceRegistry"]
__all__ = _all