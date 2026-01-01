import inspect

import pytest

from aduib_rpc.server.rpc_execution.service_call import service_function


@pytest.mark.asyncio
async def test_service_function_async_wrapper_passes_through_async_generator():
    async def handler():
        async def gen():
            yield 1
            yield 2

        return gen()

    wrapped = service_function(handler)

    res = await wrapped()
    assert inspect.isasyncgen(res)

    items = []
    async for x in res:
        items.append(x)

    assert items == [1, 2]


def test_service_function_sync_wrapper_rejects_async_generator_return():
    def handler():
        async def gen():
            yield 1

        return gen()

    wrapped = service_function(handler)

    with pytest.raises(TypeError, match=r"returned an async generator"):
        wrapped()

