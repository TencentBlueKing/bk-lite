import asyncio

from .registry import default_registry
from .utils import database_sync_to_async


async def nats_handler(key: str, data):
    args = data.get("args", [])
    kwargs = data.get("kwargs", {})

    data = default_registry.registry.get(key)
    if data is None:
        raise ValueError(f"No function found for `{key}`")

    func = data["func"]
    if not asyncio.iscoroutinefunction(func):
        # 默认共用一条线程，数据库连接留在这条线程上。长查询把
        # _nats_thread_sensitive 设为 False，避免占住其余 handler。
        func = database_sync_to_async(func, thread_sensitive=getattr(func, "_nats_thread_sensitive", True))

    return await func(*args, **kwargs)
