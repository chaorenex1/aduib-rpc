import asyncio


async_thread_pool = futures.ThreadPoolExecutor(thread_name_prefix='async_thread_pool')

class AsyncUtils:
    @classmethod
    def run_async(cls, coro):
        """
            使用线程池在独立事件循环中运行协程任务，
            主线程阻塞等待结果。
            """

        def run_in_thread(coro):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        # 在线程池中执行协程
        future = async_thread_pool.submit(run_in_thread, coro)
        return future.result()
