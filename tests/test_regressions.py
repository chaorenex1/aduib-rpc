import pytest

import httpx
from typing import Any, cast

from aduib_rpc.client.errors import ClientHTTPError
from aduib_rpc.client.transports.jsonrpc import JsonRpcTransport
from aduib_rpc.server.context import ServerContext
from aduib_rpc.client.base_client import BaseAduibRpcClient
from aduib_rpc.client.config import ClientConfig
from aduib_rpc.client.midwares import ClientContext
from aduib_rpc.client.transports.base import ClientTransport
from aduib_rpc.utils.constant import SecuritySchemes, TransportSchemes


@pytest.mark.asyncio
async def test_jsonrpc_transport_timeout_maps_to_client_http_error():
    class _FakeHTTPXClient:
        async def post(self, *args: Any, **kwargs: Any):
            raise httpx.ReadTimeout("boom", request=httpx.Request("POST", "http://example.com"))

    transport = JsonRpcTransport(httpx_client=cast(httpx.AsyncClient, _FakeHTTPXClient()), url="http://example.com")

    with pytest.raises(ClientHTTPError) as ei:
        await transport._send_request({"jsonrpc": "2.0", "method": "x", "params": {}, "id": "1"})

    assert ei.value.status_code == 408


def test_server_context_has_isolated_state_and_metadata_dicts():
    c1 = ServerContext()
    c2 = ServerContext()

    c1.state["k"] = "v"
    c1.metadata["m"] = 1

    assert "k" not in c2.state
    assert "m" not in c2.metadata


@pytest.mark.asyncio
async def test_base_client_completion_with_meta_none_does_not_crash():
    class _DummyTransport(ClientTransport):
        async def completion(self, request, *, context):
            return "ok"

        async def completion_stream(self, request, *, context):
            async def _gen():
                if False:
                    yield "ok"  # pragma: no cover
            return _gen()

    client = BaseAduibRpcClient(config=ClientConfig(streaming=False), transport=_DummyTransport())

    out = []
    async for item in client.completion(name="CrawlService", method="m", data={"a": 1}, meta=None):
        out.append(item)

    assert out == ["ok"]


def test_client_context_schema_defaults_when_missing():
    ctx = ClientContext()
    assert ctx.get_schema() == SecuritySchemes.APIKey


def test_transport_scheme_defaults_when_missing():
    assert TransportSchemes.to_original(None) == TransportSchemes.JSONRPC
