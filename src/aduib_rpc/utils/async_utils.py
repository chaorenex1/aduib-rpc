import asyncio


class AsyncUtils:
    @classmethod
    def run_async(cls,coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有 loop，新建一个
            return asyncio.run(coro)
        else:
            # 有 loop，直接创建任务
            return loop.create_task(coro)

    @classmethod
    def get_or_create_event_loop(cls):
        """Gets or creates an event loop."""
        try:
            asyncio.create_task()
            return asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

