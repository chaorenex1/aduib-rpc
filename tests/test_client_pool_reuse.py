import pytest

from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.client.config import ClientConfig
from aduib_rpc.utils.constant import TransportSchemes


@pytest.mark.asyncio
async def test_httpx_pool_reuses_client_for_same_url():
    # Two factories with pooling enabled should reuse the same underlying httpx.AsyncClient
    cfg1 = ClientConfig(streaming=False, supported_transports=[TransportSchemes.JSONRPC], pooling_enabled=True)
    cfg2 = ClientConfig(streaming=False, supported_transports=[TransportSchemes.JSONRPC], pooling_enabled=True)

    f1 = AduibRpcClientFactory(cfg1)
    f2 = AduibRpcClientFactory(cfg2)

    c1 = f1.create("http://example.com", server_preferred=TransportSchemes.JSONRPC)
    c2 = f2.create("http://example.com", server_preferred=TransportSchemes.JSONRPC)

    assert c1._transport.httpx_client is c2._transport.httpx_client  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_httpx_pool_disabled_does_not_reuse():
    cfg1 = ClientConfig(streaming=False, supported_transports=[TransportSchemes.JSONRPC], pooling_enabled=False)
    cfg2 = ClientConfig(streaming=False, supported_transports=[TransportSchemes.JSONRPC], pooling_enabled=False)

    f1 = AduibRpcClientFactory(cfg1)
    f2 = AduibRpcClientFactory(cfg2)

    c1 = f1.create("http://example.com", server_preferred=TransportSchemes.JSONRPC)
    c2 = f2.create("http://example.com", server_preferred=TransportSchemes.JSONRPC)

    assert c1._transport.httpx_client is not c2._transport.httpx_client  # type: ignore[attr-defined]

