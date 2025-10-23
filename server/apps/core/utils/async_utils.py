"""
异步工具函数模块
提供 ASGI 环境下的兼容性工具
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

from apps.core.logger import opspilot_logger as logger


def create_async_compatible_generator(sync_generator):
    """
    创建与 ASGI 兼容的异步生成器

    在 ASGI 环境下，StreamingHttpResponse 需要异步迭代器。
    这个函数将同步生成器转换为异步生成器，并在线程池中执行同步操作，
    避免阻塞事件循环。

    Args:
        sync_generator: 同步生成器对象

    Returns:
        异步生成器，与 ASGI 兼容
    """

    async def async_wrapper():
        """异步包装器"""
        try:
            # 在线程池中运行同步生成器，避免阻塞事件循环
            loop = asyncio.get_event_loop()

            def get_next_item():
                try:
                    return next(sync_generator)
                except StopIteration:
                    return None

            with ThreadPoolExecutor() as executor:
                while True:
                    # 在线程池中执行同步操作
                    item = await loop.run_in_executor(executor, get_next_item)
                    if item is None:
                        break
                    yield item

        except Exception as e:
            logger.error(f"Async generator wrapper error: {e}")
            # 返回错误信息，格式取决于使用场景
            yield f"error: {str(e)}\n\n"

    return async_wrapper()
