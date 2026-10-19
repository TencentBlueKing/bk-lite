import math
import os
import threading
from contextlib import contextmanager
from functools import wraps

from django.db import connections

from apps.core.logger import monitor_logger as logger
from apps.core.utils.web_utils import WebUtils


def _positive_number_env(name, default, caster):
    try:
        value = caster(os.getenv(name, str(default)))
        valid = math.isfinite(value) and value > 0
    except (OverflowError, TypeError, ValueError):
        return default
    return value if valid else default


USER_QUERY_MAX_CONCURRENCY = int(_positive_number_env("MONITOR_USER_QUERY_MAX_CONCURRENCY", 4, int))
USER_QUERY_WAIT_TIMEOUT_SECONDS = float(_positive_number_env("MONITOR_USER_QUERY_WAIT_TIMEOUT_SECONDS", 15.0, float))

_slots_lock = threading.Lock()
_user_slots: dict[tuple[str, str], threading.BoundedSemaphore] = {}


class UserQueryBusyError(Exception):
    """同一用户同类查询过多，调用方应返回 429。"""


def _semaphore_for(user_key: str, group: str) -> threading.BoundedSemaphore:
    key = (user_key, group)
    with _slots_lock:
        semaphore = _user_slots.get(key)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(USER_QUERY_MAX_CONCURRENCY)
            _user_slots[key] = semaphore
        return semaphore


def _release_open_connections():
    """排队前释放已打开的连接，未打开则不动（避免无 DB 测试被 pytest-django 拦截）。"""
    for conn in connections.all():
        if conn.connection is not None:
            conn.close()


@contextmanager
def acquire_user_query_slot(user_id, group="query"):
    user_key = str(user_id if user_id is not None else "anonymous")
    semaphore = _semaphore_for(user_key, group)
    # 排队期间不占用 PG：auth 中间件可能已打开连接。
    _release_open_connections()
    acquired = semaphore.acquire(timeout=USER_QUERY_WAIT_TIMEOUT_SECONDS)
    if not acquired:
        logger.warning(
            "event=monitor_user_query_busy user_id=%s group=%s failed_stage=acquire_slot error_type=UserQueryBusyError",
            user_key,
            group,
        )
        raise UserQueryBusyError("查询繁忙，请稍后重试")
    logger.debug("event=monitor_user_query_acquired user_id=%s group=%s", user_key, group)
    try:
        yield
    finally:
        semaphore.release()


def with_user_query_slot(group="query"):
    def decorator(view_method):
        @wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            user_id = getattr(getattr(request, "user", None), "id", None)
            try:
                with acquire_user_query_slot(user_id, group=group):
                    return view_method(self, request, *args, **kwargs)
            except UserQueryBusyError as exc:
                return WebUtils.response_error(error_message=str(exc), status_code=429)

        return wrapper

    return decorator
