import inspect
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

    lb_key: str | None = None

    @property
    def url(self) -> str:
        return self.instance.url

    @property
    def scheme(self):
        return self.instance.scheme

    def meta(self) -> dict[str, Any]:
        return self.instance.metadata

    def get_lb_value(self) -> str:
        """Get load balancing values from instance metadata."""
        lb_value = ""
        if self.lb_key and self.lb_key in self.instance.metadata:
            try:
                lb_value= str(self.instance.metadata[self.lb_key])
            except Exception:
                logger.warning("Invalid load balancing key value for %s: %s", self.instance.service_name, self.lb_key)
        return lb_value


class ServiceResolver:
    """Resolve a service name to a concrete ServiceInstance.

    Boundary:
    - Resolver only deals with discovery and load-balancing.
    - It *does not* create clients and does not perform RPC calls.
    """

    async def resolve(self, service_name: str,lb_key: str | None) -> ResolvedService | None:
        raise NotImplementedError


class RegistryServiceResolver(ServiceResolver):
    def __init__(
        self,
        registries,
        *,
        policy: LoadBalancePolicy | None = None,
        allow_private_ips: bool = True,
        allow_loopback: bool = True,
    ):
        self._registries = list(registries)
        self._policy = policy or LoadBalancePolicy.WeightedRoundRobin
        self._lb = LoadBalancerFactory.get_load_balancer(self._policy)
        self._allow_private_ips = allow_private_ips
        self._allow_loopback = allow_loopback

    def _validate_instance(self, inst: ServiceInstance, service_name: str) -> bool:
        """Validate service instance before use."""
        import ipaddress

        # 验证服务名匹配
        if inst.service_name != service_name:
            logger.error("Service name mismatch: requested=%s, got=%s", service_name, inst.service_name)
            return False

        # 验证主机地址
        try:
            ip = ipaddress.ip_address(inst.host)
            if ip.is_private and not self._allow_private_ips:
                logger.error("Private IP rejected: %s", inst.host)
                return False
            if ip.is_loopback and not self._allow_loopback:
                logger.error("Loopback IP rejected: %s", inst.host)
                return False
        except ValueError:
            # 不是 IP，验证主机名
            if inst.host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
                if not self._allow_loopback:
                    logger.error("Loopback hostname rejected: %s", inst.host)
                    return False

        # 验证端口范围
        if not (1 <= inst.port <= 65535):
            logger.error("Invalid port: %d", inst.port)
            return False

        return True

    def _get_lb_value(self, instance: ServiceInstance,lb_key: str | None) -> str:
        """Get load balancing values from instance metadata."""
        lb_value = ""
        if lb_key and lb_key in instance.metadata:
            try:
                lb_value= str(instance.metadata[lb_key])
            except Exception:
                logger.warning("Invalid load balancing key value for %s: %s", instance.service_name, lb_key)
        return lb_value

    async def resolve(self, service_name: str, lb_key: str | None) -> ResolvedService | None:
        for registry in self._registries:
            try:
                if hasattr(registry, "list_instances"):
                    result = registry.list_instances(service_name)
                    if inspect.isawaitable(result):
                        result = await result
                    instances = [i for i in (result or []) if isinstance(i, ServiceInstance) and self._validate_instance(i, service_name)]
                    if not instances:
                        continue
                    inst = self._lb.select_instance(list(instances), key=self._get_lb_value(instances[0],lb_key))
                else:
                    # Backward compatibility for registries that haven't been updated.
                    inst = registry.discover_service(service_name)
                    if inspect.isawaitable(inst):
                        inst = await inst
            except Exception:
                logger.exception("Service discovery failed for %s via %s", service_name, type(registry).__name__)
                continue

            if inst:
                if isinstance(inst, dict):
                    logger.warning("Registry %s returned dict for %s; expected ServiceInstance", type(registry).__name__, service_name)
                    continue
                if not isinstance(inst, ServiceInstance):
                    logger.warning(
                        "Registry %s returned %s for %s; expected ServiceInstance",
                        type(registry).__name__,
                        type(inst).__name__,
                        service_name,
                    )
                    continue
                if not self._validate_instance(inst, service_name):
                    continue
                return ResolvedService(instance=inst,lb_key=lb_key)
        return None
