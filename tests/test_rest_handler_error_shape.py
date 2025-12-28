import pytest

from aduib_rpc.server.request_handlers.rest_handler import RESTHandler
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.server.context import ServerContext


class BoomHandler(RequestHandler):
    async def on_message(self, message, context=None):  # type: ignore[override]
        raise RuntimeError("boom")

    async def on_stream_message(self, message, context=None):  # type: ignore[override]
        raise RuntimeError("boom")


class FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


@pytest.mark.asyncio
async def test_rest_handler_exception_returns_structured_error():
    handler = RESTHandler(request_handler=BoomHandler())
    req = FakeRequest(body=b"not-a-proto")
    resp = await handler.on_message(req, ServerContext(state={}, metadata={}))  # type: ignore[arg-type]

    assert resp["status"] == "error"
    # proto schema uses string code
    assert resp["error"]["code"] in ("-32603", -32603)
    assert resp["error"]["message"]
