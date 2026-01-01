import pytest

from aduib_rpc.server.rpc_execution.runtime import RpcRuntime
from aduib_rpc.server.rpc_execution.service_call import ServiceCaller, service


@pytest.mark.asyncio
async def test_service_registration_isolated_by_runtime():
    rt1 = RpcRuntime()
    rt2 = RpcRuntime()

    @service("S", runtime=rt1)
    class S1:
        def add(self, x: int, y: int) -> int:
            return x + y

    @service("S", runtime=rt2)
    class S2:
        def add(self, x: int, y: int) -> int:
            return x * y

    caller1 = ServiceCaller.from_service_caller("S.S1", runtime=rt1)
    caller2 = ServiceCaller.from_service_caller("S.S2", runtime=rt2)

    assert await caller1.call("add", 2, 3) == 5
    assert await caller2.call("add", 2, 3) == 6

