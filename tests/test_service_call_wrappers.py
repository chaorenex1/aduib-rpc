import pytest

from aduib_rpc.server.rpc_execution.service_call import FuncCallContext, client_function, service_function


@pytest.mark.asyncio
async def test_service_function_fallback_on_exception_async():
    FuncCallContext.reset()

    async def boom(x: int) -> int:
        raise RuntimeError("boom")

    def fb(x: int) -> int:
        return 42

    wrapped = service_function(func_name="S.boom", fallback=fb)(boom)
    assert await wrapped(1) == 42


def test_service_function_fallback_on_exception_sync():
    FuncCallContext.reset()

    def boom(x: int) -> int:
        raise RuntimeError("boom")

    def fb(x: int) -> int:
        return 42

    wrapped = service_function(func_name="S.boom", fallback=fb)(boom)
    assert wrapped(1) == 42


@pytest.mark.asyncio
async def test_client_function_requires_service_name():
    FuncCallContext.reset()

    async def f(x: int) -> int:
        return x

    wrapped = client_function(func_name="C.f", service_name=None)(f)
    with pytest.raises(ValueError):
        await wrapped(1)
