import pytest

from aduib_rpc.server.request_handlers.default_request_handler import DefaultRequestHandler
from aduib_rpc.server.rpc_execution.service_call import FuncCallContext, service
from aduib_rpc.types import AduibRpcRequest


@pytest.mark.asyncio
async def test_default_request_handler_routes_v2_method() -> None:
    FuncCallContext.reset()

    @service("MyService")
    class MyService:
        def add(self, x: int, y: int) -> int:
            return x + y

    handler = DefaultRequestHandler(request_executors={})
    req = AduibRpcRequest(id="1", name="MyService.MyService",method="rpc.v2/MyService/MyService.add", data={"x": 1, "y": 2})
    resp = await handler.on_message(req, None)
    assert resp.result == 3


@pytest.mark.asyncio
async def test_default_request_handler_routes_v3_method() -> None:
    FuncCallContext.reset()

    @service("MyService")
    class MyService:
        def add(self, x: int, y: int) -> int:
            return x + y

    handler = DefaultRequestHandler(request_executors={})
    req = AduibRpcRequest(id="1",method="rpc.v2/MyService/MyService.add",
                          data={"x": 1, "y": 2})
    resp = await handler.on_message(req, None)
    assert resp.result == 3


@pytest.mark.asyncio
async def test_default_request_handler_routes_legacy_method() -> None:
    FuncCallContext.reset()

    @service("MyService")
    class MyService:
        def add(self, x: int, y: int) -> int:
            return x + y

    handler = DefaultRequestHandler(request_executors={})
    req = AduibRpcRequest(id="1", name="MyService.MyService",method="MyService.MyService.add", data={"x": 2, "y": 5})
    resp = await handler.on_message(req, None)
    assert resp.result == 7


@pytest.mark.asyncio
async def test_default_request_handler_routes_legacy_method_v2() -> None:
    FuncCallContext.reset()

    @service("MyService")
    class MyService:
        def add(self, x: int, y: int) -> int:
            return x + y

    handler = DefaultRequestHandler(request_executors={})
    req = AduibRpcRequest(id="1",method="MyService.MyService.add", data={"x": 2, "y": 5})
    resp = await handler.on_message(req, None)
    assert resp.result == 7
