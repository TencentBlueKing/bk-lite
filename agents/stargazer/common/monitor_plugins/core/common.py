# shim: common utilities
import time
import logging

logger = logging.getLogger("root")


def retry(retry_times=3, interval=5, catch_exp=False):
    def wrapper(func):
        def inner(*args, **kwargs):
            error = None
            for i in range(retry_times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Retry {i + 1} failed: {e}")
                    time.sleep(interval)
                    error = e
            if not catch_exp:
                raise error

        return inner

    return wrapper
