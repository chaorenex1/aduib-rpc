import pytest

from aduib_rpc.server.request_handlers.jsonrpc_handler import JSONRPCHandler
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.types import (
    JSONRPCErrorResponse,
    JsonRpcMessageRequest,
    JsonRpcMessageResponse,
    JSONRPCError,
    AduibRpcRequest,
)


class BoomHandler(RequestHandler):
    async def on_message(self, message, context=None):  # type: ignore[override]
        raise RuntimeError("boom")

    async def on_stream_message(self, message, context=None):  # type: ignore[override]
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_jsonrpc_handler_exception_returns_structured_error():
    handler = JSONRPCHandler(BoomHandler())
    req = JsonRpcMessageRequest(
        id=1,
        jsonrpc="2.0",
        method="message/completion",
        params=AduibRpcRequest(method="S.m", data={}),
    )

    resp: JsonRpcMessageResponse = await handler.on_message(req)
    assert isinstance(resp.root, JSONRPCErrorResponse)
    assert isinstance(resp.root.error, JSONRPCError)
    assert resp.root.error.code == -32603
    assert resp.root.error.message

