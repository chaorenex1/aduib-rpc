import pytest

from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.server.request_handlers.thrift_handler import ThriftHandler
from aduib_rpc.thrift.ttypes import RpcTask
from aduib_rpc.utils import thrift_utils


class BoomHandler(RequestHandler):
    async def on_message(self, message, context=None):  # type: ignore[override]
        raise RuntimeError("boom")

    async def on_stream_message(self, message, context=None):  # type: ignore[override]
        raise RuntimeError("boom")


def test_thrift_handler_exception_returns_structured_error():
    handler = ThriftHandler(request_handler=BoomHandler())
    task = RpcTask(id="1", method="S.m", meta="{}", data=thrift_utils.ToProto.taskData({}))

    resp = handler.completion(task)
    assert resp.status == "error"
    assert resp.error is not None
    assert resp.error.message
    # code is a string in thrift schema
    assert resp.error.code is not None
