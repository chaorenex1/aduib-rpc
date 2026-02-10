import asyncio


from aduib_rpc.server.rpc_execution.service_call import function, client
from tests.fixtures_service_module import test_add


@client(service_name="test_app")
class FixtureService:
    def ping(self) -> str:
        ...


@client(service_name="test_app")
class CaculService:
    def add(self, x, y):
        """同步加法"""
        ...

    def add2(self, data:test_add):
        """同步加法"""
        ...

    async def async_mul(self, x, y):
        """异步乘法"""
        await asyncio.sleep(0.1)
        ...

    def fail(self, x):
        """会失败的函数"""
        ...

    @function(client_stream=True, idempotent_key="numbers")
    async def client_stream_sum(self, numbers: list[int]):
        """客户端流式求和"""
        ...

    @function(server_stream=True, idempotent_key="start")
    async def server_stream_countdown(self, start: int):
        """服务端流式倒计时"""
        ...

    @function(bidirectional_stream=True, idempotent_key="messages")
    async def bidi_echo(self, messages: list[str]):
        """双向流式回声"""
        ...