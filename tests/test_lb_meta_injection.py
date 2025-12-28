import types
import pytest
import importlib

from aduib_rpc.server.rpc_execution.service_call import client_function
from aduib_rpc.server.rpc_execution.runtime import RpcRuntime


@pytest.mark.asyncio
async def test_client_function_passes_lb_meta_into_resolver(monkeypatch):
    class DummyRegistry:
        def list_instances(self, service_name: str):
            return []

    from aduib_rpc.discover.registry import registry_factory

    monkeypatch.setattr(
        registry_factory.ServiceRegistryFactory,
        "list_registries",
        classmethod(lambda cls: [DummyRegistry()]),
    )

    captured = {}

    # Patch resolver to capture the policy/key parameters.
    sr = importlib.import_module("aduib_rpc.client.service_resolver")

    real_init = sr.RegistryServiceResolver.__init__

    def fake_init(self, registries, *, policy=None, key=None):
        captured["policy"] = policy
        captured["key"] = key
        return real_init(self, registries, policy=policy, key=key)

    monkeypatch.setattr(sr.RegistryServiceResolver, "__init__", fake_init)

    async def dummy(self, x: int, meta=None):
        return x

    rt = RpcRuntime()
    wrapped = client_function(func=dummy, service_name="S", runtime=rt)

    with pytest.raises(RuntimeError):
        await wrapped(types.SimpleNamespace(), 1, meta={"lb_policy": 2, "lb_key": "user-1"})

    assert captured["key"] == "user-1"
    assert captured["policy"] is not None
