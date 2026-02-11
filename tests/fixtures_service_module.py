import asyncio

from pydantic import BaseModel

from aduib_rpc.server.rpc_execution.service_call import service, function, client


@service()
class FixtureService:
    def ping(self) -> str:
        return "pong"


class test_add(BaseModel):
    x: int = 1
    y: int = 2


@service()
class CaculService:
    def add(self, x, y):
        """同步加法"""
        return x + y

    def add2(self, data: test_add):
        """同步加法"""
        return data.x + data.y

    async def async_mul(self, x, y):
        """异步乘法"""
        await asyncio.sleep(0.1)
        return x * y

    def fail(self, x):
        """会失败的函数"""
        raise RuntimeError("Oops!")

    @function(client_stream=True, idempotent_key="numbers")
    async def client_stream_sum(self, numbers: list[int]):
        """客户端流式求和"""
        return sum(numbers)

    @function(server_stream=True, idempotent_key="start")
    async def server_stream_countdown(self, start: int):
        """服务端流式倒计时"""
        for i in range(start, -1, -1):
            await asyncio.sleep(1)
            yield i

    @function(bidirectional_stream=True, idempotent_key="messages")
    async def bidi_echo(self, messages: list[str]):
        """双向流式回声"""
        for msg in messages:
            await asyncio.sleep(0.5)
            yield msg
