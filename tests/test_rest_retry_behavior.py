import httpx
import pytest

from aduib_rpc.client.transports.rest import RestTransport
from aduib_rpc.client.midwares import ClientContext
from aduib_rpc.types import AduibRpcRequest


class _FakeClient:
    def __init__(self):
        self.calls = 0

    def build_request(self, method: str, url: str, json=None, **kwargs):
        return httpx.Request(method, url, json=json)

    async def send(self, request: httpx.Request):
        self.calls += 1
        if self.calls == 1:
            # first call fails with retryable status
            return httpx.Response(503, request=request, json={"error": "boom"})
        return httpx.Response(200, request=request, json={"ok": True})


@pytest.mark.asyncio
async def test_rest_retry_requires_idempotent():
    t = RestTransport(_FakeClient(), url="http://example.com")
    ctx = ClientContext()

    req = AduibRpcRequest(method="m", data=None, meta={"retry_enabled": True, "retry_max_attempts": 2})
    # idempotent not set => should NOT retry => first 503 returns error
    with pytest.raises(Exception):
        await t._send_post_request("/x", {"a": 1}, {}, request_meta=req.meta)


@pytest.mark.asyncio
async def test_rest_retry_retries_when_idempotent():
    c = _FakeClient()
    t = RestTransport(c, url="http://example.com")

    req = AduibRpcRequest(method="m", data=None, meta={"retry_enabled": True, "retry_max_attempts": 2, "idempotent": True})
    out = await t._send_post_request("/x", {"a": 1}, {}, request_meta=req.meta)
    assert out == {"ok": True}
    assert c.calls == 2

