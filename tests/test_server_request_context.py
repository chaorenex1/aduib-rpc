from aduib_rpc.server.rpc_execution.context import RequestContext
from aduib_rpc.types import AduibRpcRequest


def test_request_context_metadata_defaults_and_override():
    req = AduibRpcRequest(method='m', data={'x': 1}, meta={'model': 'foo', 'stream': 'false'})

    ctx1 = RequestContext(request=req)
    assert ctx1.get_metadata() == req.meta

    override = {'a': 1}
    ctx2 = RequestContext(request=req, metadata=override)
    assert ctx2.get_metadata() == override


def test_request_context_handles_none_request():
    ctx = RequestContext(request=None)
    assert ctx.get_metadata() is None
    assert ctx.get_method() is None

