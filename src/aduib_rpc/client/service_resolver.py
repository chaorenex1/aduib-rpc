import logging
from dataclasses import dataclass
from typing import Any

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.load_balance import LoadBalancerFactory
from aduib_rpc.utils.constant import LoadBalancePolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedService:
    """A resolved remote service endpoint, ready for client creation/call."""

    instance: ServiceInstance

    @property
    def url(self) -> str:
        return self.instance.url

    @property
    def scheme(self):
        return self.instance.scheme

    def meta(self) -> dict[str, Any]:
        return self.instance.get_service_info()


class ServiceResolver:
    """Resolve a service name to a concrete ServiceInstance.

    Boundary:
    - Resolver only deals with discovery and load-balancing.
    - It *does not* create clients and does not perform RPC calls.
    """

    def resolve(self, service_name: str) -> ResolvedService | None:
        raise NotImplementedError


class RegistryServiceResolver(ServiceResolver):
    def __init__(self, registries, *, policy: LoadBalancePolicy | None = None, key: str | None = None):
        self._registries = list(registries)
        self._policy = policy or LoadBalancePolicy.WeightedRoundRobin
        self._key = key
        self._lb = LoadBalancerFactory.get_load_balancer(self._policy)

    def resolve(self, service_name: str) -> ResolvedService | None:
        for registry in self._registries:
            try:
                if hasattr(registry, "list_instances"):
                    instances = registry.list_instances(service_name)
                    inst = self._lb.select_instance(instances, key=self._key)
                else:
                    # Backward compatibility for registries that haven't been updated.
                    inst = registry.discover_service(service_name)
            except Exception:
                logger.exception("Service discovery failed for %s via %s", service_name, type(registry).__name__)
                continue

            if inst:
                if isinstance(inst, dict):
                    logger.warning("Registry %s returned dict for %s; expected ServiceInstance", type(registry).__name__, service_name)
                    continue
                return ResolvedService(instance=inst)
        return None
