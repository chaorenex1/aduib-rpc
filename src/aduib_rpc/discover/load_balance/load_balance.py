import hashlib
import itertools
from abc import ABC, abstractmethod
import random
from bisect import bisect

from aduib_rpc.discover.entities import ServiceInstance


class LoadBalancer(ABC):
    """Abstract base class for a load balancer."""

    @abstractmethod
    def select_instance(self,instances: list[ServiceInstance],key: str | None = None) -> ServiceInstance | None:
        """Selects an instance from the available instances.

        Returns:
            The selected instance's address as a string.
        """


class WeightedRoundRobinLB(LoadBalancer):
    """A simple weighted round-robin load balancer.
    This load balancer selects instances based on their assigned weights,
    ensuring that instances with higher weights are chosen more frequently.
    """
    def __init__(self):
        self._iter = None
        self._pool = None

    def select_instance(self,instances: list[ServiceInstance], key: str | None = None) -> ServiceInstance | None:
        self._pool = list(itertools.chain.from_iterable(
            [inst] * inst.weight for inst in instances
        ))
        self._iter = itertools.cycle(self._pool)
        return next(self._iter, None)


class RandomLB(LoadBalancer):
    """A simple random load balancer.
    This load balancer selects instances randomly from the available instances.
    """

    def select_instance(self,instances: list[ServiceInstance], key: str | None = None) -> ServiceInstance | None:
        if not instances:
            return None
        return random.choice(instances)


class ConsistentHashLB(LoadBalancer):
    """A consistent hashing load balancer.
    This load balancer uses consistent hashing to map keys to instances,
    ensuring minimal disruption when instances are added or removed.
    """
    def __init__(self,virtual_nodes: int = 100):
        self.ring = {}
        self.sorted_keys = []
        self.virtual_nodes = virtual_nodes

    def init_hash_ring(self, instances: list[ServiceInstance], virtual_nodes: int = 100):
        self.ring = {}
        self.sorted_keys = []

        for inst in instances:
            for i in range(virtual_nodes):
                node_key = f"{inst.instance_id}#{i}"
                hash_val = self._hash(node_key)
                self.ring[hash_val] = inst
                self.sorted_keys.append(hash_val)

        self.sorted_keys.sort()

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)

    def select_instance(self,instances: list[ServiceInstance], key: str | None = None) -> ServiceInstance | None:
        self.init_hash_ring(instances, self.virtual_nodes)
        if not self.ring:
            return None
        if key is None:
            # 如果没有 key，退化成随机
            return random.choice(list(self.ring.values()))

        hash_val = self._hash(key)
        idx = bisect(self.sorted_keys, hash_val)
        if idx == len(self.sorted_keys):
            idx = 0
        return self.ring[self.sorted_keys[idx]]

