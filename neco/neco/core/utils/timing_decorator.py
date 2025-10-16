"""
计时装饰器模块
提供统一的函数执行时间监控和日志记录
"""
import time
import functools
import asyncio
import uuid
from typing import Callable, Any, Optional
from loguru import logger


def timeit(operation_name: Optional[str] = None, log_args: bool = False):
    """
    通用计时装饰器，记录函数执行时间

    Args:
        operation_name: 操作名称，如不指定则使用函数名
        log_args: 是否记录函数参数（注意敏感信息）
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # 生成调用唯一标识
            call_id = str(uuid.uuid4())[:8]
            # 获取操作名称
            op_name = operation_name or func.__name__

            # 记录开始
            start_time = time.perf_counter()
            # logger.info(f"[PERF] [{call_id}] {op_name} 开始")

            try:
                # 执行异步函数
                result = await func(*args, **kwargs)

                # 计算耗时并记录成功日志
                duration = time.perf_counter() - start_time
                logger.info(
                    f"[PERF] [{call_id}] {op_name} 完成 - 耗时: {duration:.3f}s | "
                    f"call_id={call_id} operation={op_name} function={func.__name__} "
                    f"type=async duration={duration:.3f} status=success"
                )

                return result

            except Exception as e:
                # 计算耗时并记录失败日志
                duration = time.perf_counter() - start_time
                logger.error(
                    f"[PERF] [{call_id}] {op_name} 失败 - 耗时: {duration:.3f}s | "
                    f"call_id={call_id} operation={op_name} function={func.__name__} "
                    f"type=async duration={duration:.3f} status=error error_type={type(e).__name__}"
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            # 生成调用唯一标识
            call_id = str(uuid.uuid4())[:8]
            # 获取操作名称
            op_name = operation_name or func.__name__

            # 记录开始
            start_time = time.perf_counter()
            # logger.info(f"[PERF] [{call_id}] {op_name} 开始")

            try:
                # 执行同步函数
                result = func(*args, **kwargs)

                # 计算耗时并记录成功日志
                duration = time.perf_counter() - start_time
                logger.info(
                    f"[PERF] [{call_id}] {op_name} 完成 - 耗时: {duration:.3f}s | "
                    f"call_id={call_id} operation={op_name} function={func.__name__} "
                    f"type=sync duration={duration:.3f} status=success"
                )

                return result

            except Exception as e:
                # 计算耗时并记录失败日志
                duration = time.perf_counter() - start_time
                logger.error(
                    f"[PERF] [{call_id}] {op_name} 失败 - 耗时: {duration:.3f}s | "
                    f"call_id={call_id} operation={op_name} function={func.__name__} "
                    f"type=sync duration={duration:.3f} status=error error_type={type(e).__name__}"
                )
                raise

        # 根据函数类型返回对应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator
