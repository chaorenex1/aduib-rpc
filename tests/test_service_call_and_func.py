import asyncio

import pytest

from aduib_rpc.server.rpc_execution.service_call import service, ServiceCaller
from aduib_rpc.server.rpc_execution.service_func import ServiceFunc


@pytest.mark.asyncio
async def test_service_caller_errors_for_missing_service_and_func():
    caller = ServiceCaller.from_service_caller("NotRegistered")
    with pytest.raises(ValueError):
        await caller.call("x")


@pytest.mark.asyncio
async def test_service_decorator_registers_and_executes():
    @service("Calc")
    class Calc:
        def add(self, x: int, y: int) -> int:
            return x + y

        async def mul(self, x: int, y: int) -> int:
            await asyncio.sleep(0)
            return x * y

    caller = ServiceCaller.from_service_caller("Calc.Calc")
    assert await caller.call("add", 1, 2) == 3
    assert await caller.call("mul", 2, 3) == 6


@pytest.mark.asyncio
async def test_service_func_run_preserves_original_exception_context():
    def boom(x: int) -> int:
        raise ValueError("bad")

    sf = ServiceFunc.from_function(boom, name="boom")
    # during normal wiring, wrap_fn is set; set here for direct run
    sf.wrap_fn = boom

    with pytest.raises(RuntimeError) as ei:
        await sf.run({"x": 1})

    assert "Error executing tool boom" in str(ei.value)
    assert isinstance(ei.value.__cause__, ValueError)

