"""插件侧同步 SDK 的统一包装工具。"""

from __future__ import annotations

import asyncio
import functools


def threaded_collect(sync_method):
    """让插件在自身边界把同步采集放入 asyncio 共享默认线程池。"""

    @functools.wraps(sync_method)
    async def collect_async(self, *args, **kwargs):
        return await asyncio.to_thread(sync_method, self, *args, **kwargs)

    return collect_async
