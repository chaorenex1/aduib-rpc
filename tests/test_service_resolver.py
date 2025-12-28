from aduib_rpc.client.service_resolver import RegistryServiceResolver
from aduib_rpc.discover.entities import ServiceInstance


class FakeRegistry:
    def __init__(self, instances: list[ServiceInstance]):
        self._instances = instances

    def list_instances(self, service_name: str) -> list[ServiceInstance]:
        return list(self._instances)

    def discover_service(self, service_name: str):
        return self._instances[0] if self._instances else None


def test_registry_service_resolver_picks_first_available_instance():
    inst = ServiceInstance(service_name="S", host="127.0.0.1", port=1234)
    resolver = RegistryServiceResolver([FakeRegistry([]), FakeRegistry([inst])])

    resolved = resolver.resolve("S")
    assert resolved is not None
    assert resolved.url == inst.url
