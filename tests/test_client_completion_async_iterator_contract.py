import pytest

from aduib_rpc.server.rpc_execution import service_call


class _FakeResponse:
    def __init__(self, result):
        self.result = result


class _FakeResolved:
    url = "http://example"
    scheme = "rest"

    def meta(self):
        return {}


class _FakeResolver:
    def __init__(self, registries, policy=None, key=None):
        pass

    def resolve(self, service_name: str):
        return _FakeResolved()


class _FakeRegistryFactory:
    @staticmethod
    def list_registries():
        return [object()]


class _FakeClient:
    # Important: completion returns an async generator object (AsyncIterator), NOT awaitable.
    def completion(self, method, data=None, meta=None):
        async def gen():
            yield _FakeResponse("ok")

        return gen()


class _FakeClientFactory:
    @staticmethod
    def create_client(url, stream, scheme, interceptors=None):
        return _FakeClient()


@pytest.mark.asyncio
async def test_client_function_does_not_await_async_iterator(monkeypatch):
    # Patch the imports used inside service_call.client_function._client_call
    monkeypatch.setattr(
        service_call,
        "_compose_remote_method",
        lambda service_name, handler_name: f"{service_name}.{handler_name}",
    )

    monkeypatch.setitem(
        __import__("sys").modules,
        "aduib_rpc.discover.registry.registry_factory",
        type(
            "M",
            (),
            {"ServiceRegistryFactory": _FakeRegistryFactory},
        )(),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "aduib_rpc.client.client_factory",
        type(
            "M",
            (),
            {"AduibRpcClientFactory": _FakeClientFactory},
        )(),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "aduib_rpc.client.service_resolver",
        type(
            "M",
            (),
            {"RegistryServiceResolver": _FakeResolver},
        )(),
    )

    @service_call.client_function(service_name="CrawlService")
    async def crawl(urls, notify_url=None):
        raise AssertionError("body should be ignored; wrapper calls remote")

    res = await crawl(["https://example.com"], None)
    assert res == "ok"

