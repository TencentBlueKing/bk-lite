# -- coding: utf-8 --
# @File: decorator.py
# @Time: 2025/12/23 15:21
# @Author: windyzhao
import time
from functools import wraps
from typing import Callable, Any


def timer(logger=None):
    """
    计时装饰器

    Args:
        logger: 可选的logging.Logger实例，如果提供则记录日志，否则打印到控制台
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 开始计时
            start_time = time.perf_counter()

            try:
                # 执行函数
                result = func(*args, **kwargs)
                return result

            finally:
                # 计算耗时
                end_time = time.perf_counter()
                elapsed_time = end_time - start_time

                # 格式化消息
                message = f"Function '{func.__name__}' executed in {elapsed_time:.6f} seconds"

                # 记录或打印
                if logger:
                    logger.info(message)
                else:
                    print(f"[Timer] {message}")

        return wrapper

    return decorator
