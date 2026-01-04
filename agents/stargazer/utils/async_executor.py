# -*- coding: utf-8 -*-
"""
异步执行器工具 - 提供线程池和协程并发执行能力

支持:
1. 并发执行异步任务（协程）
2. 并发执行同步任务（通过线程池）
3. 混合执行（自动识别任务类型）
"""

import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import List, Callable, Any, Optional, Coroutine
from sanic.log import logger


class AsyncExecutor:
    """异步执行器 - 支持协程和线程池混合执行"""

    def __init__(self, max_workers: Optional[int] = None):
        """
        初始化异步执行器
        
        Args:
            max_workers: 线程池最大工作线程数，默认为 None（使用系统默认值）
        """
        self.max_workers = max_workers
        self._executor = None

    @property
    def executor(self) -> ThreadPoolExecutor:
        """延迟初始化线程池"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._executor

    async def run_in_thread(self, func: Callable, *args, **kwargs) -> Any:
        """
        在线程池中执行同步函数
        
        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: func(*args, **kwargs)
        )

    async def execute_tasks(
        self,
        tasks: List[Callable],
        task_args: Optional[List[tuple]] = None,
        task_kwargs: Optional[List[dict]] = None,
        return_exceptions: bool = False
    ) -> List[Any]:
        """
        并发执行多个任务（自动识别协程和同步函数）
        
        Args:
            tasks: 任务列表（可以是协程函数或普通函数）
            task_args: 每个任务的位置参数列表
            task_kwargs: 每个任务的关键字参数列表
            return_exceptions: 是否返回异常而不抛出（默认 False）
            
        Returns:
            所有任务的执行结果列表
            
        Examples:
            # 执行协程任务
            results = await executor.execute_tasks([async_func1, async_func2])
            
            # 执行同步任务
            results = await executor.execute_tasks([sync_func1, sync_func2])
            
            # 混合执行
            results = await executor.execute_tasks([async_func, sync_func])
            
            # 带参数执行
            results = await executor.execute_tasks(
                tasks=[func1, func2],
                task_args=[(arg1,), (arg2,)],
                task_kwargs=[{'key': 'val1'}, {'key': 'val2'}]
            )
        """
        if not tasks:
            return []

        # 准备参数
        if task_args is None:
            task_args = [()] * len(tasks)
        if task_kwargs is None:
            task_kwargs = [{}] * len(tasks)

        # 确保参数列表长度一致
        if len(task_args) != len(tasks) or len(task_kwargs) != len(tasks):
            raise ValueError("task_args and task_kwargs must have the same length as tasks")

        # 创建协程列表
        coroutines = []
        for task, args, kwargs in zip(tasks, task_args, task_kwargs):
            if inspect.iscoroutinefunction(task):
                # 异步函数：直接调用
                coroutines.append(task(*args, **kwargs))
            elif callable(task):
                # 同步函数：在线程池中执行
                coroutines.append(self.run_in_thread(task, *args, **kwargs))
            else:
                raise TypeError(f"Task must be a callable or coroutine function, got {type(task)}")

        # 并发执行所有协程
        logger.info(f"🚀 Executing {len(coroutines)} tasks concurrently...")
        results = await asyncio.gather(*coroutines, return_exceptions=return_exceptions)
        logger.info(f"✅ All {len(coroutines)} tasks completed")

        return results

    async def map_async(
        self,
        func: Callable,
        items: List[Any],
        return_exceptions: bool = False
    ) -> List[Any]:
        """
        对列表中的每个元素并发执行同一个函数
        
        Args:
            func: 要执行的函数（协程或普通函数）
            items: 输入列表
            return_exceptions: 是否返回异常而不抛出
            
        Returns:
            所有执行结果列表
            
        Examples:
            # 对每个 IP 执行采集
            results = await executor.map_async(collect_func, ip_list)
        """
        tasks = [func] * len(items)
        task_args = [(item,) for item in items]
        return await self.execute_tasks(
            tasks=tasks,
            task_args=task_args,
            return_exceptions=return_exceptions
        )

    def shutdown(self, wait: bool = True):
        """
        关闭线程池
        
        Args:
            wait: 是否等待所有任务完成
        """
        if self._executor is not None:
            logger.info("🛑 Shutting down thread pool executor...")
            self._executor.shutdown(wait=wait)
            self._executor = None

    def __del__(self):
        """析构函数：自动关闭线程池"""
        self.shutdown(wait=False)


# 全局默认执行器实例（可选）
_default_executor = None


def get_default_executor(max_workers: Optional[int] = None) -> AsyncExecutor:
    """
    获取全局默认执行器
    
    Args:
        max_workers: 线程池最大工作线程数
        
    Returns:
        AsyncExecutor 实例
    """
    global _default_executor
    if _default_executor is None:
        _default_executor = AsyncExecutor(max_workers=max_workers)
    return _default_executor


async def concurrent_execute(
    tasks: List[Callable],
    max_workers: Optional[int] = None,
    return_exceptions: bool = False
) -> List[Any]:
    """
    便捷函数：并发执行任务列表
    
    Args:
        tasks: 任务列表
        max_workers: 最大工作线程数
        return_exceptions: 是否返回异常
        
    Returns:
        执行结果列表
    """
    executor = AsyncExecutor(max_workers=max_workers)
    try:
        return await executor.execute_tasks(tasks, return_exceptions=return_exceptions)
    finally:
        executor.shutdown()
