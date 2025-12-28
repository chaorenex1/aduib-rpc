import pytest

from aduib_rpc.discover.entities.service_instance import ServiceInstance
from aduib_rpc.discover.registry.registry_factory import ServiceRegistryFactory
from aduib_rpc.discover.registry.in_memory import InMemoryServiceRegistry
from aduib_rpc.utils.constant import LoadBalancePolicy, AIProtocols, TransportSchemes


@pytest.mark.asyncio
async def test_service_registry_factory_creates_and_registers_in_memory_instance():
    # Decorator registers it at import time.
    assert 'in_memory' in ServiceRegistryFactory.registry_classes

    r1 = ServiceRegistryFactory.from_service_registry('in_memory', policy=LoadBalancePolicy.WeightedRoundRobin)
    r2 = ServiceRegistryFactory.from_service_registry('in_memory', policy=LoadBalancePolicy.WeightedRoundRobin)

    assert isinstance(r1, InMemoryServiceRegistry)
    # Factory should cache instances per registry_type.
    assert r1 is r2

    # Missing service should return None.
    assert r1.discover_service('missing') is None

    service_info = ServiceInstance(
        service_name='test',
        host='127.0.0.1',
        port=12345,
        protocol=AIProtocols.AduibRpc,
        weight=1,
        scheme=TransportSchemes.JSONRPC,
    )

    await r1.register_service(service_info)
    assert r1.discover_service('test') is not None
