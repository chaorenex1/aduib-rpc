import asyncio
from concurrent import futures
from types import CoroutineType, FunctionType

async_thread_pool = futures.ThreadPoolExecutor(thread_name_prefix='async_thread_pool')

class AsyncUtils:
    @classmethod
    def run_async(cls, func_or_coro, *args, **kwargs):
        """
            使用线程池在独立事件循环中运行协程任务，
            主线程阻塞等待结果。
            """

        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 判断是协程对象还是函数
                if isinstance(func_or_coro, CoroutineType):
                    coro = func_or_coro
                elif isinstance(func_or_coro, FunctionType):
                    coro = func_or_coro(*args, **kwargs)
                else:
                    raise TypeError("func_or_coro must be an async function or coroutine object")
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        # 在线程池中执行协程
        future = async_thread_pool.submit(run_in_thread)
        return future.result()
